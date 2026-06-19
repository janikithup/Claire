#!/usr/bin/env python3
"""
claire event-log stats reader.

Turns the per-machine event log (claire_log.py's events.jsonl) into a plain summary:
the gate-decision mix, the neutral-vs-leaning audit rate, the proof-written rate, and
per-critic counts. Read-only; it never writes the log.

The load-bearing job is DEDUP. On Claude Desktop the plugin hook-glob runs EVERY cached
version's hook per dispatch, so one real dispatch emits N events that share a content-free
`dispatch_id` (the harness tool-call id) but differ in `plugin_version`. Counting raw lines
would multiply every metric by the number of installed versions. So we collapse to one
logical event per (dispatch_id, event). Events that carry no dispatch_id cannot be
correlated — silently merging them on `event` alone would erase real dispatches — so they
are kept individually and their count is surfaced, keeping the reader honest about what it
could not dedup. Stdlib only; safe to run on a bare python3.
"""
import json
import os
import sys
from collections import Counter


def default_log_path():
    return (os.path.join(os.environ.get("CLAIRE_LOG_DIR")
                         or os.path.join(os.path.expanduser("~"), ".claude", "claire"),
                         "events.jsonl"))


def load_events(path):
    """Read events.jsonl -> (events, skipped_count). A malformed line is counted, not fatal —
    a torn concurrent write or a hand-edit must never crash the reader or drop the file."""
    events, skipped = [], 0
    if not path or not os.path.exists(path):
        return events, skipped
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        events.append(obj)
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
    except Exception:
        pass
    return events, skipped


def dedup(events):
    """Collapse the N-version double-write to one logical event per (dispatch_id, event).
    Returns (deduped_events, no_correlation_id_count). Events without a dispatch_id can't be
    correlated, so they are kept as-is and counted — never merged on `event` alone."""
    seen = set()
    deduped = []
    no_id = 0
    for e in events:
        did = e.get("dispatch_id")
        if did is None:
            deduped.append(e)
            no_id += 1
            continue
        key = (did, e.get("event"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped, no_id


def summarize(path):
    """Build the plain summary dict from events.jsonl at `path`."""
    events, skipped = load_events(path)
    deduped, no_id = dedup(events)
    pre = [e for e in deduped if e.get("event") == "pre"]
    post = [e for e in deduped if e.get("event") == "post"]
    gate = Counter(e.get("gate_decision") for e in pre if e.get("gate_decision"))
    verdict = Counter(e.get("verdict") for e in post if e.get("verdict"))
    proof = Counter(bool(e.get("proof_written")) for e in post)
    per_agent = Counter(e.get("agent") for e in deduped if e.get("agent"))
    versions = Counter(e.get("plugin_version") for e in events if e.get("plugin_version"))
    return {
        "total_raw": len(events),
        "total_dedup": len(deduped),
        "skipped": skipped,
        "no_correlation_id": no_id,
        "gate": dict(gate),
        "verdict": dict(verdict),
        "proof_written": {"yes": proof.get(True, 0), "no": proof.get(False, 0)},
        "per_agent": dict(per_agent),
        "versions_seen": dict(versions),
    }


def _pct(n, total):
    return ("%d%%" % round(100 * n / total)) if total else "0%"


def format_report(s):
    """Render the summary as plain, human-readable text — the project is maintained by
    non-coders, so this reads at a glance, no JSON."""
    L = []
    L.append("=== claire event log ===")
    if s["total_raw"] == 0:
        L.append("no events logged yet on this machine.")
        return "\n".join(L)
    L.append("%d events (%d after de-duplicating the per-version double-write)"
             % (s["total_raw"], s["total_dedup"]))
    if s["skipped"]:
        L.append("  %d unparseable line(s) skipped" % s["skipped"])
    if s["no_correlation_id"]:
        L.append("  %d event(s) had no correlation id — not de-duplicated (counted as-is)"
                 % s["no_correlation_id"])

    gate = s["gate"]
    gtot = sum(gate.values())
    if gtot:
        L.append("")
        L.append("GATE decisions (de-primed dispatches let through vs caught):")
        for d in ("PASS", "REMIND", "NORECEIPT", "BLOCK"):
            if gate.get(d):
                note = "  (de-primed)" if d == "PASS" else "  (de-priming skipped, caught)"
                L.append("  %-9s %3d  %4s%s" % (d, gate[d], _pct(gate[d], gtot), note))
        skipped_share = gtot - gate.get("PASS", 0)
        if skipped_share:
            L.append("  -> de-priming-skipped share: %s   (high = investigate)"
                     % _pct(skipped_share, gtot))

    post_tot = sum(s["verdict"].values())
    if post_tot:
        L.append("")
        L.append("AUDITS (leak-auditor verdicts):")
        L.append("  neutral %d  /  leaning %d   (%s neutral)"
                 % (s["verdict"].get("neutral", 0), s["verdict"].get("leaning", 0),
                    _pct(s["verdict"].get("neutral", 0), post_tot)))
        pw = s["proof_written"]
        L.append("  receipts written: %d yes / %d no" % (pw["yes"], pw["no"]))

    if s["per_agent"]:
        L.append("")
        L.append("by critic:")
        for agent, n in sorted(s["per_agent"].items(), key=lambda kv: -kv[1]):
            L.append("  %3d  %s" % (n, agent))

    if len(s["versions_seen"]) > 1:
        L.append("")
        L.append("note: %d plugin versions are firing hooks (cached duplicates) — %s"
                 % (len(s["versions_seen"]), ", ".join(sorted(s["versions_seen"]))))
    return "\n".join(L)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else default_log_path()
    print(format_report(summarize(path)))
