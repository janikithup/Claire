#!/usr/bin/env python3
"""
UNIT TEST — the eval runner's verdict parser (run_evals._parse_verdict).

The leak-auditor's REAL output, when it flags a lean, often OPENS by dismissing
neutrality ("GENUINELY-NEUTRAL - does not apply here ... Verdict: LEAN-x"). A naive
parser that grabs the first NEUTRAL/LEAN token reads that as NEUTRAL and mis-scores a
LEAN fixture as a pass — the same class of hole found in the receipt hook's
is_clean_verdict (2026-06-19, from observing live auditor output). This pins the eval
parser against the auditor's actual verdict vocabulary.

The parser is plumbing (deterministic), so it is unit-tested here, not eval'd.
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
def test_lean_with_dismissive_neutral_opener_parses_lean():
    """BUG GUARDED (eval analog of the receipt enforcement hole): a LEAN verdict that
    OPENS 'GENUINELY-NEUTRAL - does not apply here ... Verdict: LEAN-x' must parse as
    LEAN, not be hijacked by the leading clean token."""
    resp = ("GENUINELY-NEUTRAL — does not apply here. This brief carries a clear lean.\n"
            "**Verdict:** LEAN-the-plan-is-sound")
    assert parse(resp) == "LEAN", "dismissive-neutral opener must not be read as NEUTRAL"


@case
def test_negated_neutral_then_lean_parses_lean():
    """BUG GUARDED: 'NOT genuinely-neutral. LEAN-A' contains the clean token verbatim; a
    first-token grab wrongly reads NEUTRAL. The asserted lean must win."""
    assert parse("This is NOT genuinely-neutral. LEAN-A: 'obviously' loads the answer.") == "LEAN"


@case
def test_genuinely_neutral_parses_neutral():
    """A real clean verdict must still parse NEUTRAL."""
    assert parse("**Verdict:** GENUINELY-NEUTRAL\nThe brief states both options flatly.") == "NEUTRAL"


@case
def test_declined_lean_in_clean_pass_parses_neutral():
    """A clean pass that merely DISCUSSES a declined lean must still parse NEUTRAL."""
    resp = "**Verdict:** GENUINELY-NEUTRAL\nI considered a faint LEAN-One but am declining."
    assert parse(resp) == "NEUTRAL"


@case
def test_fake_dispatcher_verdict_lines_still_parse():
    """The deterministic --fake dispatcher emits 'VERDICT: LEAN/NEUTRAL' — must still parse,
    so the eval smoke test keeps working."""
    assert parse("VERDICT: LEAN\nThis brief leaks the author's expected answer.") == "LEAN"
    assert parse("VERDICT: NEUTRAL\nThe brief states the situation without a conclusion.") == "NEUTRAL"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
