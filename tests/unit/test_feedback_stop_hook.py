#!/usr/bin/env python3
"""
UNIT TEST — feedback Stop hook (file-claire-issue.py).

The hook fires at turn-end (registered GLOBALLY in ~/.claude/settings.json so it sees every
workspace's sessions). It reads the transcript, finds the just-finished assistant turn's
text, and files any [CLAIRE-ISSUE …] marker to the private queue via claire_feedback.

Each assertion names the bug it guards. The load-bearing ones:
  * a live (unfenced) marker IS filed — the channel actually works end-to-end off a transcript.
  * a marker shown inside a ``` code fence is NOT filed — documenting the format (what this
    very session does constantly) must not spam the queue. This is the discussion-vs-emission
    guard.
  * the template placeholder body is NOT filed — an un-filled-in example is not a real issue.
  * a missing/garbage transcript exits 0 and writes nothing — FAIL-OPEN, never disrupts a turn.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "file-claire-issue.py"))


def _assistant_line(text):
    return json.dumps({"type": "assistant",
                       "message": {"role": "assistant",
                                   "content": [{"type": "text", "text": text}]}})


def _user_line(text):
    return json.dumps({"type": "user",
                       "message": {"role": "user", "content": [{"type": "text", "text": text}]}})


def run_hook(turn_text, queue_dir, transcript_lines=None):
    """Run the Stop hook over a one-turn transcript. Returns (returncode, [issue filenames])."""
    with tempfile.TemporaryDirectory() as td:
        tpath = os.path.join(td, "transcript.jsonl")
        lines = transcript_lines if transcript_lines is not None else [
            _user_line("please do the thing"),
            _assistant_line(turn_text),
        ]
        with open(tpath, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        stdin = json.dumps({"hook_event_name": "Stop", "transcript_path": tpath,
                            "cwd": "/home/dev/some-other-project", "session_id": "s1"})
        env = dict(os.environ)
        env["CLAIRE_ISSUE_DIR"] = queue_dir
        env["CLAIRE_TEST"] = "1"          # queue override is honoured only with the test flag
        proc = subprocess.run([sys.executable, HOOK], input=stdin,
                              capture_output=True, text=True, timeout=15, env=env)
        files = sorted(f for f in os.listdir(queue_dir) if f.endswith(".md")) \
            if os.path.isdir(queue_dir) else []
        return proc.returncode, files


def test_live_marker_is_filed():
    """An unfenced marker in the closing turn lands a real issue file with its body."""
    with tempfile.TemporaryDirectory() as q:
        text = ("Done. Filed the barrier.\n\n"
                "[CLAIRE-ISSUE slug=challenge-args-crash]\n"
                "claire:challenge crashed on prose args; worked around by quoting them.\n"
                "[/CLAIRE-ISSUE]")
        rc, files = run_hook(text, q)
        assert rc == 0, "hook must exit 0"
        assert len(files) == 1, "exactly one issue should be filed, got %r" % files
        with open(os.path.join(q, files[0])) as fh:
            body = fh.read()
        assert "crashed on prose args" in body
        assert "challenge-args-crash" in files[0]


def test_fenced_marker_is_not_filed():
    """A marker shown inside a ``` fence is documentation, not an emission — must NOT file.
    Guards against this session's own constant discussion of the marker format spamming the queue."""
    with tempfile.TemporaryDirectory() as q:
        text = ("Here's how the feedback marker works:\n\n"
                "```\n"
                "[CLAIRE-ISSUE slug=example-only]\n"
                "what was invoked · how it fell short · the workaround\n"
                "[/CLAIRE-ISSUE]\n"
                "```\n\n"
                "Use it like that.")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "a fenced/example marker must not be filed, got %r" % files


def test_template_placeholder_is_not_filed():
    """An unfenced marker whose body is still the placeholder text is not a real issue."""
    with tempfile.TemporaryDirectory() as q:
        text = ("[CLAIRE-ISSUE slug=todo]\n"
                "what was invoked · how it fell short · the workaround\n"
                "[/CLAIRE-ISSUE]")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "the placeholder body must not file, got %r" % files


def test_elided_shorthand_is_not_filed():
    """REGRESSION (live-caught 2026-06-21): an unfenced `[CLAIRE-ISSUE slug=…]…[/CLAIRE-ISSUE]`
    shorthand reference — no real slug, ellipsis body — must NOT file. This exact block, taken
    from real session prose, slipped past the first guard set and filed a slug=feedback/body='…'
    junk issue. Both the explicit-slug requirement and the body-length floor now reject it."""
    with tempfile.TemporaryDirectory() as q:
        text = "as discussed, the hook files an emitted [CLAIRE-ISSUE slug=…]…[/CLAIRE-ISSUE] marker"
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "the elided shorthand must not file, got %r" % files


def test_thin_body_is_not_filed():
    """A well-slugged marker with a too-short body (under the floor) is not a real report."""
    with tempfile.TemporaryDirectory() as q:
        rc, files = run_hook("[CLAIRE-ISSUE slug=foo]\nnope\n[/CLAIRE-ISSUE]", q)
        assert rc == 0
        assert files == [], "a sub-floor body must not file, got %r" % files


def test_no_marker_no_file():
    """A normal closing turn with no marker files nothing (the overwhelmingly common case)."""
    with tempfile.TemporaryDirectory() as q:
        rc, files = run_hook("All done — tests pass and the change is live.", q)
        assert rc == 0
        assert files == []


