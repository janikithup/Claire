#!/usr/bin/env python3
"""
claire de-priming gate — INJECTION design (>=0.8.0).

PreToolUse hook on the Agent/Task tool. FAIL-OPEN by default: any error => allow
silently, so a gate bug can never block a real dispatch.

What this does, and why it replaces fingerprint-matching:
The de-priming spine is "the critic must never reason from text no leak-checker
cleared." Earlier versions PROVED that by fingerprint-matching the audited brief
against the dispatched one — brittle, because the orchestrator built the two texts
separately and the harness mutated one. This version removes the comparison: on a
clean leak-audit the companion PostToolUse hook stores the audited brief VERBATIM,
keyed by an orchestrator-chosen nonce carried as [CLAIRE-RECEIPT:<nonce>]. This gate
looks the nonce up and OVERWRITES the critic's whole prompt with the stored brief via
updatedInput. The critic reasons from exactly-what-was-audited by construction; an
orchestrator-supplied steer is discarded by the overwrite, and a dispatch with no
genuine receipt fails closed.

Decision tree:
  - not a de-priming dispatch                      -> silent pass
  - carries a nonce with a fresh receipt           -> INJECT the audited brief (allow)
  - carries a nonce but NO fresh receipt           -> NORECEIPT (deny by default; warn if soft)
  - de-priming dispatch with no nonce at all       -> REMIND  (deny by default; warn if soft)

The two failure states BLOCK by default (PreToolUse deny): a skipped or failed
de-priming hard-stops. This is safe to default on because detection is EXACT IDENTITY
— a claire:-namespaced critic, or a [CLAIRE-RECEIPT] marker — so a block can only ever
land on a genuine Claire dispatch, never on unrelated work. Set CLAIRE_GATE_STRICT=0
(or false) to soften both states to an advisory warning — the escape hatch for an
install that ever hits a false block. This is DISTINCT from the fail-open net above:
an ERROR inside the gate still allows silently; only a correctly-detected skipped
de-priming blocks.
"""
import sys, os, json, time, re, datetime

ADVERSARIAL_AGENTS = {
    "blank-slate-advisor", "failure-mode-attacker", "affected-actor-simulator",
    "probe-auditor", "dialectical-scout", "over-capture-triage-verifier",
}
# brief-leak-auditor is DELIBERATELY NOT listed: it is the de-priming CHECKER, not an
# adversary that needs a de-primed brief. Gating it would circularly demand a receipt on
# the very tool that earns receipts.
#
# Detection is EXACT IDENTITY ONLY — a claire:-namespaced adversary agent (by name), or a
# [CLAIRE-RECEIPT] marker. There is deliberately NO keyword/phrase matching on the prompt:
# a guesser that fired on words like "devil's advocate" both false-positived on unrelated
# work (the reason the gate could not safely block by default) and false-negatived on real
# critiques that missed the magic words. So the gate guards Claire's OWN critics by name,
# not the act of seeking criticism through any agent. (Keyword net removed in >=0.12.0 —
# "no more keyword logic"; the wider "route any outside-read request" gap is a separate
# concern, not this hook's job.)

# The de-priming handshake marker. The orchestrator puts the SAME nonce on the audit and
# the critic dispatch; the receipt is keyed by it. Charset is filename-safe by construction,
# so the nonce can index a receipt file directly with no path-traversal risk.
RECEIPT_SENTINEL_RE = re.compile(r"\[CLAIRE-RECEIPT:([A-Za-z0-9_-]+)\]")

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "gate-fire.log")
RECEIPT_DIR = os.path.join(HERE, ".receipts")
TTL_SECONDS = 2 * 60 * 60

# Block-by-default: a skipped/failed de-priming denies (PreToolUse). CLAIRE_GATE_STRICT=0
# (or false) softens both failure states to advisory warnings — the escape hatch. Unset or
# any other value => block. (Detection is exact-identity only, so a default block can never
# land on unrelated work — see the ADVERSARIAL_AGENTS note above.)
STRICT = os.environ.get("CLAIRE_GATE_STRICT", "").strip() not in ("0", "false", "False")
DEBUG = os.environ.get("CLAIRE_DEBUG", "").strip() not in ("", "0", "false", "False")

# Event log (0.6.0) — OBSERVABILITY only; never affects the decision. Import-guarded so a
# copy-one-file unit harness or an install missing the logger can't crash the gate.
try:
    import claire_log
except Exception:
    claire_log = None


def _plugin_version():
    try:
        with open(os.path.join(HERE, "..", ".claude-plugin", "plugin.json")) as fh:
            return json.load(fh).get("version")
    except Exception:
        return None


PLUGIN_VERSION = _plugin_version()


def log(line):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (ts, line))
    except Exception:
        pass


def extract_nonce(prompt):
    """The de-priming nonce carried in the prompt, or None. First match wins."""
    m = RECEIPT_SENTINEL_RE.search(prompt or "")
    return m.group(1) if m else None


def fresh_receipt(nonce):
    """The receipt dict for `nonce` if a fresh one exists, else None. Reads the single
    nonce-keyed file written by record-audit-receipt.py on a clean leak-audit."""
    if not nonce:
        return None
    try:
        with open(os.path.join(RECEIPT_DIR, nonce + ".json")) as fh:
            rec = json.load(fh)
    except Exception:
        return None
    if time.time() - rec.get("ts", 0) > TTL_SECONDS:
        return None
    brief = rec.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        return None
    return rec


def emit_allow(new_input):
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": new_input,
    }}
    print(json.dumps(out))


def emit_block(reason):
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}
    print(json.dumps(out))


