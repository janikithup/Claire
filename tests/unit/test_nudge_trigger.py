#!/usr/bin/env python3
"""
UNIT TEST — discoverability nudge trigger precision.

The nudge is a UserPromptSubmit hook. When the user's prompt reads like a request
for a critique or an outside view, it surfaces a one-line marker that the toolkit
exists (so a fresh session doesn't forget to reach for it). The trigger is
DELIBERATELY TIGHT: a loose nudge becomes ambient noise and gets tuned out, which
fails silently. So this test has two equally important halves:

  - POSITIVE: known critique-shaped prompts MUST fire the nudge.
  - NEGATIVE: ordinary prompts (including ones with overlapping words) MUST NOT.

The negative half is the one that actually protects the product — a nudge that
fires on everything is worse than no nudge. Each negative case is a prompt that a
naive "contains the word attack/wrong/missing" matcher would wrongly fire on.

We drive the hook directly with stdin JSON and read its stdout: a fired nudge
prints a JSON object with additionalContext starting "[claire]"; a non-fire prints
nothing.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NUDGE = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "adv-nudge.py"))


def run_nudge(prompt):
    """Feed the nudge one user prompt; return its stdout text (isolated log dir)."""
    with tempfile.TemporaryDirectory() as td:
        copy = os.path.join(td, "adv-nudge.py")
        with open(NUDGE) as fh:
            src = fh.read()
        with open(copy, "w") as fh:
            fh.write(src)
        proc = subprocess.run(
            [sys.executable, copy],
            input=json.dumps({"prompt": prompt}),
            capture_output=True, text=True, timeout=15)
        return proc.stdout


def fires(prompt):
    out = run_nudge(prompt)
    if not out.strip():
        return False
    obj = json.loads(out)
    return obj["hookSpecificOutput"]["additionalContext"].startswith("[claire]")


# Prompts that MUST fire — genuine requests for an outside/critical read.
SHOULD_FIRE = [
    "What am I missing in this rollout plan?",
    "Play devil's advocate on my product strategy.",
    "Give me an outside view on this decision.",
    "Poke holes in this argument for me.",
    "Can you red-team this approach?",
    "Stress-test the assumptions behind this design.",
    "Talk me out of rewriting this module this way.",
    "What could go wrong with shipping this on Friday?",
    "Is this a good idea or am I fooling myself?",
    "Convince me I'm wrong about the methodology.",
]

# Prompts that MUST NOT fire — ordinary work, including overlapping vocabulary.
SHOULD_NOT_FIRE = [
    "Summarise these three interview transcripts.",
    "Fix the broken link in the README.",
    "The build is wrong, the path points at the old folder.",   # 'wrong' but not a critique request
    "Add a regression test for the parser.",
    "What is the deadline for the Q3 report?",
    "Translate this email into English.",
    "The threat-model attack surface section needs a citation.", # 'attack' in domain content, not a request
    "Explain what a PreToolUse hook does.",
    "Schedule the supervisor meeting for next Tuesday.",
    "Reformat data.csv to fix the column order.",
]


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_all_critique_prompts_fire():
    """BUG GUARDED: a trigger word gets dropped or the matcher breaks, so genuine
    critique requests stop surfacing the toolkit — it silently becomes undiscoverable."""
    missed = [p for p in SHOULD_FIRE if not fires(p)]
    assert not missed, "these critique-shaped prompts FAILED to fire the nudge:\n  - " + \
        "\n  - ".join(missed)


@case
def test_no_ordinary_prompt_fires():
    """BUG GUARDED: the trigger list is loosened (e.g. a bare common word added),
    so the nudge fires on routine work and becomes noise the user tunes out. This is
    the failure the 'tight by design' comment in the hook exists to prevent."""
    wrong = [p for p in SHOULD_NOT_FIRE if fires(p)]
    assert not wrong, "these ORDINARY prompts wrongly fired the nudge (noise):\n  - " + \
        "\n  - ".join(wrong)


@case
def test_case_insensitive():
    """BUG GUARDED: matching becomes case-sensitive, so a capitalised real request
    ('Devil's Advocate this') stops firing."""
    assert fires("DEVIL'S ADVOCATE this plan, please."), \
        "trigger matching must be case-insensitive"


@case
def test_empty_prompt_silent():
    """BUG GUARDED: an empty or missing prompt throws instead of failing open."""
    assert run_nudge("").strip() == "", "empty prompt must produce no nudge"


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from _runner import run
    sys.exit(run(CASES))