def test_marker_with_prose_after_is_not_filed():
    """THE CORE SPAM FIX (re-gate blocker): a well-formed unfenced marker is only an EMISSION if
    it is the LAST block of the turn. The same marker with explanatory prose after it is a
    teaching example / quote — not a report — and must NOT file."""
    with tempfile.TemporaryDirectory() as q:
        text = ("[CLAIRE-ISSUE slug=mid-prose-example]\n"
                "claire:challenge errored on prose args; this is a fully-formed example body.\n"
                "[/CLAIRE-ISSUE]\n\nThat's how you'd file it — note the structure above.")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "a marker with prose after it is documentation, not an emission: %r" % files


def test_tilde_fenced_example_not_filed():
    """REGRESSION (breaker-caught): a marker inside a ~~~ tilde fence is documentation, not filed."""
    with tempfile.TemporaryDirectory() as q:
        text = ("Use it like:\n~~~\n[CLAIRE-ISSUE slug=tilde]\n"
                "a fully formed body that is plenty long enough to count\n[/CLAIRE-ISSUE]\n~~~")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "a ~~~-fenced example must not file, got %r" % files


def test_indented_example_not_filed():
    """REGRESSION (breaker-caught): a 4-space-indented marker is not flush-left, so not an emission."""
    with tempfile.TemporaryDirectory() as q:
        text = ("Like so:\n\n    [CLAIRE-ISSUE slug=indented]\n"
                "    a fully formed body that is plenty long enough to count\n    [/CLAIRE-ISSUE]")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert files == [], "an indented example must not file, got %r" % files


def test_missing_transcript_is_fail_open():
    """A missing/garbage transcript path exits 0 and writes nothing — never disrupts the turn."""
    with tempfile.TemporaryDirectory() as q:
        stdin = json.dumps({"hook_event_name": "Stop",
                            "transcript_path": "/nonexistent/path.jsonl", "cwd": "/x"})
        env = dict(os.environ)
        env["CLAIRE_ISSUE_DIR"] = q
        env["CLAIRE_TEST"] = "1"
        proc = subprocess.run([sys.executable, HOOK], input=stdin,
                              capture_output=True, text=True, timeout=15, env=env)
        assert proc.returncode == 0, proc.stderr
        assert [f for f in os.listdir(q) if f.endswith(".md")] == []


def test_empty_stdin_is_fail_open():
    """Empty stdin (no payload) exits 0, no crash."""
    proc = subprocess.run([sys.executable, HOOK], input="",
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr


def test_oversized_single_message_marker_recovered():
    """REGRESSION (re-gate minor): a single assistant message larger than the 256KB tail used to
    truncate into unparseable JSON and silently drop its trailing marker. read_tail now grows
    the read when the tail holds no complete line, so the emission is still filed."""
    with tempfile.TemporaryDirectory() as q:
        huge = "x" * 300000
        text = "%s\n\n[CLAIRE-ISSUE slug=after-huge]\n%s\n[/CLAIRE-ISSUE]" % (
            huge, "a real barrier described in a full sentence here")
        rc, files = run_hook(text, q)
        assert rc == 0
        assert len(files) == 1, "the trailing marker on an oversized message must still file, got %r" % files


def test_fire_log_records_the_decision():
    """When a marker is present the hook logs its decision, so a drop is never silent (Claire's
    FM1 — a silent miss is undiagnosable). A real emission logs FILED beside the queue."""
    with tempfile.TemporaryDirectory() as q:
        text = "[CLAIRE-ISSUE slug=logged-emission]\na real barrier described fully here\n[/CLAIRE-ISSUE]"
        rc, files = run_hook(text, q)
        assert rc == 0 and len(files) == 1
        logp = os.path.join(q, "feedback-fire.log")
        assert os.path.isfile(logp), "a fire-log line must be written when a marker is present"
        content = open(logp).read()
        assert "FILED" in content and "logged-emission" in content, content


def test_no_fire_log_on_plain_turn():
    """A turn with no marker writes NO fire-log line — the log stays quiet on the common case."""
    with tempfile.TemporaryDirectory() as q:
        run_hook("All done, nothing to report here.", q)
        assert not os.path.isfile(os.path.join(q, "feedback-fire.log")), \
            "the fire-log must stay quiet when no marker is present"


def test_dedup_across_two_fires():
    """The same marker filed twice (e.g. hook re-fires) produces ONE file, not two."""
    with tempfile.TemporaryDirectory() as q:
        text = ("[CLAIRE-ISSUE slug=dup-barrier]\nreal barrier body here\n[/CLAIRE-ISSUE]")
        run_hook(text, q)
        rc, files = run_hook(text, q)
        assert rc == 0
        assert len(files) == 1, "dedup must keep it at one file, got %r" % files


CASES = [
    test_live_marker_is_filed,
    test_fenced_marker_is_not_filed,
    test_template_placeholder_is_not_filed,
    test_elided_shorthand_is_not_filed,
    test_thin_body_is_not_filed,
    test_no_marker_no_file,
    test_marker_with_prose_after_is_not_filed,
    test_tilde_fenced_example_not_filed,
    test_indented_example_not_filed,
    test_oversized_single_message_marker_recovered,
    test_fire_log_records_the_decision,
    test_no_fire_log_on_plain_turn,
    test_missing_transcript_is_fail_open,
    test_empty_stdin_is_fail_open,
    test_dedup_across_two_fires,
]

if __name__ == "__main__":
    import _runner
    raise SystemExit(_runner.run(CASES, label="test_feedback_stop_hook.py"))
