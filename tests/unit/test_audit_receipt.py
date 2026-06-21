#!/usr/bin/env python3
"""
UNIT TEST — leak-audit RECEIPT writer, sentinel-verdict design (>=2026-06-21).

record-audit-receipt.py is a PostToolUse hook. On a CLEAN brief-leak-auditor verdict it stores
the audited brief VERBATIM, keyed by the orchestrator nonce carried in the auditor prompt as
[CLAIRE-RECEIPT:<nonce>]. The companion gate later injects that brief into the critic. No
fingerprint, no normalisation — the bytes the auditor judged are the bytes stored (only the nonce
marker is stripped, cosmetically).

"Clean" is now read from the auditor's MACHINE verdict line — `CLAIRE-VERDICT: NEUTRAL` — not
guessed from prose. So these tests pin the EFFECT contract (write iff clean-sentinel + nonce +
auditor) against the sentinel, and no longer chase prose edge cases (those bugs are gone by
construction; the prose around the sentinel is irrelevant). Each assertion names the bug it guards.

Receipt = .receipts/<nonce>.json : {"ts": <float>, "nonce": <str>, "brief": <verbatim>}.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "record-audit-receipt.py"))

# A clean / leaning auditor response is one that ENDS with the machine verdict line. The prose
# above the line is deliberately noisy (mentions "lean", "neutral") to prove it is ignored.
CLEAN = "The brief states both options flatly; it leans neither way.\nCLAIRE-VERDICT: NEUTRAL"
LEAN = "The framing tilts toward the first option.\nCLAIRE-VERDICT: LEAN"
NO_VERDICT = "GENUINELY-NEUTRAL, I think — though the framing maybe leans. (no machine line)"
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


# --- the core: clean sentinel + nonce writes one verbatim, nonce-keyed receipt ----

@case
def test_clean_verdict_with_nonce_writes_one_receipt():
    """BUG GUARDED: a passed brief leaves no receipt, so the gate can never inject and nags every
    clean run. A CLAIRE-VERDICT: NEUTRAL on a nonce-tagged brief must write exactly one receipt."""
    brief = "A team must pick one of two suppliers. What is the outside read?"
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("aa11bb22", brief), CLEAN))
    assert rc == 0
    assert len(receipts) == 1, "a clean nonce-tagged verdict must write exactly one receipt"
    assert receipts[0]["nonce"] == "aa11bb22", "receipt must be keyed by the nonce"


@case
def test_receipt_stores_brief_verbatim_not_normalised():
    """BUG GUARDED: the receipt stores a normalised/lowercased fingerprint, so the injected brief
    differs from what the auditor read. The brief must be stored VERBATIM — case and structure
    preserved — with only the [CLAIRE-RECEIPT:<nonce>] marker stripped."""
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
    nothing — the handshake was not run. No nonce -> nothing to inject against -> no receipt."""
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


# --- leaning / sentinel-less verdicts write nothing -----------------------------

@case
def test_lean_verdict_writes_no_receipt():
    """BUG GUARDED: a leaning brief earns a receipt and then sails through the gate. A
    CLAIRE-VERDICT: LEAN line must write NOTHING."""
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("ln01", "Find what's wrong with A."), LEAN))
    assert receipts == [], "a leaning verdict must write no receipt"


@case
def test_no_verdict_line_fails_closed():
    """BUG GUARDED (the whole point of the sentinel): an auditor response with NO machine verdict
    line — however neutral its prose sounds — must NOT earn a receipt. The verdict is read from the
    line we define, not guessed from prose, so a missing line fails closed (the gate nags)."""
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("nv01", "Two vendors, one slot."), NO_VERDICT))
    assert receipts == [], "a response with no CLAIRE-VERDICT line must write no receipt"


@case
def test_last_verdict_line_wins():
    """BUG GUARDED: the auditor restates the line while reasoning, then lands its real verdict. The
    LAST verdict line decides — a NEUTRAL it later overrides with LEAN must not earn a receipt."""
    resp = ("On a first pass I'd write CLAIRE-VERDICT: NEUTRAL.\n\n"
            "But the closing beat tilts it.\n\nCLAIRE-VERDICT: LEAN")
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("lw01", "Gut-check the plan."), resp))
    assert receipts == [], "a verdict ending in LEAN must not earn a receipt even if NEUTRAL appears earlier"


# --- prose around the sentinel is irrelevant ------------------------------------

@case
def test_clean_sentinel_with_lean_discussion_still_writes():
    """BUG GUARDED (the false-warn class the sentinel retires): a clean audit whose PROSE weighs
    or quotes a lean (LEAN-x, "leans", "closer to neutral") must still write — only the machine
    line is read, so the prose cannot suppress a clean pass."""
    resp = ("I weighed a faint LEAN-One toward the first club and quoted e.g. LEAN-road-A as the "
            "shape it would take, then declined; it drifts closer to neutral and lands there.\n\n"
            "CLAIRE-VERDICT: NEUTRAL")
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("pr01", "Two clubs, one slot."), resp))
    assert len(receipts) == 1, "prose discussing a lean must not block a clean CLAIRE-VERDICT: NEUTRAL"


@case
def test_markdown_around_sentinel_writes():
    """BUG GUARDED: the auditor wraps the line in emphasis/blockquote markup. The reader tolerates
    cosmetic markup around the sentinel, so '**CLAIRE-VERDICT: NEUTRAL**' must still write."""
    resp = "Both options stated flatly with symmetric detail.\n\n**CLAIRE-VERDICT: NEUTRAL**"
    rc, out, receipts = run_hook(_post(AUDITOR, _tagged("md01", "Build or buy?"), resp))
    assert len(receipts) == 1, "markdown around the sentinel must still write a receipt"


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
    results may write one — even a perfectly-formed CLAIRE-VERDICT: NEUTRAL from another agent."""
    rc, out, receipts = run_hook(_post("adversarial-review", _tagged("na01", "Attack this plan."), CLEAN))
    assert receipts == [], "only the leak-auditor's results may write a receipt"


# --- shape independence: verdict found in string / list / dict ------------------

@case
def test_clean_verdict_in_content_blocks_writes():
    blocks = [{"type": "text", "text": CLEAN}]
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("cb01", "A scheduling clash — view?"), blocks))
    assert len(receipts) == 1, "a clean verdict in content blocks must still write"


@case
def test_lean_verdict_in_content_blocks_writes_nothing():
    blocks = [{"type": "text", "text": LEAN}]
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("cb02", "Poke holes in A."), blocks))
    assert receipts == [], "a leaning verdict in content blocks must write nothing"


@case
def test_clean_verdict_in_dict_response_writes():
    as_dict = {"content": [{"type": "text", "text": CLEAN}]}
    rc, out, receipts = run_hook(_post(AUDITOR_BARE, _tagged("dc01", "Hire or train?"), as_dict))
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
        _post(AUDITOR, _tagged("db03", "Obviously A; poke holes."), LEAN),
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
