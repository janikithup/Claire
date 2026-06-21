#!/usr/bin/env python3
"""
EXPLORATORY breaker harness for the feedback Stop hook — NOT part of the unit CASES.

Throws adversarial / pathological transcripts at the real hook and reports anything that
crashes (non-zero exit), hangs (timeout), files junk it shouldn't, or escapes the queue.
Real findings get promoted to committed regression tests + fixes. Run: python3 this_file.py
"""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "file-claire-issue.py"))


def asst(text):
    return json.dumps({"type": "assistant",
                       "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})


def user(text):
    return json.dumps({"type": "user",
                       "message": {"role": "user", "content": [{"type": "text", "text": text}]}})


def tool_result(text):
    return json.dumps({"type": "user",
                       "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]}})


def run(lines, label, expect_files):
    """Run the hook over `lines`; return (ok, msg). expect_files = how many .md should appear."""
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as q:
        tp = os.path.join(td, "t.jsonl")
        with open(tp, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        stdin = json.dumps({"hook_event_name": "Stop", "transcript_path": tp, "cwd": "/x"})
        env = dict(os.environ); env["CLAIRE_ISSUE_DIR"] = q; env["CLAIRE_TEST"] = "1"
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True,
                               text=True, timeout=20, env=env)
        except subprocess.TimeoutExpired:
            return False, "HANG (>20s)"
        dt = time.time() - t0
        files = [f for f in os.listdir(q) if f.endswith(".md")]
        bodies = []
        for f in files:
            with open(os.path.join(q, f)) as fh:
                bodies.append((f, fh.read()))
        # escape check
        for f, _ in bodies:
            rp = os.path.realpath(os.path.join(q, f))
            if not rp.startswith(os.path.realpath(q) + os.sep):
                return False, "ESCAPED QUEUE: %s" % rp
        if p.returncode != 0:
            return False, "NONZERO EXIT %d stderr=%s" % (p.returncode, p.stderr[:200])
        if len(files) != expect_files:
            return False, "FILED %d, expected %d: %r" % (len(files), expect_files, [f for f, _ in bodies])
        note = "%.2fs" % dt if dt > 1 else ""
        return True, ("ok %s" % note).strip()


REAL = "claire:challenge errored on a multi-line prose argument; worked around by quoting it."
TESTS = []


def t(label, lines, expect):
    TESTS.append((label, lines, expect))


# 1. tilde ~~~ fence around an example marker — does the fence-strip cover ~~~ ?
t("tilde-fence example", [user("q"), asst(
    "Example:\n~~~\n[CLAIRE-ISSUE slug=tilde-example]\n%s\n[/CLAIRE-ISSUE]\n~~~\ndone." % REAL)], 0)

# 2. 4-space-indented code block holding an example marker
t("indented-code example", [user("q"), asst(
    "Like so:\n\n    [CLAIRE-ISSUE slug=indented-example]\n    %s\n    [/CLAIRE-ISSUE]\n\nend." % REAL)], 0)

# 3. marker only in a tool_result (user role) — must NOT be read
t("marker-in-tool-result", [user("q"), tool_result(
    "[CLAIRE-ISSUE slug=from-tool]\n%s\n[/CLAIRE-ISSUE]" % REAL), asst("all done")], 0)

# 4. marker only in user text — must NOT be read
t("marker-in-user-text", [user("[CLAIRE-ISSUE slug=from-user]\n%s\n[/CLAIRE-ISSUE]" % REAL),
                          asst("acknowledged")], 0)

# 5. assistant QUOTES file content with a marker, THEN keeps talking (prose after -> not trailing)
t("echoed-marker-then-prose", [user("show me the file"), asst(
    "Here's the file content:\n\n[CLAIRE-ISSUE slug=echoed-from-file]\n%s\n[/CLAIRE-ISSUE]\n\n"
    "As you can see, that's the format." % REAL)], 0)

# 5b. a real emission: marker IS the final block (nothing after) -> files
t("real-emission-trailing", [user("file it"), asst(
    "Filing to your queue at turn-end: challenge-crash.\n\n"
    "[CLAIRE-ISSUE slug=challenge-crash]\n%s\n[/CLAIRE-ISSUE]" % REAL)], 1)

# 6. performance: 20k bare open-tokens, no close (lazy-regex worst case)
t("many-open-tokens", [user("q"), asst("[CLAIRE-ISSUE " * 20000)], 0)

# 6b. the WORKFLOW's quadratic trigger: 10k COMPLETE flush-left opens, no closes (must be fast)
t("many-complete-opens-no-close", [user("q"), asst(
    "\n".join("[CLAIRE-ISSUE slug=open%d]" % i for i in range(10000)))], 0)

# 6c. 256KB single line ending in a real trailing marker (read_tail must not blank it)
t("huge-single-line-marker", [user("q"), asst(
    "x" * 300000 + " [CLAIRE-ISSUE on one giant line is mid-line so not flush-left] "
    "\n[CLAIRE-ISSUE slug=after-huge-line]\n%s\n[/CLAIRE-ISSUE]" % REAL)], 1)

# 7. performance: huge transcript (tail-read must keep it fast), real marker at the very end
big = [user("q")] + [asst("filler line %d " % i + "x" * 500) for i in range(4000)]
big.append(asst("[CLAIRE-ISSUE slug=end-of-huge]\n%s\n[/CLAIRE-ISSUE]" % REAL))
t("huge-transcript-marker-at-end", big, 1)

# 8. malformed JSON lines interleaved
t("malformed-json-lines", ["{not json", user("q"), "][", asst(
    "[CLAIRE-ISSUE slug=despite-garbage]\n%s\n[/CLAIRE-ISSUE]" % REAL), "}{"], 1)

# 9. content as a STRING not a list
t("content-as-string", [user("q"),
   json.dumps({"type": "assistant", "message": {"role": "assistant",
    "content": "[CLAIRE-ISSUE slug=string-content]\n%s\n[/CLAIRE-ISSUE]" % REAL}})], 1)

# 10. two markers, the SECOND is trailing — only the trailing one files (one report per turn)
t("two-markers-only-trailing-files", [user("q"), asst(
    "[CLAIRE-ISSUE slug=first-one]\n%s\n[/CLAIRE-ISSUE]\n"
    "[CLAIRE-ISSUE slug=second-one]\nA different real barrier, fully described here.\n[/CLAIRE-ISSUE]" % REAL)], 1)

# 11. nested-ish: a stray open token inside a body — bounded regex + flush-left -> files nothing
t("nested-open-in-body", [user("q"), asst(
    "[CLAIRE-ISSUE slug=outer]\nbody mentions [CLAIRE-ISSUE inside and keeps going for real here\n[/CLAIRE-ISSUE]")], 0)

# 12. CRLF line endings in the transcript
t("crlf-endings", [user("q"), asst(
    "[CLAIRE-ISSUE slug=crlf-test]\r\n%s\r\n[/CLAIRE-ISSUE]" % REAL)], 1)

# 13. unicode / emoji body
t("unicode-body", [user("q"), asst(
    "[CLAIRE-ISSUE slug=unicode]\nГ̑ate misfired 日本語 🔥 on a clean handshake, reproduced twice.\n[/CLAIRE-ISSUE]")], 1)


if __name__ == "__main__":
    passes = fails = 0
    for label, lines, expect in TESTS:
        ok, msg = run(lines, label, expect)
        mark = "ok  " if ok else "FAIL"
        print("  [%s] %-32s %s" % (mark, label, msg))
        if ok:
            passes += 1
        else:
            fails += 1
    print("\n  -> %d ok, %d FAIL" % (passes, fails))
    sys.exit(1 if fails else 0)
