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
MIN_COVERAGE = 0.6
TRAILING_SLACK = 240            # chars of boilerplate allowed after a prefix-matched brief
MIN_RECEIPT_LEN_FOR_SLACK = 60  # the slack path needs a real brief, not a tiny decoy prefix
STRICT = os.environ.get("CLAIRE_GATE_STRICT", "").strip() not in ("", "0", "false", "False")


def log(line):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (ts, line))
    except Exception:
        pass


def normalise(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def brief_region(prompt):
    """The portion of the critic prompt that should BE the audited brief: everything
    after the last tag. If there is no tag, the whole prompt is the candidate region."""
    idx = prompt.rfind(TAG)
    region = prompt[idx + len(TAG):] if idx != -1 else prompt
    return normalise(region)


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


NORECEIPT_MSG = (
    "[CLAIRE GATE] This adversarial dispatch carries the " + TAG + " tag but NO leak-audit "
    "receipt exists for this brief — meaning brief-leak-auditor did not actually run on this "
    "exact text (or the text changed after it ran). The tag is self-attestation; it is the "
    "receipt, not the tag, that certifies de-priming. Run brief-leak-auditor on the brief now "
    "(it reads only the brief and judges whether it leaks your lean); fix any lean it names "
    "using ITS neutral rewrite; re-audit until clean; then re-dispatch. Do NOT reply 'my brief "
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
    is_adv = (atype_bare in ADVERSARIAL_AGENTS) or any(p in pl for p in ADVERSARIAL_PHRASES)
    if not is_adv:
        return  # not an adversarial dispatch — silent pass

    # The receipt — not the tag — is what certifies de-priming.
    if has_matching_receipt(brief_region(prompt)):
        log("PASS agent=%s" % (atype or "?"))
        return  # audited-and-clean brief — pass through silently

    tag_present = TAG in prompt
    if tag_present:
        log("NORECEIPT agent=%s (tag, no receipt)" % (atype or "?"))
        if STRICT:
            log("BLOCK agent=%s (strict, no receipt)" % (atype or "?"))
            emit_block(NORECEIPT_MSG)
        else:
            emit_context(NORECEIPT_MSG)
        return

    log("REMIND agent=%s (no %s)" % (atype or "?", TAG))
    if STRICT:
        log("BLOCK agent=%s (strict, no tag)" % (atype or "?"))
        emit_block(REMIND_MSG)
    else:
        emit_context(REMIND_MSG)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never block a dispatch on a gate error
