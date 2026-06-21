#!/usr/bin/env python3
"""
claire de-priming RECEIPT writer — INJECTION design (>=0.8.0).

PostToolUse hook on the Agent/Task tool. FAIL-OPEN: any error => do nothing.

NOTE on registration: a plugin hooks.json PostToolUse hook does NOT fire on macOS
Desktop, so this writer is registered in ~/.claude/settings.json by setup-receipts.sh
(the same mechanism as 0.4.2+). It still reads the same Agent-result payload.

What it does: it watches brief-leak-auditor finish, and on a CLEAN verdict
(GENUINELY-NEUTRAL, no asserted lean) it stores the audited brief VERBATIM, keyed by
the orchestrator-chosen nonce carried in the auditor's prompt as [CLAIRE-RECEIPT:<nonce>].
The companion PreToolUse gate then looks that nonce up on the critic dispatch and
INJECTS the stored brief — so the critic reasons only from text the auditor cleared.

There is no fingerprint and no round-trip: the orchestrator already knows the nonce
(it chose it and put it on both the audit and the dispatch), so this writer never has
to communicate anything back. Receipt = .receipts/<nonce>.json : {ts, nonce, brief}.
They expire fast (TTL) and are pruned opportunistically; the dir is git-ignored.
"""
import sys, os, json, time, re, glob

# The orchestrator's de-priming nonce, carried in the auditor prompt and the critic dispatch.
RECEIPT_SENTINEL_RE = re.compile(r"\[CLAIRE-RECEIPT:([A-Za-z0-9_-]+)\]")

# --- verdict parsing: READ the auditor's machine verdict line, do not GUESS from prose --------
# The auditor's output contract is to END with a fixed sentinel line — `CLAIRE-VERDICT: NEUTRAL`
# or `CLAIRE-VERDICT: LEAN`. We READ that line; we do NOT reverse-engineer the verdict out of
# free model prose. The format is one WE define for the auditor, so parsing is deterministic —
# which is the whole point: a regex hunting a verdict inside random model output is a losing
# game that accreted edge-case bugs (markdown fences, "faint"/"closer to neutral" qualifiers,
# the innocent "tip" inside "multiple"). The sentinel ends that entire class of bug. Tolerant of
# an optional "genuinely-" before NEUTRAL; case-insensitive. NOT line-anchored: the token is
# distinctive enough that an accidental prose occurrence is implausible, last-occurrence wins so a
# quote in the analysis is superseded by the real final verdict line, and matching anywhere also
# survives a structured/JSON-escaped tool_response (where real newlines become literal "\n" and a
# `^`-anchor would miss the line). (Distinct from RECEIPT_SENTINEL_RE above, which carries the
# brief's nonce — this one carries the verdict.)
VERDICT_SENTINEL_RE = re.compile(
    r"(?i)claire-verdict[ \t]*[:=][ \t]*(?:genuinely[- ]?)?(neutral|lean)\b")


def is_clean_verdict(resp):
    """True iff the auditor's machine verdict line says NEUTRAL.

    The auditor MUST emit `CLAIRE-VERDICT: NEUTRAL` or `CLAIRE-VERDICT: LEAN` as its final line.
    We trust ONLY that line. Absent or LEAN -> NOT clean (fail closed: write no receipt, the gate
    nags). A missing/garbled verdict can therefore only ever false-NAG a clean brief (safe), never
    false-CLEAN a leaning one (the de-priming hole). Last occurrence wins — the auditor's final
    verdict, in case it restates the token while reasoning."""
    matches = VERDICT_SENTINEL_RE.findall(resp or "")
    return bool(matches) and matches[-1].lower() == "neutral"


AUDITOR_NAMES = {"brief-leak-auditor"}
RECEIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".receipts")
TTL_SECONDS = 2 * 60 * 60  # a receipt is valid for 2 hours, then ignored/pruned
DEBUG = os.environ.get("CLAIRE_DEBUG", "").strip() not in ("", "0", "false", "False")

# Event log (0.6.0) — OBSERVABILITY only. Import-guarded so a copy-one-file unit harness or
# an install missing the logger can't crash the writer.
try:
    import claire_log
except Exception:
    claire_log = None

_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))


