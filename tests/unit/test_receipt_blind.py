#!/usr/bin/env python3
"""
UNIT TEST (BLIND) — record-audit-receipt.py, the leak-audit RECEIPT writer.

Written purely from the behavioural spec and I/O contract, WITHOUT reading the
hook's source. Every assertion is on OBSERVABLE behaviour only — how many receipts
land on disk, what text they store, the process exit code, whether anything is
printed — never on the hook's internal parsing, branch structure, or token
matching. If two implementations satisfy the contract, both must pass this file.

THE CONTRACT (observable):
  in  : one JSON object on stdin with tool_input.subagent_type, tool_input.prompt
        (the audited brief), and tool_response (the auditor's reply, in any shape).
  out : zero or one receipt files in a ".receipts/" dir beside the hook, each
        {"ts": <float>, "text": <canonical brief>, "len": <int>}; exit code 0;
        no stdout unless CLAIRE_DEBUG is truthy, then exactly one JSON line.
        The CANONICAL brief (0.6.2) = the text AFTER the first [DEPRIMED-BRIEF] tag
        when the prompt carries one, else the whole prompt; coda-stripped + normalised.
        (Recording the after-tag region — not the whole prompt — is what lets the gate
        match by exact equality against the critic's own after-tag region while excluding
        any wrapper the caller put before the tag.)
  rule: a receipt is written WHEN AND ONLY WHEN the finished agent is the
        leak-auditor AND its verdict says the brief is genuinely neutral (passed).

Driven by crafted stdin straight into a copy of the SHIPPED hook. Each test's
docstring names the behaviour — and the failure — it guards.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "record-audit-receipt.py"))

# The contract's two named verdict tokens and the auditor's name. These come from
# the I/O CONTRACT, not from the hook's source — they are the public interface.
CLEAN = "GENUINELY-NEUTRAL"
AUDITOR = "claire:brief-leak-auditor"
AUDITOR_BARE = "brief-leak-auditor"


def _run(payload, env_extra=None):
    """Run the SHIPPED hook on one stdin payload in a throwaway dir and observe
    what it does. Returns (returncode, stdout, [receipt dicts written]).

    Isolation: copy the hook into a fresh temp dir so its ".receipts" dir is ours
    alone; scrub CLAIRE_DEBUG from the inherited env so a developer's shell can't
    make the suite flaky; layer env_extra on top for the trace tests.
    """
    with tempfile.TemporaryDirectory() as td:
        copy = os.path.join(td, "record-audit-receipt.py")
        with open(HOOK) as fh:
            src = fh.read()
        with open(copy, "w") as fh:
            fh.write(src)

        env = dict(os.environ)
        env.pop("CLAIRE_DEBUG", None)  # determinism: never inherit the dev switch
        if env_extra:
            env.update(env_extra)

        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run(
            [sys.executable, copy],
            input=stdin, capture_output=True, text=True, timeout=15, env=env)

        rdir = os.path.join(td, ".receipts")
        receipts = []
        if os.path.isdir(rdir):
            for name in sorted(os.listdir(rdir)):
                with open(os.path.join(rdir, name)) as fh:
                    receipts.append(json.load(fh))
        return proc.returncode, proc.stdout, receipts


def _payload(subagent_type, brief, response):
    """A PostToolUse-shaped stdin object: who finished, the brief they audited,
    and the reply they returned (string / list / dict — caller's choice)."""
    return {"tool_input": {"subagent_type": subagent_type, "prompt": brief},
            "tool_response": response}


def _expected_text(brief):
    """The contract's normalisation, computed independently of the hook:
    lowercase, collapse every run of whitespace to one space, trim the ends.
    We assert the stored 'text' equals THIS, never how the hook produces it."""
    return " ".join(brief.lower().split())


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Clause 2 — a clean verdict from the auditor writes exactly one receipt.
# ---------------------------------------------------------------------------

@case
def test_clean_auditor_writes_exactly_one_receipt():
    """Clause 2. The auditor passed the brief as genuinely neutral, so the proof of
    that pass must land: exactly one receipt. GUARDS the failure where a passed brief
    leaves no receipt, so the later gate can never go quiet and nags every clean run."""
    brief = "A team must pick one of two suppliers. What is the outside read?"
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, CLEAN))
    assert rc == 0, "the hook must always exit 0"
    assert len(receipts) == 1, "a clean verdict must write exactly one receipt, no more, no fewer"


