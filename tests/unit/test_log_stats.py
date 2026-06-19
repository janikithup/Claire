#!/usr/bin/env python3
"""
UNIT TEST — event-log stats reader (hooks/claire_log_stats.py).

The reader turns events.jsonl into a plain summary: the gate-decision mix, the
neutral-vs-leaning rate, the proof-written rate, and per-critic counts. Its load-bearing
job is to DEDUP the N-version double-write: the desktop hook-glob runs every cached
version's hook per dispatch, so one real dispatch emits N events sharing a dispatch_id
but differing in plugin_version. Counting must collapse those to one. Malformed lines
must be survivable, and events lacking a correlation id must be handled honestly (kept,
counted, reported — never silently merged).
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODPATH = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "claire_log_stats.py"))
_spec = importlib.util.spec_from_file_location("claire_log_stats", MODPATH)
stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats)

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def _write(lines):
    """Write a list of dicts (or raw strings) as events.jsonl; return its path."""
    d = tempfile.mkdtemp(prefix="claire_stats_test_")
    p = os.path.join(d, "events.jsonl")
    with open(p, "w") as fh:
        for ln in lines:
            fh.write((ln if isinstance(ln, str) else json.dumps(ln)) + "\n")
    return p


@case
def test_dedup_collapses_n_version_double_write():
    """BUG GUARDED: the N-version hook-glob makes one dispatch emit one event per cached
    version (same dispatch_id, different plugin_version). The reader must collapse those to
    ONE logical event per (dispatch_id, event) — otherwise every metric is multiplied by the
    number of installed versions."""
    p = _write([
        {"event": "pre", "dispatch_id": "tu1", "plugin_version": "0.6.0", "gate_decision": "PASS"},
        {"event": "pre", "dispatch_id": "tu1", "plugin_version": "0.5.1", "gate_decision": "PASS"},
        {"event": "pre", "dispatch_id": "tu1", "plugin_version": "0.4.6", "gate_decision": "PASS"},
    ])
    s = stats.summarize(p)
    assert s["total_raw"] == 3
    assert s["total_dedup"] == 1, "three cached versions of one dispatch must dedup to one"
    assert s["gate"]["PASS"] == 1


@case
def test_gate_decision_mix():
    """BUG GUARDED: the gate-decision mix is the headline metric (a high REMIND/NORECEIPT
    share means de-priming is being skipped). It must count distinct dispatches per decision."""
    p = _write([
        {"event": "pre", "dispatch_id": "a", "gate_decision": "PASS"},
        {"event": "pre", "dispatch_id": "b", "gate_decision": "REMIND"},
        {"event": "pre", "dispatch_id": "c", "gate_decision": "NORECEIPT"},
        {"event": "pre", "dispatch_id": "d", "gate_decision": "PASS"},
    ])
    s = stats.summarize(p)
    assert s["gate"]["PASS"] == 2 and s["gate"]["REMIND"] == 1 and s["gate"]["NORECEIPT"] == 1


@case
def test_verdict_and_proof_rates():
    """BUG GUARDED: the neutral-vs-leaning rate and proof-written rate come from post events.
    They must count deduped post events, never the lean direction (already binarised upstream)."""
    p = _write([
        {"event": "post", "dispatch_id": "a", "verdict": "neutral", "proof_written": True},
        {"event": "post", "dispatch_id": "b", "verdict": "leaning", "proof_written": False},
        {"event": "post", "dispatch_id": "c", "verdict": "neutral", "proof_written": True},
    ])
    s = stats.summarize(p)
    assert s["verdict"]["neutral"] == 2 and s["verdict"]["leaning"] == 1
    assert s["proof_written"]["yes"] == 2 and s["proof_written"]["no"] == 1


@case
def test_malformed_lines_are_skipped_not_fatal():
    """BUG GUARDED: one corrupt line (a torn write, a manual edit) must not crash the reader
    or drop the whole file. Bad lines are counted as skipped; good lines still parse."""
    p = _write([
        {"event": "pre", "dispatch_id": "a", "gate_decision": "PASS"},
        "this is not json {{{",
        {"event": "pre", "dispatch_id": "b", "gate_decision": "REMIND"},
    ])
    s = stats.summarize(p)
    assert s["skipped"] == 1
    assert s["total_dedup"] == 2


@case
def test_events_without_correlation_id_are_kept_and_reported():
    """BUG GUARDED: if a harness never supplies a tool_use_id, events can't be cross-version
    deduped — and silently merging them (e.g. on event alone) would erase real dispatches.
    Such events must be kept individually and their count surfaced, so the reader is honest
    about what it could not dedup."""
    p = _write([
        {"event": "pre", "gate_decision": "PASS"},
        {"event": "pre", "gate_decision": "PASS"},
    ])
    s = stats.summarize(p)
    assert s["no_correlation_id"] == 2, "events without an id must be counted as un-dedupable"
    assert s["total_dedup"] == 2, "without an id they cannot be collapsed — both are kept"


@case
def test_per_agent_counts():
    """BUG GUARDED: per-critic-slot counts let the user see which critics they lean on. They
    must count deduped events by agent."""
    p = _write([
        {"event": "pre", "dispatch_id": "a", "agent": "claire:failure-mode-attacker", "gate_decision": "PASS"},
        {"event": "pre", "dispatch_id": "a", "plugin_version": "x", "agent": "claire:failure-mode-attacker", "gate_decision": "PASS"},
        {"event": "pre", "dispatch_id": "b", "agent": "claire:blank-slate-advisor", "gate_decision": "REMIND"},
    ])
    s = stats.summarize(p)
    assert s["per_agent"]["claire:failure-mode-attacker"] == 1
    assert s["per_agent"]["claire:blank-slate-advisor"] == 1


@case
def test_missing_file_is_empty_summary():
    """BUG GUARDED: a machine that has never run a critic has no log; the reader must return
    a clean empty summary, not raise."""
    s = stats.summarize("/no/such/events.jsonl")
    assert s["total_raw"] == 0 and s["total_dedup"] == 0


@case
def test_format_report_is_plain_text():
    """BUG GUARDED: the report must be human-readable plain text (the project is maintained by
    non-coders). format_report returns a string naming the headline numbers."""
    p = _write([
        {"event": "pre", "dispatch_id": "a", "gate_decision": "PASS"},
        {"event": "post", "dispatch_id": "a", "verdict": "neutral", "proof_written": True},
    ])
    out = stats.format_report(stats.summarize(p))
    assert isinstance(out, str) and "PASS" in out


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
