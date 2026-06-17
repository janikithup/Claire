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

NEUTRAL_RE = re.compile(r"genuinely-neutral", re.IGNORECASE)
# The verdict token the auditor emits when it DOES find a lean: uppercase "LEAN-<option>"
# (agent contract: the verdict, on its own line). Case-sensitive so the auditor's lowercase
# prose about leaning ("lean-verdict", "a real lean") is never mistaken for a verdict.
LEAN_TOKEN = re.compile(r"(?<![A-Za-z])LEAN-\w")


def is_clean_verdict(resp):
    """True iff the auditor PASSED the brief (verdict GENUINELY-NEUTRAL).

    The leak-auditor discusses leans BY NATURE even when it passes: it will write
    "I considered a faint LEAN-One but am declining" and still conclude
    GENUINELY-NEUTRAL. So scanning for a LEAN token ANYWHERE wrongly suppresses the
    receipt for a brief that passed (observed live 2026-06-17, twice). The agent
    contract puts the VERDICT first ("return, in order: 1. Verdict ... on its own
    line"), with any such reasoning after it. So a clean pass = the first ASSERTED
    (non-negated) GENUINELY-NEUTRAL appears BEFORE any uppercase LEAN-<option> token.
    A real lean puts "LEAN-X" as the verdict, ahead of (or instead of) any neutral
    mention; a negated "not GENUINELY-NEUTRAL" is skipped so it cannot pass."""
    neutral_pos = None
    for m in NEUTRAL_RE.finditer(resp):
        before = resp[max(0, m.start() - 6):m.start()].lower()
        if re.search(r"(?:not|n't)\s*$", before):
            continue
        neutral_pos = m.start()
        break
    if neutral_pos is None:
        return False
    lean = LEAN_TOKEN.search(resp)
    return lean is None or neutral_pos < lean.start()

AUDITOR_NAMES = {"brief-leak-auditor"}
RECEIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".receipts")
TTL_SECONDS = 2 * 60 * 60  # a receipt is valid for 2 hours, then ignored/pruned


def normalise(text):
    """Lowercase + collapse all whitespace to single spaces + strip.

    Containment matching against this form is robust to the wrapping the critic
    prompt adds (persona preamble, the tag line, a trailing attack-license)."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


# The harness appends a standing-invitation coda to a subagent prompt AFTER the
# PreToolUse gate has read it but BEFORE this PostToolUse hook reads it. So the brief
# this hook fingerprints carries a trailing coda the gate's view never had, and the
# two fingerprints would never match. Cut the (already-normalised) brief at the coda
# marker so BOTH hooks fingerprint the brief ALONE. No-op when no coda is present
# (e.g. an install whose CLAUDE.md carries no subagent-latitude guidance). Observed
# live 2026-06-17; the marker is the harness's own stable label for the injected coda.
CODA_MARKERS = ("[standing invitation]",)


def strip_coda(norm_text):
    cut = len(norm_text)
    for m in CODA_MARKERS:
        i = norm_text.find(m)
        if i != -1:
            cut = min(cut, i)
    return norm_text[:cut].strip()


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
    if not is_clean_verdict(response_text(data)):
        return

    norm = strip_coda(normalise(brief))
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