@case
def test_receipt_stores_the_audited_brief_normalised():
    """Clause 2 / EFFECT. The receipt must fingerprint the brief THAT PASSED, stored
    normalised (lowercased, whitespace collapsed, trimmed). GUARDS the failure where
    the receipt stores the wrong text (e.g. the response, or the raw un-normalised
    brief) so the gate's later fingerprint comparison can never match."""
    brief = "  Choose   between\tVendor-X  and Vendor-Y.\n  State the trade-offs.  "
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, CLEAN))
    assert len(receipts) == 1
    assert receipts[0]["text"] == _expected_text(brief), \
        "stored text must be the brief, lowercased + whitespace-collapsed + trimmed"
    # And not, say, the verdict or empty:
    assert CLEAN.lower() not in receipts[0]["text"], "must store the brief, not the verdict"


@case
def test_receipt_stores_whole_prompt_minus_tag_delimiter():
    """0.7.1 contract. The receipt fingerprints the WHOLE auditor prompt with only the first
    [DEPRIMED-BRIEF] delimiter excised — NOT just the after-tag body. So any preamble before the
    tag (a persona line, an attack-license — or a smuggled steer) IS part of the fingerprint, so
    it must be audited and it must match the critic's whole prompt. GUARDS the regression where
    the receipt drops the preamble (the 0.6.2 after-tag behaviour that left the pre-tag channel
    unaudited, issue 2026-06-20_1046)."""
    preamble = "You are a sharp outsider. The obvious read is to switch."
    body = "A team must choose between two vendors for a year. Outside read?"
    prompt = preamble + "\n[DEPRIMED-BRIEF]\n" + body
    rc, out, receipts = _run(_payload(AUDITOR_BARE, prompt, CLEAN))
    assert len(receipts) == 1
    assert receipts[0]["text"] == _expected_text(preamble + " " + body), \
        "receipt must store the whole prompt (preamble included), only the tag delimiter excised"
    assert "deprimed-brief" not in receipts[0]["text"], "the tag delimiter itself must not be in the fingerprint"


@case
def test_receipt_schema_shape_is_correct():
    """EFFECT contract. A receipt is {"ts": <float secs>, "text": <str>, "len": <int>}
    and 'len' is the length of the stored text. GUARDS a malformed receipt the gate
    cannot read, and a 'len' that drifts from 'text' (a self-inconsistent fingerprint)."""
    brief = "One slot, two clubs want it — which, and why?"
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, CLEAN))
    assert len(receipts) == 1
    r = receipts[0]
    assert set(r.keys()) >= {"ts", "text", "len"}, "receipt must carry ts, text, len"
    assert isinstance(r["ts"], float), "ts must be unix seconds as a float"
    assert isinstance(r["text"], str)
    assert isinstance(r["len"], int)
    assert r["len"] == len(r["text"]), "len must equal the length of the stored text"


# ---------------------------------------------------------------------------
# Clause 3 — a leaning verdict writes nothing.
# ---------------------------------------------------------------------------

@case
def test_lean_verdict_writes_no_receipt():
    """Clause 3. A LEAN verdict means the brief leaks the author's answer; certifying
    it would defeat the entire product. GUARDS the failure where a leaky brief earns a
    receipt and then sails through the gate as if it had been de-primed."""
    brief = "Obviously option A is the waste; go find what's wrong with it."
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, "LEAN-A"))
    assert rc == 0
    assert receipts == [], "a leaning verdict must write NO receipt"


# ---------------------------------------------------------------------------
# Clause 4 — a NEGATED neutral verdict is not clean.
# ---------------------------------------------------------------------------

@case
def test_verdict_that_denies_neutrality_writes_no_receipt():
    """Clause 4. When the auditor's verdict DENIES that the brief is neutral, the brief
    did not pass — so no receipt. (Observably: the auditor reports the brief is not
    neutral; the contract says treat that as not-clean.) GUARDS the failure where a
    'the brief is not neutral' verdict is mistaken for a pass because the words of the
    neutral token appear inside the denial."""
    brief = "Clearly we should ship Friday; just confirm it for me."
    # The auditor states, in its own words, that the brief is NOT neutral and leans.
    deny = "Assessment: the brief is not neutral — it leans toward shipping. LEAN-SHIP."
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, deny))
    assert rc == 0
    assert receipts == [], "a verdict that denies neutrality must not earn a receipt"


# ---------------------------------------------------------------------------
# Clause 5 — pass that merely DISCUSSES a lean still writes; lean that merely
# MENTIONS neutral still does not. Asserted purely on the receipt outcome.
# ---------------------------------------------------------------------------

