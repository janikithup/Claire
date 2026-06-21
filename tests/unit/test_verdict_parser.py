#!/usr/bin/env python3
"""
UNIT TEST — the de-priming verdict parser and the verbatim-storage invariant.

These came out of a leak/bug-test brainstorm (2026-06-20). The verdict parser
(is_clean_verdict) is the one residual heuristic in the injection design — if it
FALSE-CLEANS a leaning verdict, the gate goes silent on a primed dispatch (a spine
hole); if it FALSE-NAGS a clean one, the product is unusable. So we pin it three ways:

  1. REAL-PROSE CORPUS — every verdict the live `claire:brief-leak-auditor` actually
     produced in a re-gate (tests/fixtures/auditor_prose_corpus.json) must be read
     correctly, forever. This guards against the parser drifting away from how the
     real auditor writes (synthetic tests can't catch that).
  2. PROPERTY/INVARIANTS — an asserted LEAN is never clean; a NEUTRAL that merely
     declines/quotes a LEAN is clean; no decisive verdict fails CLOSED.
  3. HOOK-vs-EVAL AGREEMENT — the live gate's parser (is_clean_verdict) and the eval
     harness's parser (_parse_verdict) must agree on every real sample, or the eval
     measures a different thing than the gate enforces (fold-in 2's risk).

Plus the verbatim-storage invariant (the "receipt IS the brief" round-trip).
"""
import importlib.util
import json
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

with open(os.path.join(REPO, "tests", "fixtures", "auditor_prose_corpus.json")) as fh:
    CORPUS = json.load(fh)

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- 1. real-auditor-prose corpus ----------------------------------------------

@case
def test_parser_reads_every_real_auditor_sample_correctly():
    """BUG GUARDED: the parser drifts from how the LIVE auditor actually writes its
    verdict, so a real clean pass gets nagged or a real lean is certified. Every verdict
    the live auditor produced in a re-gate must be read correctly."""
    assert len(CORPUS) >= 12, "corpus should carry the frozen live samples"
    misread = []
    for c in CORPUS:
        want_clean = (c["expressed_verdict"] == "NEUTRAL")
        if is_clean_verdict(c["response"]) != want_clean:
            misread.append("%s#%d (auditor said %s)" % (c["arm"], c["idx"], c["expressed_verdict"]))
    assert not misread, "parser misread real auditor verdicts: %s" % misread


# --- 2. property / invariants --------------------------------------------------

@case
def test_asserted_lean_is_never_clean():
    """INVARIANT: a response whose declared verdict is an asserted (non-declined) LEAN must
    parse NOT clean — including the dismissive-opener shape that once defeated the check."""
    leans = [
        "LEAN-option-a",
        "**Verdict:** LEAN-cloud",
        "Verdict — LEAN-x\nThe tells: 'obviously' loads it.",
        "GENUINELY-NEUTRAL — does not apply here. Verdict: LEAN-ship",   # dismissive opener
        "This is NOT genuinely-neutral. LEAN-b leaks the answer.",
    ]
    for r in leans:
        assert is_clean_verdict(r) is False, "an asserted LEAN must never be clean: %r" % r


@case
def test_neutral_that_declines_or_quotes_a_lean_is_clean():
    """INVARIANT (fold-in 2 — the false-warn this redesign targets): a NEUTRAL verdict that
    merely declines or quotes a LEAN example must parse CLEAN."""
    cleans = [
        "GENUINELY-NEUTRAL",
        "**Verdict** — GENUINELY-NEUTRAL\nBoth options stated flatly.",
        "Verdict: GENUINELY-NEUTRAL\nI considered a faint LEAN-one but declined.",
        "GENUINELY-NEUTRAL\n(a stricter auditor could call LEAN-two; I land neutral.)",
        "Verdict: GENUINELY-NEUTRAL — for reference, had it leaned I'd write e.g. LEAN-x; it does not.",
    ]
    for r in cleans:
        assert is_clean_verdict(r) is True, "a NEUTRAL declining/quoting a LEAN must be clean: %r" % r


@case
def test_no_decisive_verdict_fails_closed():
    """INVARIANT: no parseable verdict -> NOT clean (fail closed: write no receipt, gate nags).
    The dangerous failure is the inverse — defaulting an ambiguous response to clean."""
    for r in ["", "   ", "I'm not sure how to read this.", "The brief discusses two options at length.",
              "It mentions cleanly-framed trade-offs and leans on no one."]:
        assert is_clean_verdict(r) is False, "no decisive verdict must fail closed: %r" % r


