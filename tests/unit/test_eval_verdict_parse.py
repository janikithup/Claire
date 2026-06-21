#!/usr/bin/env python3
"""
UNIT TEST — the eval runner's verdict reader (run_evals._parse_verdict).

It reads the auditor's machine verdict line (CLAIRE-VERDICT: NEUTRAL | LEAN), identical to the
receipt hook's is_clean_verdict. Deterministic, so unit-tested here. The prose-guessing parser
this replaced is gone — see test_verdict_parser.py and hooks/record-audit-receipt.py for why a
regex on random model output was the bug source (2026-06-21).
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_EVALS = os.path.abspath(os.path.join(HERE, "..", "evals", "run_evals.py"))
_spec = importlib.util.spec_from_file_location("run_evals_under_test", RUN_EVALS)
run_evals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_evals)
parse = run_evals._parse_verdict

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_sentinel_neutral_and_lean():
    """The machine verdict line parses to its token."""
    assert parse("Both options stated flatly.\nCLAIRE-VERDICT: NEUTRAL") == "NEUTRAL"
    assert parse("The framing tilts.\nCLAIRE-VERDICT: LEAN") == "LEAN"


@case
def test_absent_sentinel_is_none():
    """No machine verdict line -> None (fail-closed), whatever the surrounding prose says — the
    dismissive-opener and directional-mention shapes that broke the old parser are simply None."""
    assert parse("GENUINELY-NEUTRAL — no, it leans. A LEAN-x sits in the framing.") is None
    assert parse("the framing would only move toward genuinely-neutral if reworded") is None
    assert parse("") is None


@case
def test_last_occurrence_wins():
    """Only the final verdict line counts; an earlier restated line is superseded."""
    assert parse("CLAIRE-VERDICT: NEUTRAL\n(reconsidering)\nCLAIRE-VERDICT: LEAN") == "LEAN"


@case
def test_fake_dispatcher_lines_parse():
    """The --fake dispatcher now ends with the sentinel — must parse, so the eval smoke keeps working."""
    assert parse("leaks the answer\nCLAIRE-VERDICT: LEAN") == "LEAN"
    assert parse("states it flatly\nCLAIRE-VERDICT: NEUTRAL") == "NEUTRAL"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
