#!/usr/bin/env python3
"""
UNIT TEST — de-priming gate behavioural contract.

The gate is a PreToolUse hook on the Agent/Task tool. Its job: when an
ADVERSARIAL subagent is being dispatched WITHOUT the [DEPRIMED-BRIEF] tag in its
prompt, inject a non-blocking reminder (so the de-priming step can't be silently
skipped). When the tag IS present, pass through silently. Non-adversarial
dispatches always pass through silently.

This is deterministic plumbing: same stdin JSON in, same decision out. We drive
the hook script directly by feeding it crafted stdin and reading what it does:

  - REMIND  -> the script prints a JSON object whose additionalContext mentions
              the gate, AND writes a "REMIND" line to gate-fire.log
  - PASS    -> the script prints NOTHING on stdout, AND writes a "PASS" line
  - SILENT  -> the script prints NOTHING and writes NO log line

Each assertion below would FAIL if a specific bug came back. The bug each one
guards is named in its docstring.

The hook under test is the shipped gate in hooks/adversarial-gate.py — the
executable spec these tests pin the gate's behaviour against.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "adversarial-gate.py"))


def run_gate(payload):
    """Drive the gate with one stdin JSON payload in an isolated log dir.

    Returns (stdout_text, log_text). We copy the gate into a throwaway dir so
    its sibling gate-fire.log never pollutes the real one and tests stay
    independent of each other and of prior runs.
    """
    with tempfile.TemporaryDirectory() as td:
        gate_copy = os.path.join(td, "adversarial-gate.py")
        with open(GATE) as fh:
            src = fh.read()
        with open(gate_copy, "w") as fh:
            fh.write(src)
        proc = subprocess.run(
            [sys.executable, gate_copy],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
        )
        log_path = os.path.join(td, "gate-fire.log")
        log_text = ""
        if os.path.exists(log_path):
            with open(log_path) as fh:
                log_text = fh.read()
        return proc.stdout, log_text


# --- helpers -----------------------------------------------------------------

def _dispatch(subagent_type, prompt):
    """Shape a PreToolUse payload the way the harness delivers an Agent dispatch."""
    return {"tool_input": {"subagent_type": subagent_type, "prompt": prompt}}


# --- the tests ---------------------------------------------------------------

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_adversarial_no_tag_fires_remind():
    """BUG GUARDED: gate goes silent on a bare adversarial dispatch, so the
    de-priming step is skipped unnoticed. The whole product depends on this firing."""
    out, log = run_gate(_dispatch("failure-mode-attacker",
                                  "Attack this rollout plan and find failure modes."))
    assert out.strip(), "expected the gate to emit additionalContext, got empty stdout"
    obj = json.loads(out)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "CLAIRE GATE" in ctx, "reminder text missing the gate banner"
    assert "[DEPRIMED-BRIEF]" in ctx, "reminder must name the tag the user has to add"
    assert "REMIND" in log, "gate must log a REMIND line for the stats tooling"


@case
def test_adversarial_with_tag_passes():
    """BUG GUARDED: a properly de-primed brief still gets nagged (false positive),
    training the user to ignore the gate. Tag present anywhere => silent pass + PASS log."""
    out, log = run_gate(_dispatch(
        "failure-mode-attacker",
        "[DEPRIMED-BRIEF]\nNeutral situation: a team plans X. Find failure modes."))
    assert out.strip() == "", "tag present must produce NO stdout (silent pass), got: %r" % out
    assert "PASS" in log, "a passed dispatch must still log a PASS line"
    assert "REMIND" not in log, "must NOT also log REMIND when the tag is present"


@case
def test_tag_not_required_on_first_line():
    """BUG GUARDED: an earlier version demanded the tag be the literal first line,
    so an Explore/Plan persona-preamble dispatch (preamble first, tag after) got a
    false reminder. The tag must be accepted ANYWHERE in the prompt."""
    out, log = run_gate(_dispatch(
        "blank-slate-advisor",
        "You are Claire, a blank-slate advisor.\n\n[DEPRIMED-BRIEF]\nSituation: ..."))
    assert out.strip() == "", "tag after a preamble must still pass silently"
    assert "PASS" in log


@case
def test_namespaced_agent_name_matches():
    """BUG GUARDED: live dispatches carry the namespaced name (e.g.
    claire:blank-slate-advisor). If the gate only matched bare names, the prefix
    would make the name-match silently never fire. It must strip the namespace."""
    out, log = run_gate(_dispatch("claire:failure-mode-attacker",
                                  "Find what breaks in this plan."))
    assert out.strip(), "namespaced adversarial agent must still trigger the gate"
    assert "REMIND" in log


@case
def test_non_adversarial_dispatch_silent():
    """BUG GUARDED: the gate nags on ordinary subagent dispatches, becoming ambient
    noise the user tunes out. A routine non-adversarial dispatch must be fully silent
    (no stdout, no log line)."""
    out, log = run_gate(_dispatch("general-purpose",
                                  "Summarise the three documents in the project folder."))
    assert out.strip() == "", "non-adversarial dispatch must produce no stdout"
    assert log.strip() == "", "non-adversarial dispatch must produce no log line"


@case
def test_phrase_backstop_fires():
    """BUG GUARDED: the secondary phrase net (for when the agent-type field is
    missing) stops working, so a dispatch whose only adversarial signal is in the
    prompt text slips through un-reminded."""
    out, log = run_gate({"tool_input": {
        "prompt": "Play devil's advocate against this conclusion."}})
    assert out.strip(), "devil's-advocate phrasing must trigger the gate even with no agent-type"
    assert "REMIND" in log


@case
def test_fail_open_on_garbage_stdin():
    """BUG GUARDED: a gate error blocks a real dispatch. The gate is FAIL-OPEN —
    any error must exit silently with no stdout (so the dispatch is allowed)."""
    with tempfile.TemporaryDirectory() as td:
        gate_copy = os.path.join(td, "adversarial-gate.py")
        with open(GATE) as fh:
            src = fh.read()
        with open(gate_copy, "w") as fh:
            fh.write(src)
        proc = subprocess.run(
            [sys.executable, gate_copy],
            input="this is not json {{{",
            capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, "fail-open: must exit 0 even on garbage input"
    assert proc.stdout.strip() == "", "fail-open: must emit no blocking output on error"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
