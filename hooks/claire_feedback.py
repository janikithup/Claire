#!/usr/bin/env python3
"""
claire feedback channel — shared filing core.

THE PROBLEM IT SOLVES. When a Claire skill or agent hits a barrier while working in
ANOTHER workspace (not the Claire repo), the standing instinct is "file an issue to the
central queue ~/.claude/claire/issues/". But the agent's Write tool is SANDBOXED to the
current workspace, so that absolute path is refused and the issue falls back into whatever
repo the session happens to be in — scattering Claire bug reports across random projects,
and (worse) leaking private content into public repos.

THE FIX. The agent never WRITES the issue. It EMITS a marker —

    [CLAIRE-ISSUE slug=short-kebab-slug]
    what was invoked · how it fell short · the workaround
    [/CLAIRE-ISSUE]

— and a Stop hook (file-claire-issue.py), which the harness runs AS THE USER outside the
tool sandbox, scans the just-finished turn for the marker and calls file_issue() here. The
hook can reach the private queue from ANY session; the agent's Write tool can't. Same trick
the receipt-writer uses (hooks run unsandboxed).

SPINE / PRIVACY GUARANTEES (enforced here, pinned by tests/unit/test_feedback_channel.py):
  * file_issue() writes ONLY under the absolute private queue (queue_dir()). The target is
    NEVER derived from the session cwd, so an issue can't be redirected into a workspace
    repo. This is the structural cure for the scatter+leak vector.
  * a slug carrying path traversal ('../../x') is sanitised by slugify(), so a write can
    never escape the queue dir.
  * the queue dir is git-ignored AND carries its own nested .gitignore (belt-and-suspenders
    against a parent un-ignore — see setup-feedback.sh).
  * FAIL-SAFE: any error returns None (no write) rather than raising into the hook.

CLAIRE_ISSUE_DIR overrides the queue location — for TESTS ONLY (mirrors claire_log's
CLAIRE_LOG_DIR). It is an explicit env affordance, never a cwd-derived path, so it does not
reopen the scatter vector.
"""
import os
import re
import time
import hashlib
import glob

# A feedback marker block. The opening tag must be FLUSH-LEFT (line start): a deliberate
# emission is a standalone block, while an indented / quoted / mid-sentence mention is
# discussion and must never file (breaker-caught 2026-06-21: a 4-space-indented example was
# filing). The body group is BOUNDED — it cannot rescan across another `[CLAIRE-ISSUE` open —
# which (a) makes matching linear instead of quadratic on a turn that repeats the token (a
# re-gate-verified 27s stall otherwise) and (b) stops a nested inner marker from corrupting an
# outer body. slug attr optional; case-insensitive.
MARKER_RE = re.compile(
    r"^\[CLAIRE-ISSUE(?P<attrs>[^\]]*)\]"
    r"(?P<body>(?:(?!\[CLAIRE-ISSUE)[\s\S])*?)"
    r"\[/CLAIRE-ISSUE\]",
    re.IGNORECASE | re.MULTILINE)
SLUG_ATTR_RE = re.compile(r"slug\s*=\s*([A-Za-z0-9][A-Za-z0-9 _-]*)", re.IGNORECASE)


def queue_dir():
    """The private feedback queue: absolute, fixed, NEVER cwd-derived.

    CLAIRE_ISSUE_DIR overrides it ONLY when CLAIRE_TEST=1 is also set (tests). Without that
    gate a hostile project `.claude/settings.json` env block could set CLAIRE_ISSUE_DIR=../..
    and redirect this UNSANDBOXED hook's write out of the private queue and into a repo — the
    exact scatter+leak vector the channel exists to close (re-gate-verified). The registered
    Stop command also strips both vars, so production never honours an override at all."""
    override = os.environ.get("CLAIRE_ISSUE_DIR")
    if override and os.environ.get("CLAIRE_TEST") == "1":
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "claire", "issues")


def slugify(s, fallback="feedback"):
    """Lowercase kebab, junk stripped, length-bounded, never empty. Also the path-traversal
    guard: any '/' or '.' collapses to '-', so a slug can't escape the queue dir."""
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return (s[:60].strip("-")) or fallback


def parse_markers(text):
    """Return [{'slug', 'body'}] for each [CLAIRE-ISSUE …]…[/CLAIRE-ISSUE] block in `text`.

    `slug` is the explicit, well-formed slug= attribute (kebab-normalised) or None — there is
    deliberately NO body-derived fallback. A Claire-dev session writes elided shorthand like
    `[CLAIRE-ISSUE slug=…]…[/CLAIRE-ISSUE]` constantly; with a fallback, that junk reference
    files as a real issue (live-caught 2026-06-21: it produced slug=feedback / body='…'). A
    LIVE emission MUST name a slug; the filing hook drops slug=None. No marker -> []."""
    out = []
    for m in MARKER_RE.finditer(text or ""):
        body = (m.group("body") or "").strip()
        if not body:
            continue
        sm = SLUG_ATTR_RE.search(m.group("attrs") or "")
        out.append({"slug": slugify(sm.group(1)) if sm else None, "body": body})
    return out


def _render(slug, body, source, stamp, content_hash):
    head = ["---", "slug: %s" % slug, "filed: %s" % stamp,
            "content-hash: %s" % content_hash]
    if source:
        head.append("source: %s" % source)
    head += ["via: claire feedback channel (Stop hook)", "---", "", body, ""]
    return "\n".join(head)


def file_issue(slug, body, source=None, ts=None):
    """Write one issue to the private queue. Returns the path written (or the existing path on
    a content-dedup hit), or None on empty body / any error.

    Idempotent: an identical slug+body already in the queue is detected by its content-hash
    frontmatter and NOT rewritten, so a double-firing Stop hook can't create duplicates."""
    try:
        slug = slugify(slug)
        body = (body or "").strip()
        if not body:
            return None
        d = queue_dir()
        os.makedirs(d, exist_ok=True)
        content_hash = hashlib.sha256(("%s\n%s" % (slug, body)).encode("utf-8")).hexdigest()[:10]

        # Dedup: if any queued issue already carries this content-hash, reuse it.
        for existing in glob.glob(os.path.join(d, "*.md")):
            try:
                with open(existing) as fh:
                    if ("content-hash: %s" % content_hash) in fh.read(512):
                        return existing
            except Exception:
                pass

        stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(ts if ts is not None else time.time()))
        # slugify already removed path separators, so this join cannot escape `d`.
        path = os.path.join(d, "%s_%s.md" % (stamp, slug))
        n = 1
        while os.path.exists(path):  # different content, same stamp+slug -> suffix, never clobber
            path = os.path.join(d, "%s_%s-%d.md" % (stamp, slug, n))
            n += 1
        with open(path, "w") as fh:
            fh.write(_render(slug, body, source, stamp, content_hash))
        return path
    except Exception:
        return None