def emit_context(msg):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}
    print(json.dumps(out))


NORECEIPT_MSG = (
    "[CLAIRE GATE] This adversarial dispatch carries a de-priming receipt id "
    "([CLAIRE-RECEIPT:...]) but NO fresh leak-audit receipt exists for it — meaning "
    "brief-leak-auditor did not return a clean verdict on a brief carrying this exact id "
    "(or the receipt expired). The id is self-attestation; it is the receipt that certifies "
    "de-priming. Run brief-leak-auditor on the brief — tagged with this id on its own line — "
    "fix any lean it names using its neutral rewrite, re-audit until clean, then re-dispatch "
    "with the same id. On a clean audit the gate INJECTS that exact audited brief into the "
    "critic, so the critic reasons only from text the checker cleared. Do NOT reply 'my brief "
    "is already neutral, moving on' — a producer cannot reliably judge their own brief's "
    "neutrality, which is the exact bypass this gate exists to stop."
)

REMIND_MSG = (
    "[CLAIRE GATE] This looks like an adversarial / outside-perspective dispatch, but it "
    "carries no [CLAIRE-RECEIPT:<id>] marker — the de-priming step may have been skipped.\n"
    "Before dispatching, apply the de-priming checklist (/claire:challenge Step 2):\n"
    "  - strip your own rationale and the answer you expect\n"
    "  - state every live option fairly (neutral framing, not just omitting your conclusion)\n"
    "  - de-jargon to plain language an outsider reads cold\n"
    "  - situation first, so the adversary forms its own read before any claim\n"
    "  - if this tests whether a specific behaviour fires, run claire:probe-auditor first\n"
    "Then run brief-leak-auditor on the brief tagged with a fresh [CLAIRE-RECEIPT:<id>], fix "
    "any lean it names with its neutral rewrite, show the user the NEUTRAL BRIEF, and "
    "re-dispatch with that id. The gate injects the audited brief only once a fresh receipt "
    "covers the id. Do NOT self-certify 'my brief is already neutral' — that is the bypass "
    "this gate exists to stop."
)


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    ti = data.get("tool_input", data) or {}

    atype = (ti.get("subagent_type") or ti.get("agentType") or ti.get("agent_type")
             or data.get("subagent_type") or "")
    prompt = ti.get("prompt") or ti.get("description") or ""
    atype_bare = str(atype).strip().split(":")[-1]
    atype_raw = str(atype).strip()

    # NEVER gate the de-priming CHECKER itself — authoritative over the phrase net below.
    if atype_bare == "brief-leak-auditor":
        return

    nonce = extract_nonce(prompt)
    # Only Claire's OWN adversarial agents (namespaced) count by type; a bare same-named
    # workspace agent is someone else's and is left alone.
    is_claire_adv = atype_bare in ADVERSARIAL_AGENTS and atype_raw.startswith("claire:")
    is_depriming = is_claire_adv or (nonce is not None)
    if not is_depriming:
        return  # not a Claire de-priming dispatch — silent pass

    agent = atype or "?"
    dispatch_id = data.get("tool_use_id")

    def record_pre(decision, brief_len=0):
        if not claire_log:
            return
        try:
            claire_log.record(event="pre", gate_decision=decision, agent=agent,
                              dispatch_id=dispatch_id, plugin_version=PLUGIN_VERSION,
                              brief_len=brief_len)
        except Exception:
            pass

    def trace(msg, decision, n_brief=0):
        if not DEBUG:
            return msg
        t = ("[CLAIRE TRACE] gate: agent=%s · decision=%s · nonce=%s · brief-len=%d · strict=%s"
             % (agent, decision, nonce or "none", n_brief, "on" if STRICT else "off"))
        return (msg + "\n\n" + t) if msg else t

    # Injection path: a nonce that resolves to a fresh, clean receipt.
    if nonce is not None:
        rec = fresh_receipt(nonce)
        if rec is not None:
            brief = rec["brief"]
            log("PASS agent=%s nonce=%s" % (agent, nonce))
            record_pre("PASS", len(brief))
            new_input = dict(ti)
            new_input["prompt"] = brief
            # Overwrite ONLY `prompt`. Keep every other field — including `description`, a
            # REQUIRED Agent/Task field. The critic reads only `prompt` (which we replace), so a
            # label left in `description` never reaches it; but DROPPING a required field makes the
            # harness reject the whole dispatch downstream of this hook's fail-open net — which
            # hard-blocked every receipted dispatch in 0.8.0/0.8.1. (A non-content label is no
            # de-priming channel, so there is nothing to gain by removing it.)
            emit_allow(new_input)  # inject the audited brief over the orchestrator's prompt
            return
        # nonce present but no fresh receipt -> fail closed
        log("NORECEIPT agent=%s nonce=%s (no fresh receipt)" % (agent, nonce))
        if STRICT:
            log("BLOCK agent=%s (strict, no receipt)" % agent)
            record_pre("BLOCK")
            emit_block(trace(NORECEIPT_MSG, "NORECEIPT/BLOCK"))
        else:
            record_pre("NORECEIPT")
            emit_context(trace(NORECEIPT_MSG, "NORECEIPT"))
        return

    # De-priming dispatch with no nonce at all (claire-typed or phrase-net) -> REMIND.
    log("REMIND agent=%s (no receipt id)" % agent)
    if STRICT:
        log("BLOCK agent=%s (strict, no id)" % agent)
        record_pre("BLOCK")
        emit_block(trace(REMIND_MSG, "REMIND/BLOCK"))
    else:
        record_pre("REMIND")
        emit_context(trace(REMIND_MSG, "REMIND"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never block a dispatch on a gate error
