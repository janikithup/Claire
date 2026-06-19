#!/usr/bin/env python3
"""
claire event logger — shared, fail-open, append-only.

Both Claire hooks (the de-priming gate and the receipt writer) import this to
record ONE structured event per pipeline step to a single per-machine JSON-lines
file. The log is OBSERVABILITY only — de-priming stats, gate-decision mix, and
(later) latency. It is a side-channel RECORD: it never affects a dispatch, the
gate's decision, whether a receipt is written, or the de-priming itself.

Hard guarantees this module enforces:

- FAIL-OPEN. Any error is swallowed; `record()` never raises into the hook.
- SPINE + PRIVACY by construction. A strict field ALLOWLIST *is* the schema:
  anything a caller passes that is not on the list is structurally never
  serialized, so the file can never hold brief text, a content hash, or a lean
  DIRECTION. `verdict` is collapsed to the binary neutral/leaning before write —
  the direction the brief leaned can never persist.
- VERSION-STABLE PATH. A fixed path that does NOT change across plugin versions
  and is NOT derived from __file__ (which would resolve to the version-specific
  plugin cache and fragment the log). One level below ~/.claude/. Overridable by
  the CLAIRE_LOG_DIR env var (for tests / advanced relocation), read at call time.
- SELF-INITIALIZING. Creates its directory and file on the first write — works
  even if the doctor/setup command was never run.
- CRASH-SAFE APPEND. One bounded (< MAX_LINE) line per call, written under a brief
  exclusive flock, so concurrent hook processes can never interleave a torn line.

Why a content-free correlation id (dispatch_id): callers pass the harness
`tool_use_id` (the id of the dispatch tool-call), which every concurrently-firing
cached version of a hook receives identically and which is NOT derived from the
brief. That lets the reader dedup duplicate writes and join pre/post events
without any brief-derived material ever touching the correlation path.
"""
import os
import json
import time
import fcntl

# The schema IS the privacy/spine guarantee. ONLY these keys are ever written.
# Deliberately absent and unrepresentable: brief text, any content hash, and the
# lean DIRECTION (only the binary `verdict` below can be stored).
ALLOWED_FIELDS = (
    "dispatch_id",     # content-free correlation id (harness tool_use_id); may be absent
    "plugin_version",  # which cached version emitted this (read-time dedup across versions)
    "event",           # "pre" (gate) | "post" (receipt)
    "ts",              # unix seconds (float); defaulted if not supplied
    "agent",           # the critic's namespaced agent type — a slot label, never content
    "gate_decision",   # pre only: PASS | REMIND | NORECEIPT | BLOCK
    "verdict",         # post only: BINARY "neutral" | "leaning" — never a direction
    "proof_written",   # post only: bool — did a receipt get written
    "brief_len",       # int char count — never the text
)

MAX_LINE = 512  # keep one serialized line well under any atomic-append ceiling


def _log_dir():
    # Fixed, version-stable, install-mode-agnostic. NEVER derived from __file__.
    return (os.environ.get("CLAIRE_LOG_DIR")
            or os.path.join(os.path.expanduser("~"), ".claude", "claire"))


def log_path():
    return os.path.join(_log_dir(), "events.jsonl")


def _binary_verdict(value):
    """Collapse any verdict to the binary neutral/leaning — the direction can never leak.
    Clean ('GENUINELY-NEUTRAL'/'neutral'/'clean') -> 'neutral'; anything else
    (a LEAN-<x> token, 'not-clean', a direction) -> 'leaning'. None stays None."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("neutral", "clean", "genuinely-neutral"):
        return "neutral"
    return "leaning"


def record(**fields):
    """Append one event line. FAIL-OPEN: never raises. Only ALLOWED_FIELDS are written;
    `verdict` is forced to the binary form; the line is bounded and lock-protected."""
    try:
        rec = {}
        for k in ALLOWED_FIELDS:
            v = fields.get(k)
            if v is not None:
                rec[k] = v
        rec["ts"] = fields.get("ts", time.time())
        if "verdict" in rec:
            rec["verdict"] = _binary_verdict(rec["verdict"])

        line = json.dumps(rec, separators=(",", ":"))
        if len(line) > MAX_LINE and "agent" in rec:
            rec["agent"] = str(rec["agent"])[:64]
            line = json.dumps(rec, separators=(",", ":"))
        if len(line) > MAX_LINE:
            return  # pathological; drop rather than risk a torn/oversized line

        data = (line + "\n").encode("utf-8")
        os.makedirs(_log_dir(), exist_ok=True)
        fd = os.open(log_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)   # brief; held only around the single write
            os.write(fd, data)
        finally:
            os.close(fd)                     # releases the flock
    except Exception:
        return  # fail-open: logging must never disrupt a dispatch
