#!/usr/bin/env python3
"""
UNIT TEST — event-log WIRING in the two hooks (0.6.0).

The shared logger (claire_log.py) is import-guarded inside each hook and records ONE
event per pipeline step to events.jsonl. These tests run the REAL hook scripts with
claire_log.py beside them (as in a real install) and CLAIRE_LOG_DIR pointed at a temp
dir, then assert the right event landed AND that logging never changes the hook's
decision or disrupts the dispatch.

Scope split: the log's privacy/spine guarantees (allowlist, binary verdict, fail-open,
bounded, concurrent-safe) are covered by test_claire_log.py. Here we check only that
the hooks CALL the logger correctly — the wiring — and stay fail-open when it is absent.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.abspath(os.path.join(HERE, "..", "..", "hooks"))
GATE = os.path.join(HOOKS, "adversarial-gate.py")
RECEIPT = os.path.join(HOOKS, "record-audit-receipt.py")
LOGGER = os.path.join(HOOKS, "claire_log.py")
TAG = "[DEPRIMED-BRIEF]"


def _normalise(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def _run(script_path, payload, receipts=None, env=None, with_logger=True):
    """Copy the hook (+ claire_log.py, as in a real install) into a temp dir, point
    CLAIRE_LOG_DIR at a sibling temp dir, run the hook on one stdin payload, and return
    (stdout, [event dicts]). with_logger=False omits claire_log.py to model an install
    where the logger is missing (the import-guard path)."""
    with tempfile.TemporaryDirectory() as td:
        shutil.copy(script_path, os.path.join(td, os.path.basename(script_path)))
        if with_logger:
            shutil.copy(LOGGER, os.path.join(td, "claire_log.py"))
        logdir = os.path.join(td, "log")
        if receipts:
            rdir = os.path.join(td, ".receipts")
            os.makedirs(rdir, exist_ok=True)
            now = time.time()
            for nonce, brief, age in receipts:
                with open(os.path.join(rdir, nonce + ".json"), "w") as fh:
                    json.dump({"ts": now - age, "nonce": nonce, "brief": brief}, fh)
        run_env = dict(os.environ)
        for var in ("CLAIRE_DEBUG", "CLAIRE_GATE_STRICT"):
            run_env.pop(var, None)
        run_env["CLAIRE_LOG_DIR"] = logdir
        if env:
            run_env.update(env)
        proc = subprocess.run(
            [sys.executable, os.path.join(td, os.path.basename(script_path))],
            input=json.dumps(payload), capture_output=True, text=True, timeout=15, env=run_env)
        events = []
        p = os.path.join(logdir, "events.jsonl")
        if os.path.exists(p):
            with open(p) as fh:
                events = [json.loads(l) for l in fh if l.strip()]
        return proc.stdout, events


# --- gate -> "pre" event -------------------------------------------------------

@case
def test_gate_logs_pre_event_on_remind():
    """BUG GUARDED: the gate takes a decision but records nothing, so the event log can
    never show the gate-decision mix. An adversarial dispatch with no tag must log exactly
    one 'pre' event naming the REMIND decision, the agent slot, and the dispatch id."""
    out, events = _run(GATE, {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                             "prompt": "Attack this rollout plan."},
                              "tool_use_id": "tu_abc123"})
    assert len(events) == 1, "gate must log exactly one pre event, got %d" % len(events)
    e = events[0]
    assert e["event"] == "pre", "gate event must be 'pre'"
    assert e["gate_decision"] == "REMIND"
    assert e["agent"] == "claire:failure-mode-attacker"
    assert e.get("dispatch_id") == "tu_abc123", "pre event must carry the harness tool_use_id"
    assert "brief_len" in e and isinstance(e["brief_len"], int)


@case
def test_gate_logs_pass_decision_with_receipt():
    """BUG GUARDED: a silent PASS records nothing, so the log undercounts the de-primed
    dispatches the gate let through. A matched receipt must still log a 'pre' event with
    gate_decision=PASS."""
    brief = "Neutral situation: a team plans X. Find failure modes."
    out, events = _run(GATE, {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                             "prompt": "[CLAIRE-RECEIPT:lg01] x"}},
                       receipts=[("lg01", brief, 10)])
    assert len(events) == 1
    assert events[0]["event"] == "pre" and events[0]["gate_decision"] == "PASS"


@case
def test_gate_logs_block_in_strict_mode():
    """BUG GUARDED: strict-mode blocks aren't distinguished in the log. A no-receipt
    dispatch under CLAIRE_GATE_STRICT must log gate_decision=BLOCK."""
    out, events = _run(GATE, {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                             "prompt": "Attack this plan."}},
                       env={"CLAIRE_GATE_STRICT": "1"})
    assert len(events) == 1 and events[0]["gate_decision"] == "BLOCK"


@case
def test_gate_logs_nothing_for_non_adversarial():
    """BUG GUARDED: the gate logs ordinary dispatches, flooding the log with non-Claire
    activity. A non-adversarial dispatch (early silent return) must log NOTHING."""
    out, events = _run(GATE, {"tool_input": {"subagent_type": "general-purpose",
                                             "prompt": "Summarise the three docs."}})
    assert events == [], "non-adversarial dispatch must log no event, got %r" % events


@case
def test_gate_logs_nothing_for_leak_auditor():
    """BUG GUARDED: the de-priming CHECKER itself gets a gate event, double-counting. The
    leak-auditor returns early and must log no 'pre' event."""
    out, events = _run(GATE, {"tool_input": {"subagent_type": "claire:brief-leak-auditor",
                                             "prompt": "Judge this brief about the [DEPRIMED-BRIEF] tag."}})
    assert events == [], "leak-auditor must not log a gate event, got %r" % events


@case
def test_gate_logging_absent_logger_is_fail_open():
    """BUG GUARDED (fail-open): if claire_log.py is missing from the install, the gate must
    still take its decision and emit normal output — never crash on a failed import."""
    out, events = _run(GATE, {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                             "prompt": "Attack this plan."}},
                       with_logger=False)
    assert out.strip(), "gate must still warn even with the logger absent"
    obj = json.loads(out)
    assert "CLAIRE GATE" in obj["hookSpecificOutput"]["additionalContext"]
    assert events == [], "no logger -> no events, but no crash"


@case
def test_gate_logging_does_not_change_the_decision():
    """BUG GUARDED: wiring the logger alters the gate's stdout/decision. With the logger
    present, the REMIND output must be the same shape as without it."""
    payload = {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                              "prompt": "Attack this plan."}}
    with_log, _ = _run(GATE, payload, with_logger=True)
    without_log, _ = _run(GATE, payload, with_logger=False)
    assert with_log == without_log, "logging must not change the gate's output"


@case
def test_event_carries_plugin_version_from_manifest():
    """BUG GUARDED: plugin_version is read from the install's .claude-plugin/plugin.json and is
    load-bearing for the reader's cross-version dedup. Run the hook from a realistic install
    layout (hooks/<hook>.py with a sibling ../.claude-plugin/plugin.json) and assert the version
    lands in the event. (The other harness runs hooks bare, where _plugin_version() -> None.)"""
    with tempfile.TemporaryDirectory() as td:
        hooks_dir = os.path.join(td, "hooks")
        os.makedirs(hooks_dir)
        os.makedirs(os.path.join(td, ".claude-plugin"))
        shutil.copy(GATE, os.path.join(hooks_dir, os.path.basename(GATE)))
        shutil.copy(LOGGER, os.path.join(hooks_dir, "claire_log.py"))
        with open(os.path.join(td, ".claude-plugin", "plugin.json"), "w") as fh:
            json.dump({"version": "9.9.9"}, fh)
        logdir = os.path.join(td, "log")
        run_env = dict(os.environ)
        for var in ("CLAIRE_DEBUG", "CLAIRE_GATE_STRICT"):
            run_env.pop(var, None)
        run_env["CLAIRE_LOG_DIR"] = logdir
        subprocess.run([sys.executable, os.path.join(hooks_dir, os.path.basename(GATE))],
                       input=json.dumps({"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                                        "prompt": "Attack this plan."},
                                         "tool_use_id": "tu_v"}),
                       capture_output=True, text=True, timeout=15, env=run_env)
        with open(os.path.join(logdir, "events.jsonl")) as fh:
            events = [json.loads(l) for l in fh if l.strip()]
    assert len(events) == 1 and events[0].get("plugin_version") == "9.9.9", \
        "pre event must carry the manifest version, got %r" % events


# --- receipt writer -> "post" event --------------------------------------------

@case
def test_receipt_logs_post_neutral_with_proof():
    """BUG GUARDED: a clean audit writes a receipt but logs no event, so the neutral-rate
    metric can't be computed. A GENUINELY-NEUTRAL verdict must log one 'post' event with
    verdict=neutral, proof_written=True, the agent slot, and the dispatch id."""
    out, events = _run(RECEIPT, {
        "tool_input": {"subagent_type": "claire:brief-leak-auditor",
                       "prompt": "[CLAIRE-RECEIPT:lp01]\nTwo vendors, one slot — which, and why? State the trade-offs."},
        "tool_response": "GENUINELY-NEUTRAL\nBoth stated flatly.",
        "tool_use_id": "tu_post1"})
    assert len(events) == 1, "auditor completion must log exactly one post event, got %d" % len(events)
    e = events[0]
    assert e["event"] == "post"
    assert e["verdict"] == "neutral"
    assert e["proof_written"] is True
    assert e["agent"] == "claire:brief-leak-auditor"
    assert e.get("dispatch_id") == "tu_post1"
    assert "brief_len" in e


@case
def test_receipt_logs_post_leaning_no_proof():
    """BUG GUARDED: a leaning audit (no receipt) logs nothing, so the log undercounts leans.
    A LEAN verdict must still log a 'post' event with verdict=leaning and proof_written=False.
    The lean DIRECTION must never appear (the logger binarises it — checked in test_claire_log)."""
    out, events = _run(RECEIPT, {
        "tool_input": {"subagent_type": "claire:brief-leak-auditor",
                       "prompt": "Obviously option A is wasteful; find problems with it."},
        "tool_response": "LEAN-B\nTells: 'obviously', 'wasteful'."})
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "post" and e["verdict"] == "leaning"
    assert e["proof_written"] is False


@case
def test_receipt_logs_nothing_for_non_auditor():
    """BUG GUARDED: any agent's clean-looking output logs a post event, polluting the audit
    metrics. Only brief-leak-auditor completions may log a post event."""
    out, events = _run(RECEIPT, {
        "tool_input": {"subagent_type": "failure-mode-attacker", "prompt": "Attack this plan."},
        "tool_response": "GENUINELY-NEUTRAL in places but risky."})
    assert events == [], "a non-auditor dispatch must log no post event, got %r" % events


@case
def test_receipt_logging_absent_logger_fail_open():
    """BUG GUARDED (fail-open): a missing logger must not stop the receipt writer or crash it.
    With claire_log absent, the hook still runs (writes its receipt) and logs no event."""
    out, events = _run(RECEIPT, {
        "tool_input": {"subagent_type": "claire:brief-leak-auditor", "prompt": "Two roads; which?"},
        "tool_response": "GENUINELY-NEUTRAL"}, with_logger=False)
    assert events == [], "no logger -> no events, but no crash"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