@case
def test_pass_that_discusses_a_declined_lean_still_writes_receipt():
    """Clause 5 (forward). The auditor passes a brief yet, by nature, talks about leans
    it weighed and declined. The brief PASSED, so a receipt must still land. GUARDS the
    failure where mentioning a lean anywhere in the reasoning suppresses the receipt for
    a brief that actually passed — sending a clean run into a false-warning loop."""
    brief = "A school has one open slot and two clubs apply; pick one."
    # The auditor names the lean it weighed using the same LEAN-<option> token it
    # would use to FAIL a brief — so a writer that suppresses on any LEAN token at
    # all would wrongly drop this receipt. The verdict itself is still the pass.
    passed_with_reasoning = (
        "Verdict: " + CLEAN + ".\n\n"
        "Reasoning: I weighed whether to call a faint LEAN-One toward the first-named "
        "club, then declined — the concreteness is intrinsic to the option, not "
        "smuggled in by the author.")
    rc, out, receipts = _run(_payload(AUDITOR, brief, passed_with_reasoning))
    assert len(receipts) == 1, \
        "a passing verdict that merely discusses a declined lean must still write a receipt"
    assert receipts[0]["text"] == _expected_text(brief)


@case
def test_lean_that_later_mentions_neutral_writes_no_receipt():
    """Clause 5 (reverse). The mirror must stay shut: the auditor LEANS, and only in
    passing notes the brief 'seems neutral at first'. It did not pass, so no receipt.
    GUARDS the failure where any later appearance of the neutral wording flips a real
    lean into a wrongful pass."""
    brief = "Obviously option A is wasteful; find the problems with it."
    lean_then_aside = (
        "Verdict: LEAN-B.\n\n"
        "At first glance the brief might seem neutral, but 'obviously' and "
        "'wasteful' load option A negatively — the author's answer is showing.")
    rc, out, receipts = _run(_payload(AUDITOR, brief, lean_then_aside))
    assert receipts == [], \
        "a leaning verdict must not earn a receipt even when 'neutral' appears later"


# ---------------------------------------------------------------------------
# Clause 1 — only the leak-auditor's results write receipts.
# ---------------------------------------------------------------------------

@case
def test_non_auditor_clean_looking_output_writes_no_receipt():
    """Clause 1. Some other agent finishes with text that happens to contain the clean
    token. A brief that never went through the leak-auditor must NOT be certified.
    GUARDS the failure where any agent's output can mint a de-priming receipt."""
    brief = "Attack this rollout plan and tell me what fails."
    # An attacker's prose that incidentally contains the clean token.
    rc, out, receipts = _run(_payload(
        "adversarial-review", brief,
        "The plan reads " + CLEAN + " in tone, but the rollback step is missing."))
    assert receipts == [], "only the leak-auditor's results may write a receipt"


# ---------------------------------------------------------------------------
# Clause 6 — the auditor's name is recognised namespaced OR bare.
# ---------------------------------------------------------------------------

@case
def test_namespaced_auditor_name_is_recognised():
    """Clause 6. In production the auditor arrives as 'claire:brief-leak-auditor'. If
    the writer only matched the bare name it would record nothing in real use. GUARDS
    that production failure: the namespaced name must still earn a receipt."""
    brief = "Two roads diverge; which to take and why?"
    rc, out, receipts = _run(_payload(AUDITOR, brief, CLEAN))
    assert len(receipts) == 1, "the namespaced auditor name must be recognised"


@case
def test_bare_auditor_name_is_recognised():
    """Clause 6. The bare name 'brief-leak-auditor' must work too — the contract names
    both forms. GUARDS a writer that only handled one of the two name shapes."""
    brief = "Build it in-house or buy it off the shelf?"
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, CLEAN))
    assert len(receipts) == 1, "the bare auditor name must be recognised"


# ---------------------------------------------------------------------------
# Clause 7 — the verdict is found regardless of the response's SHAPE.
# Observable contract: same verdict, same outcome, whatever container carries it.
# (We do not assert HOW the hook digs it out — only that the receipt outcome is
# identical to the plain-string case for each carrier.)
# ---------------------------------------------------------------------------

@case
def test_clean_verdict_found_in_list_of_content_blocks():
    """Clause 7. The reply may arrive as a list of content blocks rather than a plain
    string. The same clean verdict must produce the same outcome — one receipt. GUARDS
    the failure where a structured reply is treated as having no verdict, so a passed
    brief silently loses its receipt."""
    brief = "A scheduling clash between two teams — what's the outside view?"
    blocks = [{"type": "text", "text": CLEAN + " — both sides stated flatly."}]
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, blocks))
    assert len(receipts) == 1, "a clean verdict carried in content blocks must still write a receipt"
    assert receipts[0]["text"] == _expected_text(brief)


@case
def test_lean_verdict_in_content_blocks_still_writes_nothing():
    """Clause 7 + Clause 3, combined. The negative half of shape-independence: a LEAN
    carried in content blocks must STILL write nothing. GUARDS a parser that, on the
    structured path, loses the lean and wrongly certifies the brief."""
    brief = "Obviously we go with A; poke holes in it."
    blocks = [{"type": "text", "text": "LEAN-A — 'obviously' loads the answer."}]
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, blocks))
    assert receipts == [], "a leaning verdict in content blocks must still write no receipt"


