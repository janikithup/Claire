#!/usr/bin/env python3
"""
claire feedback channel — Stop hook (files emitted [CLAIRE-ISSUE …] markers).

WHY A HOOK. When a Claire barrier is hit in another workspace, the agent's Write tool is
sandboxed away from the central queue. A hook is run by the harness AS THE USER, outside
that sandbox, so it can reach ~/.claude/claire/issues/ from ANY session. The agent emits a
marker in its closing turn; this hook scans the just-finished turn and files it.

REGISTRATION. Registered GLOBALLY in ~/.claude/settings.json by setup-feedback.sh — NOT in
the plugin hooks.json, because a plugin Stop hook's firing on macOS Desktop is unproven and
the 0.4.x receipt saga is the standing lesson (plugin PostToolUse silently never fired). A
global settings.json Stop hook is boundary-tested to fire for every workspace's sessions and
to see THIS turn's own just-finished text at fire time (hook-design notes, 2026-06-20).

FAIL-OPEN. A Stop hook cannot rewrite or block the turn it follows; it only files. Any error
exits 0 silently — it must never disrupt a turn.

DISCUSSION vs EMISSION. The marker text is discussed constantly during Claire's own dev (this
very docstring contains the words). Three guards keep documentation out of the queue:
  1. fenced code regions (``` … ```) are stripped before scanning — examples are fenced;
  2. a body that is still the template placeholder is skipped;
  3. content-hash dedup means repeated discussion of the same block files at most once.
"""
import os
import sys
import json
import re
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import claire_feedback
except Exception:
    claire_feedback = None

MARKER_TOKEN = "[CLAIRE-ISSUE"          # cheap raw-substring gate (no parse on the common path)
# Strip fenced code regions (examples are fenced) — BOTH ``` backtick and ~~~ tilde fences
# (breaker-caught 2026-06-21: a ~~~-fenced example was filing). Replace with a newline so a
# fence between two lines can't merge them and defeat the flush-left marker anchor.
FENCE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
# The design's placeholder body — an un-filled-in marker is not a real issue.
PLACEHOLDER_RE = re.compile(r"what was invoked.*how it fell short", re.IGNORECASE | re.DOTALL)
MIN_BODY_LEN = 15                        # below this is shorthand/elided junk, not a real report
TAIL_BYTES = 256 * 1024                 # the just-finished turn is at the end of the file
MAX_TAIL_BYTES = 8 * 1024 * 1024        # ceiling when one message alone exceeds the normal tail


def _fire_log_path():
    # In test mode (the gated queue override) the log goes inside the temp queue so unit runs
    # don't pollute the real log; otherwise the fixed private region (CLAIRE_LOG_DIR-overridable).
    test_dir = os.environ.get("CLAIRE_ISSUE_DIR")
    if test_dir and os.environ.get("CLAIRE_TEST") == "1":
        return os.path.join(test_dir, "feedback-fire.log")
    base = os.environ.get("CLAIRE_LOG_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "claire")
    return os.path.join(base, "feedback-fire.log")


def log_fire(decision, **kw):
    """One compact line per fire, but ONLY when a marker token is present in the turn (called
    after that check) — OBSERVABILITY only, fail-open. Makes a silent drop diagnosable, which is
    exactly Claire's own FM1 (an undiagnosable silent miss). Never affects filing; quiet on the
    common no-marker turn, so it does not log every turn-end globally."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "decision": decision}
        rec.update(kw)
        with open(_fire_log_path(), "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def read_tail(path):
    size = os.path.getsize(path)
    nbytes = min(size, TAIL_BYTES)
    with open(path, "rb") as fh:
        fh.seek(size - nbytes)
        chunk = fh.read()
    # If the tail holds no COMPLETE transcript line (we seeked into one message larger than the
    # tail — its only newline is the trailing terminator), the leading partial JSON is
    # unparseable and the marker is silently dropped (re-gate finding). Grow the read to a
    # ceiling. Self-limiting: only fires when there is genuinely no newline besides a trailing
    # one, so a normal multi-line tail never pays for it.
    if nbytes < size and b"\n" not in chunk.rstrip(b"\n") and nbytes < MAX_TAIL_BYTES:
        nbytes = min(size, MAX_TAIL_BYTES)
        with open(path, "rb") as fh:
            fh.seek(size - nbytes)
            chunk = fh.read()
    text = chunk.decode("utf-8", "replace")
    if nbytes < size:
        nl = text.find("\n")                # drop the partial first line, if a complete one follows
        if 0 <= nl < len(text) - 1:
            text = text[nl + 1:]
    return text


def assistant_text(tail):
    """Concatenate the assistant TEXT blocks present in the transcript tail, in order.
    Only role=assistant, block type=text — tool_use / tool_result / thinking are skipped."""
    chunks = []
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    chunks.append(b["text"])
    return "\n\n".join(chunks)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    data = json.loads(raw)
    tpath = data.get("transcript_path")
    if not tpath or not os.path.isfile(tpath) or claire_feedback is None:
        return

    tail = read_tail(tpath)
    if MARKER_TOKEN not in tail:         # common path: no marker anywhere -> cheap, quiet, no log
        return

    # From here a marker token is present in the turn — log every decision so a drop is never
    # silent (Claire's FM1). Quiet on the common no-marker turn above.
    session = (data.get("session_id") or "")[:8]
    text = assistant_text(tail)
    if MARKER_TOKEN not in text:         # marker was only in tool/user content, not assistant text
        log_fire("marker-not-in-assistant-text", session=session)
        return

    scannable = FENCE_RE.sub("\n", text)  # drop fenced examples (``` and ~~~) — documentation

    # POSITIVE INTENT GATE (the core spam fix). A live emission is the LAST thing in the turn —
    # the /claire:report skill emits the marker as the final block. So file ONLY the trailing
    # marker, and only when the turn actually ENDS with one. Any marker with prose after it is a
    # teaching example / quote / mid-thread mention, not an emission — exactly what a Claire-dev
    # session produces constantly. This single rule kills the unfenced-quote, the ~~~/indented/
    # inline-fence, and the mid-prose-example vectors at once (re-gate finding).
    if not scannable.rstrip().endswith("[/CLAIRE-ISSUE]"):
        log_fire("not-trailing", session=session, ends=scannable.rstrip()[-60:])
        return
    issues = claire_feedback.parse_markers(scannable)
    if not issues:
        log_fire("no-markers-parsed", session=session)
        return
    issue = issues[-1]                    # the trailing block
    slug, body = issue["slug"], issue["body"]
    if slug is None:
        log_fire("slug-none", session=session)
        return                            # no explicit slug -> a shorthand reference, not an emission
    if len(body) < MIN_BODY_LEN:
        log_fire("thin-body", session=session, slug=slug)
        return                            # too thin to be a real report (an elided '…')
    if PLACEHOLDER_RE.search(body):
        log_fire("placeholder", session=session, slug=slug)
        return                            # un-filled-in template
    path = claire_feedback.file_issue(slug, body, source=data.get("cwd") or None)
    log_fire("FILED" if path else "file-failed", session=session, slug=slug)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)   # fail-open: a feedback-filing error must never disrupt the turn
