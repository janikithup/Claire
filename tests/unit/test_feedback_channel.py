#!/usr/bin/env python3
"""
UNIT TEST — claire feedback channel filing core (claire_feedback.py).

The channel exists so a Claire barrier hit while working in ANOTHER workspace lands in the
central private queue (~/.claude/claire/issues/) instead of scattering into whatever repo
the session is rooted in. The agent never WRITES the issue — it EMITS a
[CLAIRE-ISSUE …]…[/CLAIRE-ISSUE] marker and a Stop hook (which runs as the user, outside
the tool sandbox) files it. This module is the shared filing core.

Each assertion names the bug it guards. Load-bearing guarantees:
  * file_issue() writes ONLY under the private queue dir — never a cwd-derived path.
  * a slug carrying path traversal ('../../x') is sanitised, so it can't escape the queue.
  * CLAIRE_ISSUE_DIR is honoured ONLY with CLAIRE_TEST=1 — a hostile project env can't
    redirect the unsandboxed hook's write out of the queue in production (re-gate finding).
  * MARKER_RE is LINEAR on repeated open-tokens — no quadratic turn-hang (re-gate finding).
"""
import contextlib
import importlib.util
import os
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "claire_feedback.py"))


def _load():
    spec = importlib.util.spec_from_file_location("claire_feedback", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load()


@contextlib.contextmanager
def queue_at(path):
    """Point the queue at `path` for the duration — sets BOTH CLAIRE_ISSUE_DIR and the
    CLAIRE_TEST=1 gate the override now requires, and restores prior env after."""
    saved = {k: os.environ.get(k) for k in ("CLAIRE_ISSUE_DIR", "CLAIRE_TEST")}
    os.environ["CLAIRE_ISSUE_DIR"] = path
    os.environ["CLAIRE_TEST"] = "1"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- marker parsing -------------------------------------------------------------------

def test_parse_extracts_slug_and_body():
    """A well-formed flush-left marker yields its slug and trimmed body."""
    text = ("preamble\n[CLAIRE-ISSUE slug=adversarial-review-args-crash]\n"
            "claire:adversarial-review crashed on prose args; worked around by quoting.\n"
            "[/CLAIRE-ISSUE]\ntrailing")
    got = fb.parse_markers(text)
    assert len(got) == 1, "should find exactly one marker"
    assert got[0]["slug"] == "adversarial-review-args-crash", got[0]["slug"]
    assert "crashed on prose args" in got[0]["body"]
    assert "preamble" not in got[0]["body"], "body must not bleed outside the marker"


def test_parse_missing_slug_yields_none_not_a_fallback():
    """A marker with no well-formed slug= yields slug=None — NOT a body-derived fallback.
    REGRESSION (live-caught 2026-06-21): an elided shorthand `[CLAIRE-ISSUE slug=…]…[/CLAIRE-ISSUE]`
    used to fall back to slug=feedback / body='…' and file as a real issue."""
    no_slug = fb.parse_markers("[CLAIRE-ISSUE]\nGate REMIND fired on a clean handshake\n[/CLAIRE-ISSUE]")
    assert no_slug[0]["slug"] is None, "no slug= attr must yield None, not a body fallback"
    elided = fb.parse_markers("[CLAIRE-ISSUE slug=…]…[/CLAIRE-ISSUE]")
    assert elided[0]["slug"] is None, "an ill-formed (…) slug must not resolve to a real slug"


def test_parse_multiple_markers():
    """Two flush-left markers are both captured."""
    text = ("[CLAIRE-ISSUE slug=one]\nbody one\n[/CLAIRE-ISSUE]\n"
            "[CLAIRE-ISSUE slug=two]\nbody two\n[/CLAIRE-ISSUE]")
    got = fb.parse_markers(text)
    assert [g["slug"] for g in got] == ["one", "two"], got


def test_parse_no_marker_returns_empty():
    """Plain text with no marker yields nothing — the common case must be empty, not error."""
    assert fb.parse_markers("just a normal assistant reply, no markers here") == []
    assert fb.parse_markers("") == []
    assert fb.parse_markers(None) == []


def test_parse_is_linear_on_repeated_opens():
    """REGRESSION (re-gate-verified 27s hang): many flush-left [CLAIRE-ISSUE …] opens with no
    closes must parse in well under a second. The bounded body group makes matching linear, not
    quadratic — the global Stop hook fires every turn-end and must never stall one."""
    text = "\n".join("[CLAIRE-ISSUE slug=open%d]" % i for i in range(10000))
    t0 = time.time()
    got = fb.parse_markers(text)
    dt = time.time() - t0
    assert dt < 1.0, "parse took %.2fs on 10k unclosed opens — quadratic regression" % dt
    assert got == [], "unclosed opens match nothing"


def test_nested_markers_dont_corrupt_outer_body():
    """A nested inner marker is never embedded in an outer body — the bounded body group stops
    at the next open, so only a well-formed inner marker parses (re-gate minor finding)."""
    text = ("[CLAIRE-ISSUE slug=outer]\nouter intro text\n"
            "[CLAIRE-ISSUE slug=inner]\ninner body long enough to count\n[/CLAIRE-ISSUE]\n[/CLAIRE-ISSUE]")
    for g in fb.parse_markers(text):
        assert "[CLAIRE-ISSUE" not in g["body"], "body must not embed an inner marker: %r" % g["body"]


def test_slugify_kebabs_and_bounds():
    """slugify lowercases, kebabs, strips junk, and never returns empty."""
    assert fb.slugify("Gate Friction Is Real!") == "gate-friction-is-real"
    assert fb.slugify("   ") == "feedback", "empty input falls back, never blank"
    assert len(fb.slugify("x" * 200)) <= 60, "slug is length-bounded for a sane filename"


# --- filing ---------------------------------------------------------------------------

def test_file_issue_writes_to_queue_and_returns_path():
    """file_issue writes a readable .md under the queue dir and returns its path."""
    with tempfile.TemporaryDirectory() as td, queue_at(td):
        p = fb.file_issue("test-slug", "the body of the issue", source="/some/workspace")
        assert p is not None and os.path.isfile(p), "a non-empty issue must file to disk"
        with open(p) as fh:
            content = fh.read()
        assert "the body of the issue" in content and "test-slug" in content


def test_file_issue_stays_inside_queue_even_with_path_traversal_slug():
    """A slug containing ../ cannot escape the queue dir — sanitised, never a traversal write."""
    with tempfile.TemporaryDirectory() as td, queue_at(td):
        p = fb.file_issue("../../../etc/passwd", "evil but long enough body")
        assert p is not None
        real = os.path.realpath(p)
        assert real.startswith(os.path.realpath(td) + os.sep), \
            "the write MUST stay inside the queue dir; got %s" % real


def test_file_issue_dedups_identical_content():
    """Filing the same slug+body twice does not create a second file (idempotent re-fire)."""
    with tempfile.TemporaryDirectory() as td, queue_at(td):
        p1 = fb.file_issue("dup", "identical body content here")
        p2 = fb.file_issue("dup", "identical body content here")
        assert p1 == p2, "the second identical file must dedup to the first"
        files = [f for f in os.listdir(td) if f.endswith(".md")]
        assert len(files) == 1, "only one file on disk for identical content, got %r" % files


def test_file_issue_empty_body_writes_nothing():
    """An empty/whitespace body files nothing (no junk issues) and returns None."""
    with tempfile.TemporaryDirectory() as td, queue_at(td):
        assert fb.file_issue("x", "") is None
        assert fb.file_issue("x", "   \n  ") is None
        assert [f for f in os.listdir(td) if f.endswith(".md")] == []


def test_default_queue_is_the_private_absolute_path():
    """With no override, the queue resolves to ~/.claude/claire/issues — NOT a cwd-derived
    path. This is the structural guarantee that a feedback issue can never land in a repo."""
    saved = {k: os.environ.get(k) for k in ("CLAIRE_ISSUE_DIR", "CLAIRE_TEST")}
    os.environ.pop("CLAIRE_ISSUE_DIR", None)
    os.environ.pop("CLAIRE_TEST", None)
    try:
        expected = os.path.join(os.path.expanduser("~"), ".claude", "claire", "issues")
        assert fb.queue_dir() == expected, fb.queue_dir()
        assert os.path.isabs(fb.queue_dir()), "the queue path must be absolute, never relative to cwd"
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_env_override_ignored_without_test_flag():
    """PRIVACY (re-gate major): CLAIRE_ISSUE_DIR is honoured ONLY with CLAIRE_TEST=1. Without the
    flag — a hostile project env in production — queue_dir falls back to the FIXED private path,
    so the override cannot redirect a write out of the queue."""
    saved = {k: os.environ.get(k) for k in ("CLAIRE_ISSUE_DIR", "CLAIRE_TEST")}
    os.environ.pop("CLAIRE_TEST", None)
    os.environ["CLAIRE_ISSUE_DIR"] = "/tmp/evil/../../escaped"
    try:
        fixed = os.path.join(os.path.expanduser("~"), ".claude", "claire", "issues")
        assert fb.queue_dir() == fixed, "override must be ignored without CLAIRE_TEST=1: %s" % fb.queue_dir()
    finally:
        os.environ.pop("CLAIRE_ISSUE_DIR", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


CASES = [
    test_parse_extracts_slug_and_body,
    test_parse_missing_slug_yields_none_not_a_fallback,
    test_parse_multiple_markers,
    test_parse_no_marker_returns_empty,
    test_parse_is_linear_on_repeated_opens,
    test_nested_markers_dont_corrupt_outer_body,
    test_slugify_kebabs_and_bounds,
    test_file_issue_writes_to_queue_and_returns_path,
    test_file_issue_stays_inside_queue_even_with_path_traversal_slug,
    test_file_issue_dedups_identical_content,
    test_file_issue_empty_body_writes_nothing,
    test_default_queue_is_the_private_absolute_path,
    test_env_override_ignored_without_test_flag,
]

if __name__ == "__main__":
    import _runner
    raise SystemExit(_runner.run(CASES, label="test_feedback_channel.py"))
