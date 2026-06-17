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
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input=json.dumps(payload) if not isinstance(payload, str) else payload,
            capture_output=True, text=True, timeout=15)
        rdir = os.path.join(td, ".receipts")
        receipts = []
        if os.path.isdir(rdir):
            for name in os.listdir(rdir):
                with open(os.path.join(rdir, name)) as fh:
                    receipts.append(json.load(fh))
        return proc.returncode, receipts


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


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