@case
def test_fenced_faint_directional_verdict_is_lean_in_both_parsers():
    """BUG GUARDED (live dogfood 2026-06-21): a markdown-FENCED LEAN verdict whose body calls the
    lean 'faint' and whose recap says it 'would move me toward GENUINELY-NEUTRAL' was certified
    CLEAN — a leaning brief got a receipt and would have been injected into the critic. Three
    heuristic gaps aligned: the verdict-label regex did not span "**Verdict**\\n\\n`...`"; the
    'faint' declined-context window swallowed the real LEAN token; and the directional 'would move
    toward neutral' tripped the neutral fallback. Both parsers must read this LEAN, and must agree."""
    s = ("That is a detectable lean toward B. It's faint-to-moderate, but per my instructions a "
         "faint lean gets named.\n\n**Verdict**\n\n`LEAN-option-B`\n\n**The tells** ... B alone "
         "gets a built-in reassurance.\n\nRecap: the competing read is the one thing that would "
         "move me toward GENUINELY-NEUTRAL; but the asymmetric cost-handling is enough to name "
         "the faint lean rather than pass it.")
    assert is_clean_verdict(s) is False, "a fenced/faint/directional LEAN verdict must NOT be clean"
    assert eval_parse(s) == "LEAN", "the eval parser must also read it LEAN (parsers must agree)"


@case
def test_machine_readable_first_line_verdict_is_authoritative():
    """CONTRACT (>=2026-06-21): the auditor leads with a fixed `VERDICT: NEUTRAL` /
    `VERDICT: LEAN-<x>` line. Both parsers must trust that line over any prose below — a fixed
    token at a fixed position is the durable cure for the recurring prose-misreads. Parsers agree."""
    # First-line LEAN wins even when the body is thick with 'genuinely-neutral' mentions:
    lean = ("VERDICT: LEAN-option-two\n\nThe brief reads genuinely-neutral on a first skim, and a "
            "lazy reader would land on GENUINELY-NEUTRAL — but the framing leans.")
    assert is_clean_verdict(lean) is False
    assert eval_parse(lean) == "LEAN"
    # First-line NEUTRAL wins even when the body quotes a declined LEAN example:
    neutral = ("VERDICT: NEUTRAL\n\nA stricter auditor could call LEAN-option-one; I do not. "
               "Both sides are stated flatly.")
    assert is_clean_verdict(neutral) is True
    assert eval_parse(neutral) == "NEUTRAL"
    # Tolerant of leading markdown on the verdict line:
    assert is_clean_verdict("**VERDICT: LEAN-x**\nbody text") is False
    assert eval_parse("**VERDICT: NEUTRAL**\nbody text") == "NEUTRAL"


# --- 3. hook-vs-eval parser agreement ------------------------------------------

@case
def test_hook_and_eval_parsers_agree_on_real_corpus():
    """BUG GUARDED (fold-in 2): the eval harness's parser and the live gate's parser drift, so
    a green eval gives false confidence while the live gate mis-reads. They must agree on every
    real auditor sample."""
    disagree = []
    for c in CORPUS:
        hook_clean = is_clean_verdict(c["response"])
        eval_clean = (eval_parse(c["response"]) == "NEUTRAL")
        if hook_clean != eval_clean:
            disagree.append("%s#%d hook=%s eval=%s" % (c["arm"], c["idx"], hook_clean, eval_parse(c["response"])))
    assert not disagree, "hook and eval verdict parsers disagree on real prose: %s" % disagree


# --- 4. verbatim-storage round-trip (the "receipt IS the brief" invariant) ------

@case
def test_stored_brief_is_verbatim_round_trip():
    """INVARIANT: stored_brief strips ONLY the [CLAIRE-RECEIPT:<nonce>] marker (and outer
    whitespace) — never normalises. What the auditor judged is what gets injected, byte for
    byte: case, tabs, newlines, symbols all preserved."""
    briefs = [
        "Simple neutral brief about two options.",
        "Your job is to find the strongest objection.\n\nSituation: Vendor-X vs Vendor-Y. Pick one.",
        "Mixed CASE and\ttabs\nand internal   spacing kept exactly.",
        "Brief with [brackets], symbols !@#$, and a 50KB-style repeat: " + ("X " * 40),
    ]
    for b in briefs:
        tagged = "[CLAIRE-RECEIPT:nonce_42]\n" + b
        assert stored_brief(tagged) == b.strip(), "stored brief must equal the verbatim brief (marker + outer ws stripped)"
        assert "CLAIRE-RECEIPT" not in stored_brief(tagged), "the nonce marker must not survive into the stored brief"
    # explicit no-normalisation check: an uppercase brief stays uppercase
    assert "VENDOR" in stored_brief("[CLAIRE-RECEIPT:x]\nThe VENDOR choice.").upper()
    assert stored_brief("[CLAIRE-RECEIPT:x]\nThe VENDOR choice.") == "The VENDOR choice.", "no lowercasing"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
