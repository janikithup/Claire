#!/usr/bin/env python3
"""
claire de-priming gate.

PreToolUse hook on the Agent/Task tool. FAIL-OPEN by default: any error => allow
silently, so a gate bug can never block a real dispatch.

What changed in v0.2.0 — the gate no longer trusts a self-typed tag.
Previously: an adversarial dispatch carrying the literal [DEPRIMED-BRIEF] tag
passed silently. But the main agent types that tag itself, so it could skip the
leak-check and still silence the gate — honour-system enforcement an anchored
main rationalises straight past.

Now: the tag alone buys NOTHING. Silence requires a *receipt* — written by the
companion PostToolUse hook (record-audit-receipt.py) only when brief-leak-auditor
actually returned a clean verdict on this exact brief. The decision tree:

  - not an adversarial dispatch              -> silent pass
  - adversarial, brief has a matching receipt -> PASS  (silent)
  - adversarial, tag present but NO receipt  -> NORECEIPT warning (the skip is now
                                                visible; the tag can't hide it)
  - adversarial, no tag at all               -> REMIND (de-priming checklist)

Set the env var CLAIRE_GATE_STRICT=1 to make the two failure states BLOCK the
dispatch (PreToolUse deny) instead of warn — recommended on your own machines,
off by default so a public install can never hard-block on a gate quirk.
"""
import sys, os, json, time, re, glob, datetime

ADVERSARIAL_AGENTS = {
    "blank-slate-advisor", "failure-mode-attacker", "affected-actor-simulator",
    "probe-auditor", "dialectical-scout", "over-capture-triage-verifier",
}
# brief-leak-auditor is DELIBERATELY NOT listed: it is the de-priming CHECKER (it
# reads a brief to judge whether it leaks the author's lean), not an adversary that
# needs a de-primed brief. Gating it would circularly demand a [DEPRIMED-BRIEF] tag on
# the very tool that verifies de-priming. Any agent-list sync check should treat this
# one agents/ file as an intentional non-member, not a missing entry.

# Secondary net for the rare case where the agent-type field does not carry the
# custom agent's name (harness-dependent). Deliberately NARROW — only markers
# that essentially never appear in ordinary, non-adversarial briefs.
ADVERSARIAL_PHRASES = (
    "devil's advocate", "steel-man", "steelman", "de-prime", "deprime",
    "blank-slate advisor",
)
# Match phrases only at WORD boundaries, so "deprime" does not fire inside
# "deprimed" (e.g. a brief that quotes the [DEPRIMED-BRIEF] tag or discusses
# de-priming) — that false trigger is exactly what gated the leak-auditor itself.
ADVERSARIAL_PHRASE_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(re.escape(p) for p in ADVERSARIAL_PHRASES) + r")(?![a-z])"
)

TAG = "[DEPRIMED-BRIEF]"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "gate-fire.log")
RECEIPT_DIR = os.path.join(HERE, ".receipts")
TTL_SECONDS = 2 * 60 * 60
# A receipt must cover most of the dispatched brief, so auditing a tiny decoy and
# dispatching a big leaky brief does not match. But a short brief legitimately
# carries trailing boilerplate (e.g. the attack-license line the skill appends),
# which would drag a pure ratio below the floor — so we ALSO accept a bounded
# trailing remainder when the audited text is a prefix and is itself substantial.
#
# SPINE NOTE (0.5.3) — DO NOT "fix" the large-artifact false-block by excluding the
# pasted artifact from this coverage denominator. It is tempting: a genuine brief that
# inlines a big document drew a NORECEIPT, and marking the artifact + dropping it from
# coverage would silence that. But the artifact reaches the critic; excluding it from
# coverage WITHOUT auditing it lets a lean hidden inside the artifact ride to the critic
# unchecked — the same shape as the decoy attack this floor exists to stop. The coverage
# requirement is precisely what forces the WHOLE dispatched brief (artifact included) to
# have been leak-audited. The real fix lives in the skill: audit the fully-assembled
# brief, byte-for-byte what the critic receives. The gate stays strict on purpose.
MIN_COVERAGE = 0.6
TRAILING_SLACK = 240            # chars of boilerplate allowed after a prefix-matched brief
MIN_RECEIPT_LEN_FOR_SLACK = 60  # the slack path needs a real brief, not a tiny decoy prefix
STRICT = os.environ.get("CLAIRE_GATE_STRICT", "").strip() not in ("", "0", "false", "False")
# CLAIRE_DEBUG=1 surfaces an under-the-hood trace of every Claire dispatch — the gate's
# decision, whether a receipt matched, the brief-region size — so a builder can watch the
# de-priming work (see the brief next to the verdict). OFF by default; pure visibility, it
# NEVER changes the decision the gate takes. Parsed exactly like CLAIRE_GATE_STRICT above.
DEBUG = os.environ.get("CLAIRE_DEBUG", "").strip() not in ("", "0", "false", "False")

# Event log (0.6.0) — OBSERVABILITY only; never affects the decision below. Import-guarded
# so an install missing the shared logger (or the copy-one-file unit harness) can't crash
# the gate on a failed import — claire_log stays None and logging silently no-ops.
try:
    import claire_log