@case
def test_clean_verdict_found_in_dict_response():
    """Clause 7. The reply may also arrive as a dict. The same clean verdict must give
    the same outcome — one receipt. GUARDS the failure where a dict-shaped reply is
    skipped and a passed brief loses its receipt. We try a dict carrying the verdict in
    a 'content' block list, the common harness shape."""
    brief = "Hire a contractor or train an intern for this?"
    as_dict = {"content": [{"type": "text", "text": CLEAN}]}
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, as_dict))
    assert len(receipts) == 1, "a clean verdict carried in a dict response must still write a receipt"
    assert receipts[0]["text"] == _expected_text(brief)


# ---------------------------------------------------------------------------
# Clause 8 — CLAIRE_DEBUG adds VISIBILITY only; it never changes the write.
# ---------------------------------------------------------------------------

@case
def test_debug_off_by_default_prints_nothing():
    """Clause 8. With the debug switch unset, the hook must be silent on stdout so it
    never spams a trace into every dispatch. GUARDS a debug trace left on by default."""
    brief = "Two vendors, one slot — which, and why?"
    rc, out, receipts = _run(_payload(AUDITOR_BARE, brief, CLEAN))
    assert out.strip() == "", "with debug off the hook must print nothing"
    assert len(receipts) == 1, "the write is unaffected by debug being off"


@case
def test_debug_on_emits_one_trace_line_and_does_not_change_a_clean_write():
    """Clause 8. With debug on, the hook surfaces a one-line JSON trace for the builder
    to read — and the receipt write is UNCHANGED (still exactly one for a clean pass).
    GUARDS both halves: a missing/duplicated trace, and debug altering the receipt count."""
    brief = "Situation: choose between two suppliers. Outside read?"
    rc, out, receipts = _run(_payload(AUDITOR, brief, CLEAN), env_extra={"CLAIRE_DEBUG": "1"})
    assert len(receipts) == 1, "debug must not change the receipt write"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, "debug must emit exactly one trace line"
    obj = json.loads(lines[0])  # must be valid JSON in the documented envelope
    assert obj["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert isinstance(obj["hookSpecificOutput"]["additionalContext"], str)


@case
def test_debug_on_does_not_change_a_lean_no_write():
    """Clause 8. The trace must never be a back door: a LEAN with debug on still writes
    NO receipt. GUARDS the failure where turning on visibility accidentally certifies a
    leaning brief."""
    brief = "Obviously option A is wasteful; find problems with it."
    rc, out, receipts = _run(_payload(AUDITOR, brief, "LEAN-B"), env_extra={"CLAIRE_DEBUG": "1"})
    assert receipts == [], "debug visibility must not turn a leaning verdict into a receipt"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, "debug still emits its one trace line on a no-write"
    json.loads(lines[0])  # still valid JSON


# ---------------------------------------------------------------------------
# Clause 9 — robustness: malformed input does nothing, silently, exit 0.
# ---------------------------------------------------------------------------

@case
def test_garbage_stdin_fails_open_silently():
    """Clause 9. Non-JSON on stdin must never crash the dispatch: exit 0, no receipt,
    no traceback on stderr. GUARDS a hook that raises and disrupts the agent run."""
    rc, out, receipts = _run("this is not json at all {{{")
    assert rc == 0, "fail-open: garbage input must still exit 0"
    assert receipts == [], "garbage input must write nothing"


@case
def test_empty_stdin_fails_open():
    """Clause 9. Empty stdin (no payload at all) must also do nothing and exit 0.
    GUARDS a hook that assumes stdin is always a populated JSON object."""
    rc, out, receipts = _run("")
    assert rc == 0, "empty stdin must exit 0"
    assert receipts == [], "empty stdin must write nothing"


@case
def test_missing_fields_fail_open():
    """Clause 9. A well-formed JSON object that LACKS the expected fields (no
    subagent_type, no prompt, no response) must not crash and must write nothing —
    there is no audited brief to certify. GUARDS a hook that indexes blindly into
    absent keys and raises."""
    rc, out, receipts = _run({"something_else": True})
    assert rc == 0, "missing fields must not crash the hook"
    assert receipts == [], "with no brief/verdict there is nothing to certify"


@case
def test_auditor_with_clean_verdict_but_empty_brief_does_not_crash():
    """Clause 9 + Clause 2 boundary. The auditor returns a clean verdict but the brief
    is empty/whitespace. The hook must not crash (exit 0). Whether it writes a receipt
    for an empty brief is left to the implementation — we assert ONLY that it survives,
    since the spec does not state the empty-brief outcome."""
    rc, out, receipts = _run(_payload(AUDITOR_BARE, "   ", CLEAN))
    assert rc == 0, "an empty brief must not crash the hook"
    # No assertion on receipt count: the spec is silent on the empty-brief case.


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