def _plugin_version():
    try:
        with open(os.path.join(_HOOK_DIR, "..", ".claude-plugin", "plugin.json")) as fh:
            return json.load(fh).get("version")
    except Exception:
        return None


PLUGIN_VERSION = _plugin_version()


def record_post(clean, proof_written, agent, dispatch_id, brief_len):
    """Log one 'post' event per auditor completion. OBSERVABILITY only — the lean DIRECTION
    never persists (the logger binarises the verdict to neutral/leaning)."""
    if not claire_log:
        return
    try:
        claire_log.record(event="post", verdict=("neutral" if clean else "leaning"),
                          proof_written=proof_written, agent=agent,
                          dispatch_id=dispatch_id, plugin_version=PLUGIN_VERSION,
                          brief_len=brief_len)
    except Exception:
        pass


def emit_trace(msg):
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}
    print(json.dumps(out))


def stored_brief(prompt):
    """The brief to store/inject = the auditor's prompt with the [CLAIRE-RECEIPT:<nonce>]
    marker removed (cosmetic: the critic never sees the implementation token) and outer
    whitespace trimmed. Everything else — persona/attack-license, body, harness coda — is
    kept VERBATIM; there is no normalisation."""
    return RECEIPT_SENTINEL_RE.sub("", prompt or "").strip()


def prune(now):
    try:
        for path in glob.glob(os.path.join(RECEIPT_DIR, "*.json")):
            try:
                with open(path) as fh:
                    ts = json.load(fh).get("ts", 0)
                if now - ts > TTL_SECONDS:
                    os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


def response_text(data):
    """Pull the auditor's returned text out of the PostToolUse payload, stringifying
    defensively across harness shapes. Falls back to the whole payload MINUS tool_input so the
    audited brief's own wording can never be mistaken for the auditor's verdict."""
    parts = []
    for key in ("tool_response", "tool_result", "response", "output", "result"):
        if key in data:
            v = data[key]
            parts.append(v if isinstance(v, str) else json.dumps(v))
    if parts:
        return " ".join(parts)
    rest = {k: v for k, v in data.items() if k != "tool_input"}
    return json.dumps(rest)


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    ti = data.get("tool_input", {}) or {}

    atype = (ti.get("subagent_type") or ti.get("agentType") or ti.get("agent_type")
             or data.get("subagent_type") or "")
    atype_bare = str(atype).strip().split(":")[-1]
    if atype_bare not in AUDITOR_NAMES:
        return  # not the leak-auditor — nothing to record

    brief = ti.get("prompt") or ti.get("description") or ""
    resp = response_text(data)
    dispatch_id = data.get("tool_use_id")
    m = RECEIPT_SENTINEL_RE.search(brief)
    nonce = m.group(1) if m else None
    clean = is_clean_verdict(resp)
    to_store = stored_brief(brief)
    proof_written = False

    # A receipt is written ONLY for a clean verdict on a non-empty, nonce-tagged brief. No
    # nonce -> the orchestrator did not run the handshake; nothing to key a receipt by, so the
    # critic dispatch will (correctly) fail closed.
    if clean and nonce and to_store:
        now = time.time()
        prune(now)
        try:
            os.makedirs(RECEIPT_DIR, exist_ok=True)
            with open(os.path.join(RECEIPT_DIR, nonce + ".json"), "w") as fh:
                json.dump({"ts": now, "nonce": nonce, "brief": to_store}, fh)
            proof_written = True
        except Exception:
            pass

    record_post(clean, proof_written, atype, dispatch_id, len(to_store))

    if DEBUG:
        if not clean:
            saw = VERDICT_SENTINEL_RE.findall(resp or "")
            label = "LEAN" if (saw and saw[-1].lower() == "lean") else "no-verdict-line"
            emit_trace("[CLAIRE TRACE] receipt: verdict=%s · no receipt written" % label)
        elif not nonce:
            emit_trace("[CLAIRE TRACE] receipt: verdict=CLEAN · brief carried no "
                       "[CLAIRE-RECEIPT:<id>] marker, no receipt written")
        else:
            emit_trace("[CLAIRE TRACE] receipt: verdict=CLEAN · wrote nonce %s (brief len %d)"
                       % (nonce, len(to_store)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never disrupt a dispatch on a receipt-writer error
