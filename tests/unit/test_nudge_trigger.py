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


def run_nudge(prompt, claire_auto=None):
    """Feed the nudge one user prompt; return its stdout text (isolated log dir).

    `claire_auto` controls the CLAIRE_AUTO env var the hook sees: None strips it
    entirely (hermetic — an ambient CLAIRE_AUTO in the test runner's own env must
    not bleed into a case), a string sets it. This mirrors the receipt/gate test
    hermeticity fix for ambient CLAIRE_DEBUG (v0.5.1)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAIRE_AUTO"}
    if claire_auto is not None:
        env["CLAIRE_AUTO"] = claire_auto
    with tempfile.TemporaryDirectory() as td:
        copy = os.path.join(td, "adv-nudge.py")
        with open(NUDGE) as fh:
            src = fh.read()
        with open(copy, "w") as fh:
            fh.write(src)
        proc = subprocess.run(
            [sys.executable, copy],
            input=json.dumps({"prompt": prompt}),
            capture_output=True, text=True, timeout=15, env=env)
        return proc.stdout


def _context(out):
    if not out.strip():
        return ""
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def fires(prompt, claire_auto=None):
    """True iff the DISCOVERABILITY nudge fired ([claire] ... but not [claire:auto])."""
    ctx = _context(run_nudge(prompt, claire_auto=claire_auto))
    return ctx.startswith("[claire]") and not ctx.startswith("[claire:auto]")


def fires_auto(prompt, claire_auto="1"):
    """True iff the AUTONOMOUS-MODE standing instruction fired ([claire:auto])."""
    return _context(run_nudge(prompt, claire_auto=claire_auto)).startswith("[claire:auto]")


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


# ---------------------------------------------------------------------------
# CLAIRE_AUTO — autonomous-mode standing instruction.
# When CLAIRE_AUTO is on AND the prompt reads like the start of an autonomous /
# AFK run, the hook injects a standing instruction that Claire is a per-fork step
# for that run (the automation of "I told the session to use Claire on every
# judgement call before going AFK"). Two gates by design: the flag AND the
# autonomous lexicon, so a flag left on cannot bleed Claire into interactive work.
# ---------------------------------------------------------------------------

# Autonomous-run kickoffs that MUST arm auto-mode when the flag is on.
AUTO_SHOULD_FIRE = [
    "Scan and fix the dashboard issues.",
    "Work the queue and don't stop to check in.",
    "Clear the backlog of open tasks.",
    "/autoloop",
    "Go through the list and knock these out.",
    "Run unattended while I'm away and handle the queue.",
]

# Ordinary interactive prompts that MUST NOT arm auto-mode even with the flag set —
# the flag alone is not enough; the prompt must also read as an autonomous run.
AUTO_SHOULD_NOT_FIRE = [
    "Summarise these three interview transcripts.",
    "Fix the broken link in the README.",
    "What is the deadline for the Q3 report?",
    "Explain what a PreToolUse hook does.",
]


@case
def test_auto_mode_fires_on_autonomous_kickoff_with_flag():
    """BUG GUARDED: CLAIRE_AUTO is set for an AFK run but the standing instruction
    never injects, so the run silently has no Claire — the exact thing the mode exists
    to automate."""
    missed = [p for p in AUTO_SHOULD_FIRE if not fires_auto(p)]
    assert not missed, "auto-mode failed to arm on these autonomous kickoffs:\n  - " + \
        "\n  - ".join(missed)


@case
def test_auto_mode_silent_without_flag():
    """BUG GUARDED: the autonomous instruction injects even when the maintainer did
    NOT arm auto-mode — turning an opt-in run-mode into always-on, breaking the
    'nothing fires until you invoke her' promise."""
    leaked = [p for p in AUTO_SHOULD_FIRE if _context(run_nudge(p)).startswith("[claire:auto]")]
    assert not leaked, "auto-mode armed with NO CLAIRE_AUTO flag set:\n  - " + \
        "\n  - ".join(leaked)


@case
def test_auto_mode_silent_on_interactive_even_with_flag():
    """BUG GUARDED: a CLAIRE_AUTO flag left on bleeds the autonomous instruction into
    ordinary interactive prompts (noise + identity violation). The lexicon gate is
    what prevents this."""
    wrong = [p for p in AUTO_SHOULD_NOT_FIRE if fires_auto(p)]
    assert not wrong, "auto-mode wrongly armed on interactive prompts (flag on):\n  - " + \
        "\n  - ".join(wrong)


@case
def test_discoverability_nudge_unaffected_by_flag():
    """BUG GUARDED: turning on CLAIRE_AUTO breaks the ordinary discoverability nudge
    on a critique-shaped (non-autonomous) prompt — the two paths must be independent."""
    assert fires("What am I missing in this rollout plan?", claire_auto="1"), \
        "discoverability nudge must still fire on a critique prompt when CLAIRE_AUTO is on"


@case
def test_auto_mode_supersedes_discoverability_when_both_match():
    """BUG GUARDED: a prompt that is BOTH an autonomous kickoff and critique-shaped
    (flag on) must inject the standing auto instruction and SUPPRESS the one-line
    discoverability nudge — a branch-order regression would surface the wrong one."""
    p = "Work the queue and poke holes in my plan."
    assert fires_auto(p), "auto-mode must win when both an auto-trigger and a critique-trigger match"
    assert not fires(p, claire_auto="1"), "discoverability nudge must be suppressed once auto-mode arms"


@case
def test_auto_flag_falsey_values_are_off():
    """BUG GUARDED: CLAIRE_AUTO=0/false/empty is treated as ON, so a disabled flag
    still arms auto-mode (must parse identically to CLAIRE_GATE_STRICT/CLAIRE_DEBUG)."""
    p = "Work the queue and knock these out."
    for off in ("", "0", "false", "False"):
        assert not fires_auto(p, claire_auto=off), \
            "CLAIRE_AUTO=%r must be OFF, but auto-mode armed" % off


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from _runner import run
    sys.exit(run(CASES))
