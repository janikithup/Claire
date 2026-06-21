#!/usr/bin/env python3
"""
UNIT TEST — the de-priming verdict reader, and the verbatim-storage invariant.

The verdict reader (is_clean_verdict in the hook, _parse_verdict in the eval) is now
DETERMINISTIC: it reads the auditor's machine-readable verdict line — `CLAIRE-VERDICT: NEUTRAL`
or `CLAIRE-VERDICT: LEAN` — which the auditor is contracted to emit as its final line. We READ a
format WE define; we no longer GUESS the verdict out of free model prose. The prose-matching
approach this replaces accreted a string of edge-case bugs (markdown-fenced verdicts, "faint" /
"closer to neutral" qualifiers, the "tip" inside "multiple", the two readers disagreeing) — all
eliminated here by construction (2026-06-21).

We pin:
  1. SENTINEL — NEUTRAL clears, LEAN does not, ABSENT fails CLOSED (never false-cleans a lean).
  2. LAST occurrence wins (the auditor's final verdict, not a quote in its reasoning).
  3. HOOK == EVAL — both readers use the identical sentinel, so they agree by construction.
  4. The verbatim-storage invariant (the "receipt IS the brief" round-trip).
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rar = _load(os.path.join(REPO, "hooks", "record-audit-receipt.py"), "rar_hook")
is_clean_verdict = _rar.is_clean_verdict
stored_brief = _rar.stored_brief
_evals = _load(os.path.join(REPO, "tests", "evals", "run_evals.py"), "run_evals_mod")
eval_parse = _evals._parse_verdict  # returns "LEAN" / "NEUTRAL" / None

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- 1. the sentinel: NEUTRAL clears, LEAN / absent does not --------------------

@case
def test_sentinel_neutral_clears():
    """A response ending in the machine verdict line `CLAIRE-VERDICT: NEUTRAL` is clean."""
    r = "The brief states both options flatly; no steer.\n\nCLAIRE-VERDICT: NEUTRAL"
    assert is_clean_verdict(r) is True
    assert eval_parse(r) == "NEUTRAL"


@case
def test_sentinel_lean_does_not_clear():
    """`CLAIRE-VERDICT: LEAN` is not clean — even when the prose is full of the word neutral."""
    r = "The brief reads almost genuinely-neutral, but the framing tilts.\n\nCLAIRE-VERDICT: LEAN"
    assert is_clean_verdict(r) is False
    assert eval_parse(r) == "LEAN"


@case
def test_absent_sentinel_fails_closed():
    """BUG CLASS RETIRED: every prose shape that used to fool the heuristic reader now simply
    lacks the sentinel and FAILS CLOSED — no false-clean of a lean, no fragile heuristic. The
    inputs below are the exact ones the pre-release review used to break the old regexes; each is
    correctly NOT certified now (the live auditor would emit the explicit line for the real call)."""
    no_sentinel = [
        "GENUINELY-NEUTRAL — no, this leans toward cloud. The framing is one-sided.",
        "The competing read is the one thing that would move me toward GENUINELY-NEUTRAL.",
        "This drifts closer to genuinely-neutral but is not there yet.",
        "It reads as one of multiple, genuinely-neutral cues.",   # the "tip"-in-"multiple" trap
        "**Verdict**\n\n`LEAN-option-B`",                          # fenced verdict, an old false-clean
        "An asserted LEAN-x sits here.\nVerdict: GENUINELY-NEUTRAL",
        "",
        "I'm not sure how to read this.",
    ]
    for r in no_sentinel:
        assert is_clean_verdict(r) is False, "no sentinel must fail closed: %r" % r
        assert eval_parse(r) is None, "no sentinel must parse None: %r" % r


# --- 2. last occurrence wins ---------------------------------------------------

@case
def test_last_occurrence_wins():
    """The auditor may state the line then correct it; only its FINAL verdict line counts."""
    r = "CLAIRE-VERDICT: NEUTRAL\n(on reflection the closing beat tilts it)\nCLAIRE-VERDICT: LEAN"
    assert is_clean_verdict(r) is False
    assert eval_parse(r) == "LEAN"


# --- 3. tolerant of surrounding markdown / the genuinely- form ------------------

@case
def test_tolerates_markdown_and_genuinely_form():
    """Cosmetic list/blockquote/emphasis markers around the line, and the auditor's own
    `GENUINELY-NEUTRAL` vocabulary, do not change the read — the token is what matters."""
    assert is_clean_verdict("**CLAIRE-VERDICT: NEUTRAL**") is True
    assert is_clean_verdict("> CLAIRE-VERDICT: GENUINELY-NEUTRAL") is True
    assert is_clean_verdict("- CLAIRE-VERDICT: LEAN") is False
    assert eval_parse("**CLAIRE-VERDICT: NEUTRAL**") == "NEUTRAL"


# --- 4. hook and eval readers agree by construction ----------------------------

@case
def test_hook_and_eval_agree():
    """Both readers use the IDENTICAL sentinel, so they agree on every shape — the divergences
    the prose heuristics produced (one reader cleans while the other nags) cannot recur."""
    samples = [
        "x\nCLAIRE-VERDICT: NEUTRAL",
        "x\nCLAIRE-VERDICT: LEAN",
        "CLAIRE-VERDICT: NEUTRAL\nthen more\nCLAIRE-VERDICT: LEAN",
        "no verdict line at all, just prose mentioning genuinely-neutral and a lean",
        "**CLAIRE-VERDICT: GENUINELY-NEUTRAL**",
    ]
    for s in samples:
        assert is_clean_verdict(s) == (eval_parse(s) == "NEUTRAL"), "parsers disagree on %r" % s


# --- 5. verbatim-storage round-trip (the "receipt IS the brief" invariant) ------

@case
def test_stored_brief_is_verbatim_round_trip():
    """INVARIANT: stored_brief strips ONLY the [CLAIRE-RECEIPT:<nonce>] marker (and outer
    whitespace) — never normalises. What the auditor judged is what gets injected, byte for byte."""
    briefs = [
        "Simple neutral brief about two options.",
        "Your job is to find the strongest objection.\n\nSituation: Vendor-X vs Vendor-Y. Pick one.",
        "Mixed CASE and\ttabs\nand internal   spacing kept exactly.",
        "Brief with [brackets], symbols !@#$, and a 50KB-style repeat: " + ("X " * 40),
    ]
    for b in briefs:
        tagged = "[CLAIRE-RECEIPT:nonce_42]\n" + b
        assert stored_brief(tagged) == b.strip()
        assert "CLAIRE-RECEIPT" not in stored_brief(tagged)
    assert stored_brief("[CLAIRE-RECEIPT:x]\nThe VENDOR choice.") == "The VENDOR choice."


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
