#!/usr/bin/env python3
"""
claire de-priming RECEIPT writer.

PostToolUse hook on the Agent/Task tool. FAIL-OPEN: any error => do nothing,
silently. A receipt-writer bug must never disrupt a real dispatch.

Why this exists: the de-priming gate (adversarial-gate.py) used to trust a
self-typed [DEPRIMED-BRIEF] tag — which an anchored main can add WITHOUT ever
running the leak-check. That made the gate honour-system. This hook closes the
loophole: it watches the brief-leak-auditor finish, and only when the auditor
returns a CLEAN verdict (GENUINELY-NEUTRAL, no LEAN) does it write a short-lived
"receipt" — a normalised fingerprint of the exact brief that passed. The gate
then demands a matching receipt, not just the tag. A receipt cannot exist unless
the auditor genuinely ran on that text, so typing the tag no longer buys silence.

Receipt = a small JSON file under hooks/.receipts/ : {ts, text, len}. They expire
fast and are pruned opportunistically; the dir is git-ignored.
"""
import sys, os, json, time, hashlib, re, glob

# A LEAN verdict token: "lean-" followed by a letter/digit (e.g. LEAN-B, lean-option-a),
# but NOT when it sits inside an ordinary word ("cleanly", "leaning" has no hyphen so is
# safe anyway; "clean-ly" is blocked by the non-letter lookbehind). The auditor's verdict
# format is the token "LEAN-<option>"; this matches that, not prose mentions of leaning.
LEAN_VERDICT = re.compile(r"(?<![a-z])lean-[a-z0-9]")

AUDITOR_NAMES = {"brief-leak-auditor"}
RECEIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".receipts")
TTL_SECONDS = 2 * 60 * 60  # a receipt is valid for 2 hours, then ignored/pruned


def normalise(text):
    """Lowercase + collapse all whitespace to single spaces + strip.

    Containment matching against this form is robust to the wrapping the critic
    prompt adds (persona preamble, the tag line, a trailing attack-license)."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def prune(now):
    """Best-effort removal of expired receipts so the dir never grows unbounded."""
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
    """Pull the auditor's returned text out of the PostToolUse payload.

    The agent output arrives under different keys across harness versions, and may
    be a string, a dict, or a list of content blocks — so we stringify defensively.
    If no known response key is present we fall back to the whole payload MINUS
    tool_input, so the audited brief's own wording can never be mistaken for the
    auditor's verdict."""
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
    verdict = response_text(data).lower()

    # CLEAN only: the auditor passed the brief (GENUINELY-NEUTRAL, not negated) and
    # emitted no LEAN-<option> verdict. We match the lean VERDICT token, not a bare
    # "lean-" substring, so a clean verdict that happens to use words like "cleanly"
    # still earns its receipt; and we reject a negated "not genuinely-neutral".
    says_neutral = ("genuinely-neutral" in verdict
                    and "not genuinely-neutral" not in verdict
                    and "n't genuinely-neutral" not in verdict)
    clean = says_neutral and not LEAN_VERDICT.search(verdict)
    if not clean:
        return

    norm = normalise(brief)
    if not norm:
        return

    now = time.time()
    prune(now)
    try:
        os.makedirs(RECEIPT_DIR, exist_ok=True)
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        with open(os.path.join(RECEIPT_DIR, digest + ".json"), "w") as fh:
            json.dump({"ts": now, "text": norm, "len": len(norm)}, fh)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never disrupt a dispatch on a receipt-writer error
