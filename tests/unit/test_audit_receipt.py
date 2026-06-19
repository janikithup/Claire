#!/usr/bin/env python3
"""
UNIT TEST — leak-audit RECEIPT writer behavioural contract.

record-audit-receipt.py is a PostToolUse hook on the Agent/Task tool. Its single
job: when brief-leak-auditor finishes with a CLEAN verdict (GENUINELY-NEUTRAL and
no lean), write a short-lived receipt — a normalised fingerprint of the brief that
passed — into hooks/.receipts/. The gate then requires that receipt. The receipt
must NOT be written for a leaning verdict, nor for any other agent.

We drive the hook directly with crafted PostToolUse stdin and inspect the receipt
dir it writes beside its own copy. Each assertion names the bug it guards.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "record-audit-receipt.py"))


def _normalise(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def run_hook(payload):
    """Run the receipt writer on one stdin payload in an isolated dir.
    Returns the list of receipt dicts it wrote (empty if none)."""
    with tempfile.TemporaryDirectory() as td:
        hook_copy = os.path.join(td, "record-audit-receipt.py")
        with open(HOOK) as fh:
            src = fh.read()
        with open(hook_copy, "w") as fh:
            fh.write(src)
        run_env = dict(os.environ)
        run_env.pop("CLAIRE_DEBUG", None)  # hermetic: don't inherit the dev's switch
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input=json.dumps(payload) if not isinstance(payload, str) else payload,
            capture_output=True, text=True, timeout=15, env=run_env)
        rdir = os.path.join(td, ".receipts")
        receipts = []
        if os.path.isdir(rdir):
            for name in os.listdir(rdir):
                with open(os.path.join(rdir, name)) as fh:
                    receipts.append(json.load(fh))
        return proc.returncode, receipts


def run_hook_debug(payload, env=None):
    """Like run_hook but also returns the hook's stdout and supports env overrides —
    used by the CLAIRE_DEBUG trace tests. Returns (returncode, stdout, receipts)."""
    with tempfile.TemporaryDirectory() as td:
        hook_copy = os.path.join(td, "record-audit-receipt.py")
        with open(HOOK) as fh:
            src = fh.read()
        with open(hook_copy, "w") as fh:
            fh.write(src)
        run_env = dict(os.environ)
        run_env.pop("CLAIRE_DEBUG", None)
        if env:
            run_env.update(env)
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input=json.dumps(payload) if not isinstance(payload, str) else payload,
            capture_output=True, text=True, timeout=15, env=run_env)
        rdir = os.path.join(td, ".receipts")
        receipts = []
        if os.path.isdir(rdir):
            for name in os.listdir(rdir):
                with open(os.path.join(rdir, name)) as fh:
                    receipts.append(json.load(fh))
        return proc.returncode, proc.stdout, receipts


def _post(subagent_type, brief, response):
    """Shape a PostToolUse payload the way the harness delivers an Agent result."""
    return {"tool_input": {"subagent_type": subagent_type, "prompt": brief},
            "tool_response": response}


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_clean_verdict_writes_receipt():
    """BUG GUARDED: the auditor passes a brief but no receipt is written, so the gate
    can never go silent and every clean dispatch gets nagged. A GENUINELY-NEUTRAL
    verdict must write exactly one receipt."""
    brief = "Situation: a team must choose between two suppliers. Outside read?"
    rc, receipts = run_hook(_post("brief-leak-auditor", brief,
                                  "GENUINELY-NEUTRAL\nThe brief states both options flatly."))
    assert rc == 0
    assert len(receipts) == 1, "a clean verdict must write exactly one receipt"
    assert receipts[0]["text"] == _normalise(brief), "receipt must store the normalised brief"


@case
def test_lean_verdict_writes_no_receipt():
    """BUG GUARDED: a leaning brief still earns a receipt, defeating the entire point
    — a leaky brief would then pass the gate. A LEAN verdict must write NOTHING."""
    brief = "Obviously option A is wasteful; find problems with it."
    rc, receipts = run_hook(_post("brief-leak-auditor", brief,
                                  "LEAN-B\nTells: 'obviously', 'wasteful' load option A negatively."))
    assert rc == 0
    assert receipts == [], "a leaning verdict must NOT write a receipt"


@case
def test_clean_verdict_mentioning_cleanly_still_writes_receipt():
    """BUG GUARDED (review SHOULD-FIX 2): the lean check was a blunt 'lean-' substring,
    so a clean verdict that uses an ordinary word like 'cleanly' (contains 'lean')
    failed to earn a receipt, sending the user into a false warning loop. The check
    must match the LEAN-<option> verdict token, not prose."""
    brief = "Two vendors, one slot — which, and why? State the trade-offs."
    rc, receipts = run_hook(_post("brief-leak-auditor", brief,
                                  "GENUINELY-NEUTRAL\nThe brief is cleanly framed and leans neither way."))
    assert len(receipts) == 1, "a clean verdict using the word 'cleanly'/'leans' must still write a receipt"


@case
def test_negated_neutral_writes_no_receipt():
    """BUG GUARDED: the auditor phrases a lean as 'this is NOT genuinely-neutral', which
    contains the substring 'genuinely-neutral' — a naive positive match would wrongly
    write a receipt. A negated neutral must NOT earn one."""
    brief = "Obviously option A wins; poke holes in it."
    rc, receipts = run_hook(_post("brief-leak-auditor", brief,
                                  "This is NOT genuinely-neutral. LEAN-A: 'obviously' loads the answer."))
    assert receipts == [], "a negated 'not genuinely-neutral' verdict must not write a receipt"


@case
def test_namespaced_auditor_writes_receipt():
    """BUG GUARDED: the live auditor arrives namespaced (claire:brief-leak-auditor);
    if the writer only matched the bare name it would never record a receipt in
    production. It must strip the namespace prefix."""
    brief = "Two roads diverge; which to take? State the trade-offs."
    rc, receipts = run_hook(_post("claire:brief-leak-auditor", brief, "GENUINELY-NEUTRAL"))
    assert len(receipts) == 1, "namespaced auditor name must still write a receipt"


@case
def test_other_agent_writes_no_receipt():
    """BUG GUARDED: any agent's clean-looking output writes a receipt, so a brief that
    never went through the auditor gets certified. Only brief-leak-auditor results may
    write a receipt."""
    brief = "Attack this plan."
    rc, receipts = run_hook(_post("failure-mode-attacker", brief,
                                  "This plan is GENUINELY-NEUTRAL in places but risky."))
    assert receipts == [], "a non-auditor dispatch must never write a receipt"


@case
def test_response_as_content_blocks():
    """BUG GUARDED: the auditor's verdict arrives as a list of content blocks (not a
    plain string), the writer fails to find GENUINELY-NEUTRAL, and no receipt is
    written though the brief passed. The writer must search structured responses too."""
    brief = "A scheduling conflict between two teams — what is the outside view?"
    payload = {"tool_input": {"subagent_type": "brief-leak-auditor", "prompt": brief},
               "tool_response": [{"type": "text", "text": "GENUINELY-NEUTRAL"}]}
    rc, receipts = run_hook(payload)
    assert len(receipts) == 1, "a structured (list) response must still be parsed for the verdict"


@case
def test_fail_open_on_garbage_stdin():
    """BUG GUARDED: a writer error disrupts the dispatch. FAIL-OPEN — garbage input
    must exit 0 and write nothing, never raise."""
    rc, receipts = run_hook("not json at all {{{")
    assert rc == 0, "fail-open: must exit 0 on garbage input"
    assert receipts == []


@case
def test_clean_verdict_declining_a_lean_still_writes_receipt():
    """BUG GUARDED (observed live 2026-06-17, twice): the leak-auditor discusses leans BY
    NATURE even when it passes - it writes "I considered a faint LEAN-One but am declining"
    and concludes GENUINELY-NEUTRAL. A detector that scanned for a LEAN token ANYWHERE
    suppressed the receipt for a brief that PASSED. Per the agent contract the verdict comes
    first, so a clean pass = GENUINELY-NEUTRAL appears before any LEAN-<option> token."""
    brief = "A school has one slot and two clubs want it; choose one."
    resp = ("**Verdict**\n\nGENUINELY-NEUTRAL\n\nReasoning: I considered calling a faint "
            "LEAN-One on the first-position basis, per the err-toward-naming rule. I am "
            "declining because the concreteness is option-intrinsic, not authorial.")
    rc, receipts = run_hook(_post("claire:brief-leak-auditor", brief, resp))
    assert len(receipts) == 1, "a GENUINELY-NEUTRAL verdict that merely DISCUSSES a declined lean must still write a receipt"


@case
def test_lean_verdict_before_neutral_mention_writes_no_receipt():
    """BUG GUARDED: the opposite direction must stay closed. A real lean whose verdict is
    LEAN-B and then notes the brief "seems genuinely-neutral at first" in its reasoning must
    NOT earn a receipt - the verdict (first) is LEAN-B; the neutral mention follows it."""
    brief = "Obviously option A is wasteful; find problems with it."
    resp = ("**Verdict**\nLEAN-B\n\nThe tells: at first glance it seems genuinely-neutral, "
            "but 'obviously' and 'wasteful' load option A negatively.")
    rc, receipts = run_hook(_post("claire:brief-leak-auditor", brief, resp))
    assert receipts == [], "a LEAN-B verdict must not earn a receipt even if 'genuinely-neutral' appears later"


@case
def test_dismissive_neutral_opener_before_lean_writes_no_receipt():
    """BUG GUARDED (de-priming ENFORCEMENT HOLE, found 2026-06-19 by observing the live
    auditor): when the auditor flags a LEAN it often OPENS by dismissing neutrality —
    'GENUINELY-NEUTRAL - does not apply here ... Verdict: LEAN-x'. The clean token then
    appears FIRST (position 0), un-negated by any preceding 'not', so the
    neutral-before-lean ordering rule wrongly reads it as clean and writes a receipt for a
    LEANING brief — which makes the gate go silent on a primed dispatch. The asserted LEAN
    verdict must win regardless of an earlier dismissive 'genuinely-neutral'."""
    brief = "Gut-check on the test plan: assert each function returns what the code produces today; confirm it's solid?"
    resp = ("GENUINELY-NEUTRAL — does not apply here. This brief carries a clear lean.\n\n"
            "**Verdict:** LEAN-the-plan-is-sound (the test plan should be approved as-is)\n\n"
            "The tells: 'guaranteed-green suite that proves the calculator works' frames the "
            "weakness as a feature; 'no real need to question the rounding' steers the critic away.")
    rc, receipts = run_hook(_post("claire:brief-leak-auditor", brief, resp))
    assert receipts == [], "a LEAN verdict opening with a dismissed 'GENUINELY-NEUTRAL' must NOT earn a receipt"


# --- CLAIRE_DEBUG trace switch (off by default; adds visibility, never changes the write) ---

@case
def test_debug_on_clean_verdict_emits_trace_and_still_writes():
    """BUG GUARDED: debug mode must let the builder SEE the verdict that earned a receipt
    without changing the write. A clean verdict with CLAIRE_DEBUG on emits a [CLAIRE TRACE]
    line naming verdict=CLEAN, and still writes exactly one receipt."""
    brief = "Situation: a team must choose between two suppliers. Outside read?"
    rc, stdout, receipts = run_hook_debug(
        _post("claire:brief-leak-auditor", brief,
              "GENUINELY-NEUTRAL\nBoth options stated flatly."),
        env={"CLAIRE_DEBUG": "1"})
    assert len(receipts) == 1, "debug must not change the receipt write"
    ctx = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[CLAIRE TRACE]" in ctx and "verdict=CLEAN" in ctx and "wrote" in ctx.lower()


@case
def test_debug_on_lean_verdict_emits_trace_and_writes_nothing():
    """BUG GUARDED: debug visibility on a LEAN must report the refusal AND still write no
    receipt — the trace must never become a back door that certifies a leaning brief."""
    brief = "Obviously option A is wasteful; find problems with it."
    rc, stdout, receipts = run_hook_debug(
        _post("claire:brief-leak-auditor", brief, "LEAN-B\nTells: 'obviously', 'wasteful'."),
        env={"CLAIRE_DEBUG": "1"})
    assert receipts == [], "a LEAN verdict must still write no receipt under debug"
    ctx = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[CLAIRE TRACE]" in ctx and "verdict=LEAN" in ctx and "no receipt" in ctx.lower()


@case
def test_debug_off_emits_no_trace():
    """BUG GUARDED (regression): debug accidentally on by default would spam every dispatch
    with a trace. With CLAIRE_DEBUG unset, the writer emits NO stdout."""
    brief = "Two vendors, one slot — which, and why?"
    rc, stdout, receipts = run_hook_debug(
        _post("claire:brief-leak-auditor", brief, "GENUINELY-NEUTRAL"))
    assert stdout.strip() == "", "no trace when debug is off"
    assert len(receipts) == 1


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
