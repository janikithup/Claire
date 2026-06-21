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

# --- verdict parsing (fold-in 2: anchor to the verdict LINE, tolerant of its shape) ---------
# A lean verdict token: uppercase LEAN-<option>. Case-sensitive so the auditor's lowercase
# prose ("a real lean", "leans neither way") is never mistaken for the verdict token.
LEAN_TOKEN = re.compile(r"(?<![A-Za-z])LEAN-\w")
NEUTRAL_RE = re.compile(r"genuinely-neutral", re.IGNORECASE)
# Tolerant verdict-LABEL line match (mirrors tests/evals/run_evals.py): catches
# "**Verdict** — GENUINELY-NEUTRAL", "Verdict: LEAN-x", "Verdict\nNEUTRAL", and the
# markdown-FENCED "**Verdict**\n\n`LEAN-x`" — without requiring a brittle literal "VERDICT:"
# prefix the live auditor is not contracted to emit. The window spans up to 12 non-word chars
# (markdown stars, fences, colons, newlines) so a fenced verdict is not missed and mis-read by
# the fuzzy backstops below (2026-06-21: a fenced LEAN was certified clean exactly this way).
VERDICT_LABEL_RE = re.compile(
    r"verdict\b\W{0,12}(?:genuinely[- ]?)?(LEAN|NEUTRAL)", re.IGNORECASE)
# Machine-readable FIRST-LINE verdict (the auditor's output contract, >=2026-06-21):
# "VERDICT: NEUTRAL" / "VERDICT: LEAN-<x>" as the opening line. A fixed token at a fixed
# position is authoritative — it ends the prose-parsing guesswork that let fenced/qualified
# verdicts be mis-read. Tolerant of leading markdown; anchored at the start via re.match.
FIRST_LINE_VERDICT_RE = re.compile(r"[*_`>~\s]*verdict\b\s*[:\-—]\s*(NEUTRAL|LEAN)\b", re.IGNORECASE)
# Contexts in which a LEAN-<x> token is NOT an asserted verdict: the auditor discussing a
# lean it declined, or quoting one as an example. Used by the asserted-LEAN backstop so a
# clean pass that merely mentions a lean is not misread as leaning.
DECLINED_LEAN_RE = re.compile(
    r"(?:declin|considered|faint|reject|hypothetical|err[- ]?toward|tempt|not\s+a\s+real|"
    r"no\s+real\s+lean|weigh|might\s+call|could\s+call|nearly|example|e\.g\.|such\s+as|"
    r"or\s+lean)", re.IGNORECASE)


def _asserted_lean(text):
    """True if `text` contains a LEAN-<x> token that is NOT in a declined/example context."""
    for m in LEAN_TOKEN.finditer(text):
        ctx = text[max(0, m.start() - 48):m.start()].lower()
        if not DECLINED_LEAN_RE.search(ctx):
            return True
    return False


def is_clean_verdict(resp):
    """True iff the auditor PASSED the brief (verdict NEUTRAL, no asserted lean).

    Verdict-LINE anchored, conservative toward de-priming:
      1. If a verdict LABEL line is present, it is authoritative: LEAN -> not clean;
         NEUTRAL -> clean UNLESS an asserted LEAN appears AFTER it (a reversal).
      2. No label line: an asserted LEAN anywhere -> not clean.
      3. Else: a non-negated GENUINELY-NEUTRAL -> clean.
      4. Nothing decisive -> NOT clean (fail-closed: write no receipt, the gate nags).
    Erring toward "not clean" on ambiguity is the safe direction."""
    # 0. Machine-readable first-line verdict (the auditor's output contract) is authoritative
    #    when present — a fixed token at a fixed position, no prose to misread.
    fl = FIRST_LINE_VERDICT_RE.match(resp or "")
    if fl:
        return fl.group(1).upper() == "NEUTRAL"
    m = VERDICT_LABEL_RE.search(resp)
    if m:
        if m.group(1).upper() == "LEAN":
            return False
        return not _asserted_lean(resp[m.end():])  # NEUTRAL line, clean unless reversed after
    if _asserted_lean(resp):
        return False
    for nm in NEUTRAL_RE.finditer(resp):
        before = resp[max(0, nm.start() - 24):nm.start()].lower()
        # Skip a GENUINELY-NEUTRAL that is negated ("not ... neutral") OR merely directional /
        # hypothetical ("would move me toward GENUINELY-NEUTRAL", "closer to neutral") — neither
        # is the asserted verdict (2026-06-21: a directional mention false-cleaned a LEAN).
        if re.search(r"(?:not|n't|toward|towards|move\w*|would|closer|nearer|approach\w*|"
                     r"shift\w*|drift\w*|tip\w*|push\w*)\b[\s\W]*$", before):
            continue
        return True
    return False


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
            label = "LEAN" if _asserted_lean(resp) or (VERDICT_LABEL_RE.search(resp) and
                     VERDICT_LABEL_RE.search(resp).group(1).upper() == "LEAN") else "not-clean"
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
