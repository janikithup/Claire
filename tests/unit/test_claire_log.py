#!/usr/bin/env python3
"""
UNIT TEST — claire_log shared event logger (hooks/claire_log.py).

The logger is the privacy + spine guard for the event log. A strict field
ALLOWLIST is the schema, so brief text, a content hash, or a lean DIRECTION are
structurally unrepresentable; the verdict is collapsed to a binary; writes are
self-initializing, fail-open, bounded, and lock-protected. Each test names the bug
it guards. Driven by importing the shipped module directly and pointing its log at
a temp dir via CLAIRE_LOG_DIR (read at call time).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODPATH = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "claire_log.py"))
_spec = importlib.util.spec_from_file_location("claire_log", MODPATH)
claire_log = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claire_log)

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def _fresh():
    """Fresh temp log dir; sets CLAIRE_LOG_DIR and returns the events.jsonl path."""
    d = tempfile.mkdtemp(prefix="claire_log_test_")
    os.environ["CLAIRE_LOG_DIR"] = d
    return os.path.join(d, "events.jsonl")


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


@case
def test_only_allowlisted_fields_written():
    """BUG GUARDED: a hook passes an off-schema key and it lands in the durable log. Only
    allowlisted fields may be serialized; anything else is structurally dropped."""
    p = _fresh()
    claire_log.record(event="pre", agent="claire:failure-mode-attacker",
                      gate_decision="REMIND", brief_len=42,
                      brief_text="THE SECRET BRIEF", lean_direction="toward approval")
    recs = _lines(p)
    assert len(recs) == 1
    r = recs[0]
    assert r.get("event") == "pre" and r.get("gate_decision") == "REMIND"
    assert "brief_text" not in r and "lean_direction" not in r
    assert "brief_len" in r and "agent" in r


@case
def test_brief_text_can_never_reach_the_file():
    """BUG GUARDED (privacy): brief CONTENT must never reach the durable log, whatever a
    caller passes. Scan raw bytes, not just parsed keys."""
    p = _fresh()
    claire_log.record(event="post", verdict="neutral", brief_len=10,
                      brief="launch the dashboard on Friday", text="topsecret")
    with open(p) as f:
        raw = f.read()
    assert "launch the dashboard" not in raw and "topsecret" not in raw


@case
def test_verdict_collapses_to_binary():
    """BUG GUARDED (spine): the lean DIRECTION must never persist. Any LEAN-<x> collapses
    to 'leaning'; a clean verdict to 'neutral' — no direction survives."""
    p = _fresh()
    claire_log.record(event="post", verdict="LEAN-toward-shipping", brief_len=5)
    claire_log.record(event="post", verdict="GENUINELY-NEUTRAL", brief_len=5)
    assert [r["verdict"] for r in _lines(p)] == ["leaning", "neutral"]


@case
def test_self_initializes_on_first_write():
    """BUG GUARDED: logging assumed a setup step created the dir/file → silent data loss.
    The first write must create a missing directory tree and file."""
    d = tempfile.mkdtemp(prefix="claire_log_test_")
    nested = os.path.join(d, "does", "not", "exist", "claire")
    os.environ["CLAIRE_LOG_DIR"] = nested
    claire_log.record(event="pre", gate_decision="PASS", brief_len=1)
    assert os.path.exists(os.path.join(nested, "events.jsonl"))


@case
def test_fail_open_on_unwritable_location():
    """BUG GUARDED (fail-open): a logging error must never raise into the hook. Point the
    dir under a regular file so makedirs/open fail — record must return silently."""
    f = tempfile.NamedTemporaryFile(prefix="claire_block_", delete=False)
    f.write(b"x")
    f.close()
    os.environ["CLAIRE_LOG_DIR"] = os.path.join(f.name, "under_a_file")
    claire_log.record(event="pre", gate_decision="PASS", brief_len=1)  # must not raise


@case
def test_line_is_bounded_and_valid():
    """BUG GUARDED: an unbounded field grows a line past the atomic-append ceiling and
    risks a torn/interleaved line. Lines stay bounded and remain valid JSON."""
    p = _fresh()
    claire_log.record(event="pre", gate_decision="PASS", agent="x" * 5000, brief_len=1)
    with open(p) as f:
        line = f.readline()
    assert len(line) <= claire_log.MAX_LINE + 1
    json.loads(line)


@case
def test_concurrent_writers_no_torn_lines():
    """BUG GUARDED: concurrent hook processes appending interleave into corrupt JSON.
    Six processes each write 50 lines; every line must parse and the count be exact."""
    p = _fresh()
    d = os.environ["CLAIRE_LOG_DIR"]
    prog = (
        "import importlib.util,os;"
        "os.environ['CLAIRE_LOG_DIR']=%r;"
        "s=importlib.util.spec_from_file_location('cl',%r);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "[m.record(event='pre',gate_decision='PASS',agent='abcdefghij',brief_len=i) for i in range(50)]"
    ) % (d, MODPATH)
    procs = [subprocess.Popen([sys.executable, "-c", prog]) for _ in range(6)]
    for pr in procs:
        pr.wait()
    recs = _lines(p)  # parses each line — raises if any is torn
    assert len(recs) == 6 * 50, "expected 300 intact lines, got %d" % len(recs)


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
