#!/usr/bin/env python3
"""
UNIT TEST — leak-audit RECEIPT writer, INJECTION design (>=0.8.0).

record-audit-receipt.py is a PostToolUse hook. On a CLEAN brief-leak-auditor verdict it
stores the audited brief VERBATIM, keyed by the orchestrator nonce carried in the auditor
prompt as [CLAIRE-RECEIPT:<nonce>]. The companion gate later injects that brief into the
critic. No fingerprint, no normalisation — the bytes the auditor judged are the bytes
stored (only the nonce marker is stripped, cosmetically).

Receipt = .receipts/<nonce>.json : {"ts": <float>, "nonce": <str>, "brief": <verbatim>}.
Rule: written WHEN AND ONLY WHEN the auditor returns clean AND the brief carries a nonce.
This file also pins the tolerant verdict-line parser (fold-in 2): a clean verdict that
merely quotes/declines a LEAN example must still write; a real lean (even opening with a
dismissed 'GENUINELY-NEUTRAL') must not. Each assertion names the bug it guards.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "record-audit-receipt.py"))

CLEAN = "GENUINELY-NEUTRAL"
AUDITOR = "claire:brief-leak-auditor"
AUDITOR_BARE = "brief-leak-auditor"
SENTINEL_RE = re.compile(r"\[CLAIRE-RECEIPT:([A-Za-z0-9_-]+)\]")


def run_hook(payload, env=None):
    """Run the receipt writer on one stdin payload in an isolated dir.
    Returns (returncode, stdout, [receipt dicts])."""
    with tempfile.TemporaryDirectory() as td:
        copy = os.path.join(td, "record-audit-receipt.py")
        with open(HOOK) as fh:
            src = fh.read()
        with open(copy, "w") as fh:
            fh.write(src)
        run_env = dict(os.environ)
        run_env.pop("CLAIRE_DEBUG", None)
        if env:
            run_env.update(env)
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([sys.executable, copy], input=stdin,
                              capture_output=True, text=True, timeout=15, env=run_env)
        rdir = os.path.join(td, ".receipts")
        receipts = []
        if os.path.isdir(rdir):
            for name in sorted(os.listdir(rdir)):
                with open(os.path.join(rdir, name)) as fh:
                    receipts.append(json.load(fh))
        return proc.returncode, proc.stdout, receipts


def _post(subagent_type, brief, response):
    return {"tool_input": {"subagent_type": subagent_type, "prompt": brief},
            "tool_response": response}


def _tagged(nonce, brief):
    """A brief carrying the de-priming nonce on its own line, as the skill dispatches it."""
    return "[CLAIRE-RECEIPT:%s]\n%s" % (nonce, brief)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- the core: clean + nonce writes one verbatim, nonce-keyed receipt ------------

@case
def test_clean_verdict_with_nonce_writes_one_receipt():
    """BUG GUARDED: a passed brief leaves no receipt, so the gate can never inject and nags
    every clean run. A clean verdict on a nonce-tagged brief must write exactly one receipt,
    keyed by the nonce."""
    brief = "A team must pick one of two suppliers. What is the outside read?"
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("aa11bb22", brief), CLEAN))
    assert rc == 0
    assert len(receipts) == 1, "a clean nonce-tagged verdict must write exactly one receipt"
    assert receipts[0]["nonce"] == "aa11bb22", "receipt must be keyed by the nonce"


@case
def test_receipt_stores_brief_verbatim_not_normalised():
    """BUG GUARDED: the receipt stores a normalised/lowercased fingerprint, so the injected
    brief differs from what the auditor read. The brief must be stored VERBATIM — case and
    structure preserved — with only the [CLAIRE-RECEIPT:<nonce>] marker stripped."""
    brief = ("Your job is to find the strongest real objection.\n\n"
             "Situation: choose between Vendor-X and Vendor-Y. State the trade-offs.")
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("vx01", brief), CLEAN))
    assert len(receipts) == 1
    assert receipts[0]["brief"] == brief, "stored brief must be the verbatim audited text (nonce marker stripped)"
    assert "Vendor-X" in receipts[0]["brief"], "case must be preserved (no normalisation)"
    assert "CLAIRE-RECEIPT" not in receipts[0]["brief"], "the nonce marker must be stripped from the stored brief"


@case
def test_clean_verdict_without_nonce_writes_nothing():
    """BUG GUARDED: a clean audit on a brief that carries NO nonce writes a receipt keyed by
    nothing — the handshake was not run. With no nonce there is nothing to inject against, so
    no receipt is written and the dispatch will (correctly) fail closed."""
    brief = "A team must pick one of two suppliers. Outside read?"
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, brief, CLEAN))
    assert receipts == [], "a clean verdict with no nonce must write no receipt"


@case
def test_receipt_schema_shape():
    """EFFECT contract: a receipt is {ts: float, nonce: str, brief: str}."""
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("sh01", "Two clubs, one slot — pick one."), CLEAN))
    assert len(receipts) == 1
    r = receipts[0]
    assert isinstance(r["ts"], float) and isinstance(r["nonce"], str) and isinstance(r["brief"], str)


# --- leaning verdicts write nothing ---------------------------------------------

@case
def test_lean_verdict_writes_no_receipt():
    """BUG GUARDED: a leaning brief earns a receipt and then sails through the gate. A LEAN
    verdict must write NOTHING."""
    brief = "Obviously option A is the waste; find what's wrong with it."
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("ln01", brief), "LEAN-A"))
    assert receipts == [], "a leaning verdict must write no receipt"


@case
def test_denies_neutrality_writes_no_receipt():
    """BUG GUARDED: 'the brief is NOT neutral' contains the neutral token and is mistaken for
    a pass. A verdict that denies neutrality must not earn a receipt."""
    brief = "Clearly we should ship Friday; just confirm it."
    deny = "Assessment: the brief is not neutral — it leans toward shipping. LEAN-SHIP."
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("dn01", brief), deny))
    assert receipts == [], "a verdict denying neutrality must not earn a receipt"


@case
def test_dismissive_neutral_opener_before_lean_writes_nothing():
    """BUG GUARDED (de-priming ENFORCEMENT HOLE): the auditor flags a lean but OPENS by
    dismissing neutrality ('GENUINELY-NEUTRAL — does not apply here ... Verdict: LEAN-x'). The
    clean token appears first; a naive first-token grab certifies a LEANING brief. The asserted
    LEAN verdict line must win."""
    brief = "Gut-check the test plan: confirm it's solid?"
    resp = ("GENUINELY-NEUTRAL — does not apply here. This brief carries a clear lean.\n\n"
            "**Verdict:** LEAN-the-plan-is-sound (approve the plan as-is)\n\n"
            "Tells: 'guaranteed-green suite' frames the weakness as a feature.")
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("dm01", brief), resp))
    assert receipts == [], "a LEAN verdict opening with a dismissed GENUINELY-NEUTRAL must not earn a receipt"


# --- the tolerant parser: clean passes that merely MENTION a lean still write ----

@case
def test_pass_discussing_a_declined_lean_still_writes():
    """BUG GUARDED: the auditor passes a brief yet discusses a lean it weighed and declined.
    The brief PASSED, so a receipt must still land — a scan that suppresses on any LEAN token
    sends a clean run into a false-warning loop."""
    brief = "A school has one open slot and two clubs apply; pick one."
    resp = ("Verdict: " + CLEAN + ".\n\n"
            "Reasoning: I weighed whether to call a faint LEAN-One toward the first-named club, "
            "then declined — the concreteness is intrinsic to the option, not authorial.")
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("dl01", brief), resp))
    assert len(receipts) == 1, "a passing verdict discussing a declined lean must still write a receipt"


@case
def test_clean_verdict_quoting_a_lean_example_still_writes():
    """BUG GUARDED (fold-in 2, the false-warn this redesign targets): a clean audit that quotes
    the literal LEAN-<x> EXAMPLE from the auditor's own contract must still write a receipt. The
    verdict-LINE anchor + example-context guard must not read the quoted example as a verdict."""
    brief = "Two roads diverge; which to take and why?"
    resp = ("Verdict: " + CLEAN + "\n\n"
            "(For reference, had it leaned I would have written e.g. LEAN-road-A; it does not.)")
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("ex01", brief), resp))
    assert len(receipts) == 1, "a clean verdict quoting a LEAN example must still write a receipt"


@case
def test_markdown_verdict_label_shape_writes():
    """BUG GUARDED: the live auditor emits '**Verdict** — GENUINELY-NEUTRAL', not a literal
    'VERDICT:' prefix. The tolerant label parser must recognise the markdown-label shape and
    write the receipt — a brittle prefix would fail-close every clean audit."""
    brief = "Build it in-house or buy it off the shelf?"
    resp = "**Verdict** — GENUINELY-NEUTRAL\n\nBoth options stated flatly with symmetric detail."
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("md01", brief), resp))
    assert len(receipts) == 1, "the '**Verdict** — GENUINELY-NEUTRAL' shape must write a receipt"


@case
def test_clean_verdict_mentioning_cleanly_still_writes():
    """BUG GUARDED: a blunt 'lean' substring check fails a clean verdict that uses ordinary
    words ('cleanly', 'leans neither way'). Such a verdict must still write."""
    brief = "Two vendors, one slot — which, and why?"
    resp = "GENUINELY-NEUTRAL\nThe brief is cleanly framed and leans neither way."
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("cl01", brief), resp))
    assert len(receipts) == 1


# --- only the auditor, recognised namespaced or bare ----------------------------

@case
def test_namespaced_auditor_recognised():
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("ns01", "Two roads; which and why?"), CLEAN))
    assert len(receipts) == 1, "the namespaced auditor name must be recognised"


@case
def test_bare_auditor_recognised():
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("br01", "In-house or off the shelf?"), CLEAN))
    assert len(receipts) == 1, "the bare auditor name must be recognised"


@case
def test_non_auditor_writes_nothing():
    """BUG GUARDED: any agent's clean-looking output mints a receipt. Only the leak-auditor's
    results may write one."""
    rc, out, receipts = run_hook(_post(
        "adversarial-review", _tagged("na01", "Attack this plan."),
        "The plan reads " + CLEAN + " in tone, but the rollback step is missing."))
    assert receipts == [], "only the leak-auditor's results may write a receipt"


# --- shape independence: verdict found in string / list / dict ------------------

@case
def test_clean_verdict_in_content_blocks_writes():
    brief = "A scheduling clash between two teams — outside view?"
    blocks = [{"type": "text", "text": CLEAN + " — both sides stated flatly."}]
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("cb01", brief), blocks))
    assert len(receipts) == 1, "a clean verdict in content blocks must still write"


@case
def test_lean_verdict_in_content_blocks_writes_nothing():
    brief = "Obviously we go with A; poke holes in it."
    blocks = [{"type": "text", "text": "LEAN-A — 'obviously' loads the answer."}]
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("cb02", brief), blocks))
    assert receipts == [], "a leaning verdict in content blocks must write nothing"


@case
def test_clean_verdict_in_dict_response_writes():
    brief = "Hire a contractor or train an intern?"
    as_dict = {"content": [{"type": "text", "text": CLEAN}]}
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("dc01", brief), as_dict))
    assert len(receipts) == 1, "a clean verdict in a dict response must still write"


# --- CLAIRE_DEBUG: visibility only ----------------------------------------------

@case
def test_debug_off_prints_nothing():
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("db01", "Two vendors; which?"), CLEAN))
    assert out.strip() == "" and len(receipts) == 1


@case
def test_debug_on_clean_emits_one_trace_and_still_writes():
    rc, out, receipts = run_hook(
        _post(AUDITOR, _tagged("db02", "Choose between two suppliers."), CLEAN),
        env={"CLAIRE_DEBUG": "1"})
    assert len(receipts) == 1, "debug must not change the write"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


@case
def test_debug_on_lean_emits_trace_and_writes_nothing():
    rc, out, receipts = run_hook(
        _post(AUDITOR, _tagged("db03", "Obviously A; poke holes."), "LEAN-B"),
        env={"CLAIRE_DEBUG": "1"})
    assert receipts == [], "debug must not turn a lean into a receipt"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    json.loads(lines[0])


# --- robustness: fail open ------------------------------------------------------

@case
def test_garbage_stdin_fails_open():
    rc, out, receipts = run_hook("this is not json {{{")
    assert rc == 0 and receipts == []


@case
def test_empty_and_missing_fields_fail_open():
    rc1, _, r1 = run_hook("")
    rc2, _, r2 = run_hook({"something_else": True})
    assert rc1 == 0 and r1 == []
    assert rc2 == 0 and r2 == []


@case
def test_clean_verdict_empty_brief_does_not_crash():
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("eb01", "   "), CLEAN))
    assert rc == 0, "an empty brief must not crash the hook"
    assert receipts == [], "an empty brief has nothing to store"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