except Exception:
    claire_log = None


def _plugin_version():
    """Best-effort version of THIS cached build (hooks/../.claude-plugin/plugin.json), so the
    stats reader can dedup the N-version double-write the desktop hook-glob produces. -> None
    on any error (fail-open)."""
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


def normalise(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


# See record-audit-receipt.py: the harness appends a standing-invitation coda to the
# subagent prompt AFTER this PreToolUse gate reads it but BEFORE the PostToolUse
# receipt writer does, so the receipt fingerprints brief+coda while this gate sees
# brief-only. Both hooks cut at the coda marker so each fingerprints the brief ALONE,
# whichever stage the harness happens to inject at. No-op when no coda is present.
CODA_MARKERS = ("[standing invitation]",)


def strip_coda(norm_text):
    cut = len(norm_text)
    for m in CODA_MARKERS:
        i = norm_text.find(m)
        if i != -1:
            cut = min(cut, i)
    return norm_text[:cut].strip()


def brief_region(prompt):
    """The portion of the critic prompt that should BE the audited brief: everything
    after the FIRST tag. If there is no tag, the whole prompt is the candidate region.

    The first [DEPRIMED-BRIEF] is the delimiter the orchestrator places, with any
    preamble (attack-license, persona) before it and the brief — artifact included —
    after it. We deliberately take the FIRST occurrence, not the last: a pasted artifact
    can itself QUOTE the tag (Claire reviewing Claire's own docs is the common case), and
    rfind would then truncate the region to the tail after that embedded quote, falsely
    warning NORECEIPT on a brief that was correctly audited as assembled. Everything after
    the first tag is the brief, embedded tag-text and all — which is exactly what the
    receipt fingerprints (the auditor sees the brief body, embedded tag included)."""
    idx = prompt.find(TAG)
    region = prompt[idx + len(TAG):] if idx != -1 else prompt
    return strip_coda(normalise(region))


def has_matching_receipt(region_norm):
    """True if a fresh receipt's text is contained in the dispatched brief region and
    covers most of it. Reads the receipts written by record-audit-receipt.py."""
    if not region_norm:
        return False
    now = time.time()
    try:
        paths = glob.glob(os.path.join(RECEIPT_DIR, "*.json"))
    except Exception:
        return False
    for path in paths:
        try:
            with open(path) as fh:
                rec = json.load(fh)
        except Exception:
            continue
        if now - rec.get("ts", 0) > TTL_SECONDS:
            continue
        if _covers(rec.get("text", ""), region_norm):
            return True
    return False


def _covers(text, region_norm):
    """Does an audited brief `text` legitimately account for the dispatched region?

    Two ways to qualify, both requiring the audited text to actually appear in the
    region:
      (a) it covers >=60% of the region (the normal case — region IS the brief), or
      (b) it is a substantial PREFIX of the region with only a bounded remainder
          after it (the brief, then a short boilerplate suffix like the attack-
          license). The prefix + min-length conditions stop a tiny neutral decoy
          from certifying a big leaky brief tacked on after it."""
    if not text or text not in region_norm:
        return False
    if len(text) >= MIN_COVERAGE * len(region_norm):
        return True
    if (region_norm.startswith(text)
            and len(text) >= MIN_RECEIPT_LEN_FOR_SLACK
            and (len(region_norm) - len(text)) <= TRAILING_SLACK):
        return True
    return False


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


def debug_trace(agent, decision, matched, region_len):
    """One-line under-the-hood trace, emitted only when CLAIRE_DEBUG is on. Visibility
    only — it reports the decision the gate already took; it never alters it."""
    return ("[CLAIRE TRACE] gate: agent=%s · decision=%s · receipt=%s · "
            "brief-region-len=%d · strict=%s"
            % (agent or "?", decision, "matched" if matched else "none",
               region_len, "on" if STRICT else "off"))


NORECEIPT_MSG = (
    "[CLAIRE GATE] This adversarial dispatch carries the " + TAG + " tag but NO leak-audit "
    "receipt exists for this brief — meaning brief-leak-auditor did not actually run on this "
    "exact text (or the text changed after it ran). The tag is self-attestation; it is the "
    "receipt, not the tag, that certifies de-priming. Run brief-leak-auditor on the brief now "
    "(it reads only the brief and judges whether it leaks your lean); fix any lean it names "
    "using ITS neutral rewrite; re-audit until clean; then re-dispatch. "
    "MOST COMMON cause when your brief really is neutral: you assembled it from parts — a "
    "framing PLUS a pasted document/artifact — and audited the framing alone, then inlined the "
    "document afterwards. Audit the FINAL assembled brief, byte-for-byte what you are sending "
    "here, artifact included; the document reaches the critic, so a lean hidden inside it is "
    "exactly what the check must see, and a brief whose pasted bulk was never audited is "
    "correctly flagged. Do NOT reply 'my brief "
    "is already neutral, moving on' — a producer cannot reliably judge their own brief's "
    "neutrality, which is the exact bypass this gate exists to stop."
)

REMIND_MSG = (
    "[CLAIRE GATE] This looks like an adversarial / outside-perspective dispatch, but the "
    + TAG + " tag is absent — the de-priming step may have been skipped.\n"
    "Before dispatching, apply the de-priming checklist (/claire:challenge Step 2):\n"
    "  - strip your own rationale and the answer you expect\n"
    "  - state every live option fairly (neutral framing, not just omitting your conclusion)\n"
    "  - de-jargon to plain language an outsider reads cold\n"
    "  - situation first, so the adversary forms its own read before any claim\n"
    "  - if this tests whether a specific behaviour fires, run probe-auditor on the brief first\n"
    "Then run brief-leak-auditor on the brief, fix any lean it names with its neutral rewrite, "
    "show the user the NEUTRAL BRIEF block, and re-dispatch with " + TAG + " present. The gate "
    "passes silently only once a leak-audit receipt exists for the brief — the tag alone does "
    "not satisfy it. Do NOT self-certify 'my brief is already neutral' — that is the bypass "
    "this gate exists to stop."
)


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    ti = data.get("tool_input", data) or {}

    atype = (ti.get("subagent_type") or ti.get("agentType") or ti.get("agent_type")
             or data.get("subagent_type") or "")
    prompt = ti.get("prompt") or ti.get("description") or ""
    pl = prompt.lower()

    atype_bare = str(atype).strip().split(":")[-1]

    # NEVER gate the de-priming CHECKER itself. brief-leak-auditor reads a brief to
    # judge its neutrality — gating it would circularly demand a receipt on the very
    # tool that earns receipts, and its brief routinely quotes the tag and the word
    # "de-priming", which would otherwise trip the phrase backstop. This name check
    # is authoritative over the phrase net below.
    if atype_bare == "brief-leak-auditor":
        return

    # Only gate Claire's OWN adversarial agents — match on the NAMESPACED form
    # (claire:<name>), so a different tool's, or the workspace's own, same-named
    # local agent (e.g. a project's own failure-mode-attacker) is not swept in.
    # Plugin dispatches carry the namespaced agent-type; a bare same-named agent is
    # someone else's. The phrase net stays as the backstop for a missing agent-type.
    # (If a harness ever fails to namespace Claire's own agents, the gate would not
    # fire — /claire:doctor's live self-test is the per-machine detector for that.)
    atype_raw = str(atype).strip()
    is_claire_adv = atype_bare in ADVERSARIAL_AGENTS and atype_raw.startswith("claire:")
    is_adv = is_claire_adv or bool(ADVERSARIAL_PHRASE_RE.search(pl))
    if not is_adv:
        return  # not Claire's adversarial dispatch — silent pass

    # Compute the receipt match ONCE: it drives both the decision below and the debug
    # trace, so the trace can never disagree with the call the gate actually makes.
    region = brief_region(prompt)
    matched = has_matching_receipt(region)
    agent = atype or "?"

    def with_trace(msg, decision):
        """Append the debug trace to a message when CLAIRE_DEBUG is on; otherwise return
        the message untouched. The decision is already made — this only adds visibility."""
        if not DEBUG:
            return msg
        trace = debug_trace(agent, decision, matched, len(region))
        return (msg + "\n\n" + trace) if msg else trace

    # Content-free correlation id: the harness dispatch tool-call id, identical across every
    # concurrently-firing cached version, never brief-derived — lets the reader dedup the
    # N-version double-write and join this 'pre' event to its 'post' audit. Absent -> omitted.
    dispatch_id = data.get("tool_use_id")

    def record_pre(decision):
        """Log one 'pre' event for this gate decision. OBSERVABILITY only — fail-open, and
        never affects the decision already taken above."""
        if not claire_log:
            return
        try:
            claire_log.record(event="pre", gate_decision=decision, agent=agent,
                              dispatch_id=dispatch_id, plugin_version=PLUGIN_VERSION,
                              brief_len=len(region))
        except Exception:
            pass

    # The receipt — not the tag — is what certifies de-priming.
    if matched:
        log("PASS agent=%s" % agent)
        record_pre("PASS")
        if DEBUG:
            emit_context(with_trace("", "PASS"))  # silent in normal use; trace only in debug
        return  # audited-and-clean brief — pass through

    tag_present = TAG in prompt
    if tag_present:
        log("NORECEIPT agent=%s (tag, no receipt)" % agent)
        if STRICT:
            log("BLOCK agent=%s (strict, no receipt)" % agent)
            record_pre("BLOCK")
            emit_block(with_trace(NORECEIPT_MSG, "NORECEIPT/BLOCK"))
        else:
            record_pre("NORECEIPT")
            emit_context(with_trace(NORECEIPT_MSG, "NORECEIPT"))
        return

    log("REMIND agent=%s (no %s)" % (agent, TAG))
    if STRICT:
        log("BLOCK agent=%s (strict, no tag)" % agent)
        record_pre("BLOCK")
        emit_block(with_trace(REMIND_MSG, "REMIND/BLOCK"))
    else:
        record_pre("REMIND")
        emit_context(with_trace(REMIND_MSG, "REMIND"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never block a dispatch on a gate error
