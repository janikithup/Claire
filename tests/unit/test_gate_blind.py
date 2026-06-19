#!/usr/bin/env python3
"""
UNIT TEST (BLIND) — the pre-dispatch adversarial gate, tested purely from its
behavioural spec and I/O contract.

These tests were written WITHOUT reading hooks/adversarial-gate.py. They assert
only OBSERVABLE behaviour — what the hook emits on stdout, which decision word it
writes to gate-fire.log, and its exit code, for a given JSON payload on stdin.
They make NO claim about the hook's internals (no regexes, no branch shapes, no
variable names). If the hook were rewritten from scratch to satisfy the same spec,
these tests should still pass.

WHAT THE GATE IS, in plain terms:
  A filter that runs just before one of this tool's own outside-critic sub-agents
  is dispatched. Its whole job is to stop such a critic from being run on a brief
  that still carries the answer the author was hoping for — UNLESS that brief was
  independently leak-checked and passed. It can stay SILENT (allow), ADVISE (warn
  but allow), or BLOCK (deny). A strict-mode switch turns advisories into blocks;
  a debug switch adds a trace line without changing the decision; and any internal
  error must fail OPEN (silent allow), never block a real dispatch.

HOUSE HARNESS (zero-dependency, bare python3, no pytest):
  We copy the shipped hook into a temp dir and run it as a subprocess, feeding the
  payload as JSON on stdin and reading stdout / the sibling log. The copy gets its
  own ".receipts/" dir and "gate-fire.log" so cases never bleed into each other.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "adversarial-gate.py"))

# Contract constants (given in the I/O contract, NOT reverse-engineered):
MARKER = "[DEPRIMED-BRIEF]"           # the literal de-priming marker
SIGNAL_PHRASE = "devil's advocate"     # a never-in-ordinary-prompts critic signal
CRITIC = "claire:failure-mode-attacker"      # one of this tool's own critics
FOREIGN = "failure-mode-attacker"            # a same-named NON-claire agent
CHECKER = "claire:brief-leak-auditor"        # the de-priming checker — never acted on
RECEIPT_TTL = 2 * 60 * 60              # receipts valid for 2 hours (contract)

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- harness -----------------------------------------------------------------

def _scrubbed_env(**overrides):
    """A deterministic environment: the two behaviour-switching env vars are
    cleared from whatever the test runner inherited, then re-set only by the
    overrides a given test passes. Without this, a CLAIRE_DEBUG/STRICT left in the
    shell would silently change results."""
    env = dict(os.environ)
    env.pop("CLAIRE_GATE_STRICT", None)
    env.pop("CLAIRE_DEBUG", None)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    return env


def _normalize(text):
    """The brief as a receipt stores it: lowercased, whitespace-runs collapsed to
    a single space, trimmed. (From the receipt-file format in the I/O contract.)"""
    return " ".join(text.lower().split())


def run_gate(payload, env_overrides=None, receipts=None):
    """Run the hook against `payload` in an isolated temp dir.

    payload         : the dict sent as JSON on stdin.
    env_overrides   : dict of env vars to set (e.g. {"CLAIRE_DEBUG": "1"}).
    receipts        : optional list of receipt dicts to drop into ".receipts/"
                      beside the hook copy before the run.

    Returns (stdout_str, decision_words_from_log, returncode).
    """
    env_overrides = env_overrides or {}
    workdir = tempfile.mkdtemp(prefix="claire_gate_blind_")
    try:
        hook_copy = os.path.join(workdir, "adversarial-gate.py")
        shutil.copy(HOOK, hook_copy)

        rec_dir = os.path.join(workdir, ".receipts")
        os.makedirs(rec_dir, exist_ok=True)
        for i, rec in enumerate(receipts or []):
            with open(os.path.join(rec_dir, "r%d.json" % i), "w") as fh:
                json.dump(rec, fh)

        proc = subprocess.run(
            [sys.executable, hook_copy],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
            env=_scrubbed_env(**env_overrides),
            cwd=workdir,
        )

        log_path = os.path.join(workdir, "gate-fire.log")
        log_words = []
        if os.path.exists(log_path):
            with open(log_path) as fh:
                contents = fh.read()
            for word in ("PASS", "NORECEIPT", "REMIND", "BLOCK"):
                if word in contents:
                    log_words.append(word)
        return proc.stdout, log_words, proc.returncode
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def make_receipt(brief, age_seconds=0.0):
    """A receipt as the contract describes it: the normalized brief text, a
    unix-second timestamp, and the brief's length. `age_seconds` backdates the
    timestamp so expiry can be exercised."""
    norm = _normalize(brief)
    return {"ts": time.time() - age_seconds, "text": norm, "len": len(norm)}


def dispatch(subagent_type, prompt):
    """The normal-shape dispatch payload: fields at tool_input.*"""
    return {"tool_input": {"subagent_type": subagent_type, "prompt": prompt}}


# --- output-shape helpers (observable contract, not internals) ---------------

def is_silent(stdout):
    """Silent = empty (or whitespace-only) stdout. The contract: empty output
    means allow."""
    return stdout.strip() == ""


def parsed_hook_output(stdout):
    """Parse the advisory/block JSON envelope and return its hookSpecificOutput
    block. Raises if stdout isn't the documented shape — which is itself a useful
    failure (the hook emitted something, but not the contract envelope)."""
    obj = json.loads(stdout)
    return obj["hookSpecificOutput"]


def is_advisory(stdout):
    """Advisory = the documented envelope carrying additionalContext and NO deny
    decision. (Distinguished from a block purely by which fields are present.)"""
    if is_silent(stdout):
        return False
    try:
        hso = parsed_hook_output(stdout)
    except Exception:
        return False
    return "additionalContext" in hso and hso.get("permissionDecision") != "deny"


def is_block(stdout):
    """Block = the documented envelope carrying permissionDecision == 'deny'."""
    if is_silent(stdout):
        return False
    try:
        hso = parsed_hook_output(stdout)
    except Exception:
        return False
    return hso.get("permissionDecision") == "deny"


# =============================================================================
# CLAUSE 1 — irrelevant dispatch stays silent
# =============================================================================

@case
def test_unrelated_agent_no_signal_is_silent():
    """CLAUSE 1. A dispatch that is NOT one of this tool's own critics and whose
    prompt carries no outside-critic signal phrase must produce NO output and have
    no effect. BUG GUARDED: the gate over-fires on ordinary dispatches, nagging or
    blocking work it has no business touching."""
    out, words, code = run_gate(
        dispatch("some-unrelated-helper", "Refactor the billing module for clarity.")
    )
    assert is_silent(out), "expected silent allow, got: %r" % out
    assert words == [], "expected no decision logged, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 2 — a foreign same-named agent is not ours
# =============================================================================

@case
def test_foreign_same_named_agent_is_silent():
    """CLAUSE 2. An agent with the SAME bare name as one of this tool's critics but
    that is actually someone else's (not this tool's) must be left alone — silent.
    The gate must distinguish this tool's own critics from a foreign agent that
    merely shares a name. BUG GUARDED: the gate fires on another tool's (or the
    workspace's own) critic, hijacking dispatches it doesn't own. Tested with a
    marker present so the only reason to fire would be misidentifying ownership."""
    out, words, code = run_gate(
        dispatch(FOREIGN, "Attack this plan. %s" % MARKER)
    )
    assert is_silent(out), "foreign-named agent must not fire the gate, got: %r" % out
    assert words == [], "expected no decision logged, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 3 — the de-priming checker is never acted on
# =============================================================================

@case
def test_depriming_checker_is_never_acted_on():
    """CLAUSE 3. The one critic whose entire job is to read a brief and judge
    whether it leaks the author's preferred answer must NEVER be gated — even when
    its own prompt quotes the de-priming marker and talks about de-priming. BUG
    GUARDED: the gate recurses onto the very agent that performs the leak-check,
    blocking or nagging the checker and breaking the leak-check path itself."""
    out, words, code = run_gate(
        dispatch(CHECKER,
                 "Read this brief and decide whether it leaks. It contains %s and "
                 "discusses de-priming at length." % MARKER)
    )
    assert is_silent(out), "the leak-checker must be left silent, got: %r" % out
    assert words == [], "expected no decision logged for the checker, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 4 — a valid, fresh proof-of-leak-check allows silently
# =============================================================================

@case
def test_critic_with_valid_fresh_proof_is_silent():
    """CLAUSE 4. For one of this tool's own critic dispatches, when a valid and
    fresh proof that THIS brief was leak-checked and passed exists, the gate must
    stay SILENT (allow). BUG GUARDED: the gate ignores a present, matching, fresh
    proof and nags/blocks a brief that was already cleared — punishing the user for
    doing the right thing. Observable signal: silent stdout, PASS in the log."""
    brief = "Here is my plan. Tell me the genuine failure modes you can find."
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        receipts=[make_receipt(brief, age_seconds=60)],  # 1 minute old: fresh
    )
    assert is_silent(out), "a cleared brief must dispatch silently, got: %r" % out
    assert "PASS" in words, "expected a PASS decision logged, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_critic_with_expired_proof_does_not_pass():
    """CLAUSE 4 (freshness boundary). A proof older than its 2-hour validity window
    must NOT count — an expired clearance is no clearance. With the marker present
    but the only proof stale, the gate must NOT stay silent and must NOT log PASS;
    it must fall through to advising (the marker-without-valid-proof case). BUG
    GUARDED: the freshness window is ignored, so a stale clearance lets a primed
    brief through forever."""
    brief = "My plan, marked clean. %s Find the real failure modes." % MARKER
    stale = RECEIPT_TTL + (10 * 60)   # 2h10m old: comfortably past the window
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        receipts=[make_receipt(brief, age_seconds=stale)],
    )
    assert "PASS" not in words, "an expired proof must not count as PASS: %r" % words
    assert not is_silent(out), "expected an advisory, not silence, got: %r" % out
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_critic_with_proof_for_different_brief_does_not_pass():
    """CLAUSE 4 (the proof must be for THIS brief). A fresh, valid proof that
    belongs to a DIFFERENT brief must not clear the brief actually being
    dispatched. BUG GUARDED: the gate accepts any proof in existence rather than
    one matching the current brief, so a single leak-check would silence every
    later dispatch regardless of content."""
    dispatched = "Critique my new launch sequencing decision in full."
    other = "A totally unrelated brief about hiring."
    out, words, code = run_gate(
        dispatch(CRITIC, dispatched),
        receipts=[make_receipt(other, age_seconds=60)],  # fresh, but wrong brief
    )
    assert "PASS" not in words, "a non-matching proof must not PASS: %r" % words
    assert not is_silent(out), "expected an advisory, not silence, got: %r" % out
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 5 — marker present, no valid proof -> advisory (not block, default mode)
# =============================================================================

@case
def test_critic_marker_no_proof_advises():
    """CLAUSE 5. One of this tool's own critic dispatches whose brief carries the
    de-priming marker but has NO valid covering proof must get an ADVISORY (default
    mode advises, never blocks). The observable distinction from the no-marker case
    is the decision word NORECEIPT. BUG GUARDED: the gate treats the marker alone as
    sufficient and stays silent, letting a self-declared-but-unverified brief reach
    the critic with no warning."""
    brief = "My plan, and I've marked it de-primed. %s Attack it." % MARKER
    out, words, code = run_gate(dispatch(CRITIC, brief))  # no receipts at all
    assert is_advisory(out), "expected an advisory envelope, got: %r" % out
    assert not is_block(out), "default mode must advise, not block, got: %r" % out
    assert "NORECEIPT" in words, "expected NORECEIPT decision, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 6 — no marker at all -> advisory (the reminder case)
# =============================================================================

@case
def test_critic_no_marker_advises():
    """CLAUSE 6. One of this tool's own critic dispatches with NO marker at all must
    get an ADVISORY (the de-priming reminder). The observable distinction from the
    marker-but-no-proof case is the decision word REMIND. BUG GUARDED: the gate
    stays silent on a wholly un-marked, un-checked brief — exactly the case the gate
    exists to catch — letting a primed brief reach the critic unflagged."""
    brief = "Here's my approach. Be my devil and find what breaks."
    out, words, code = run_gate(dispatch(CRITIC, brief))
    assert is_advisory(out), "expected an advisory envelope, got: %r" % out
    assert not is_block(out), "default mode must advise, not block, got: %r" % out
    assert "REMIND" in words, "expected REMIND decision, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_signal_phrase_triggers_gate_without_agent_type():
    """CLAUSES 1 & 6 (the signal-phrase entry path). When no agent type identifies a
    critic but the prompt carries the outside-critic signal phrase, the gate must
    still engage (here: advise the un-marked brief), not stay silent. BUG GUARDED:
    the gate only ever keys off the agent type and completely misses a critic invoked
    by signal phrase, leaving that path unprotected."""
    payload = {"tool_input": {"prompt":
               "Play %s on my migration plan and tear it apart." % SIGNAL_PHRASE}}
    out, words, code = run_gate(payload)
    assert not is_silent(out), "signal phrase must engage the gate, got silence"
    assert (is_advisory(out) or is_block(out)), \
        "expected an advisory/block envelope, got: %r" % out
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 7 — strict mode turns advisories into blocks
# =============================================================================

@case
def test_strict_mode_blocks_marker_no_proof():
    """CLAUSE 7 (clause-5 case under strict). With strict mode ON, the marker-but-no-
    proof advisory must become a hard BLOCK (permissionDecision deny). BUG GUARDED:
    strict mode is wired but doesn't actually escalate this case, so an org that
    opted into hard enforcement still only gets a soft warning."""
    brief = "Plan marked clean. %s Attack it." % MARKER
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        env_overrides={"CLAIRE_GATE_STRICT": "1"},
    )
    assert is_block(out), "strict mode must BLOCK this case, got: %r" % out
    assert "BLOCK" in words, "expected BLOCK decision, got: %r" % words
    assert code == 0, "block is reported via JSON, exit still 0; got %d" % code


@case
def test_strict_mode_blocks_no_marker():
    """CLAUSE 7 (clause-6 case under strict). With strict mode ON, the no-marker
    advisory must also become a hard BLOCK. BUG GUARDED: strict mode escalates only
    one of the two advisory cases, leaving the un-marked-brief path soft."""
    brief = "Here's my approach, find what breaks."
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        env_overrides={"CLAIRE_GATE_STRICT": "1"},
    )
    assert is_block(out), "strict mode must BLOCK the no-marker case, got: %r" % out
    assert "BLOCK" in words, "expected BLOCK decision, got: %r" % words
    assert code == 0, "block is reported via JSON, exit still 0; got %d" % code


@case
def test_strict_mode_still_allows_valid_proof():
    """CLAUSE 7 + CLAUSE 4 interaction. Strict mode escalates only the two ADVISORY
    cases (clauses 5 & 6) into blocks. It must NOT block a brief that has a valid,
    fresh, matching proof — that case is a clean allow regardless of strict mode.
    BUG GUARDED: strict mode is implemented as 'block whenever a critic fires',
    blocking even properly leak-checked dispatches and making strict mode unusable."""
    brief = "Cleared plan, please attack it for real failure modes."
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        env_overrides={"CLAIRE_GATE_STRICT": "1"},
        receipts=[make_receipt(brief, age_seconds=60)],
    )
    assert is_silent(out), "a cleared brief must allow even in strict mode, got: %r" % out
    assert "PASS" in words, "expected PASS even under strict mode, got: %r" % words
    assert "BLOCK" not in words, "must not BLOCK a cleared brief: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_strict_mode_off_by_default_only_advises():
    """CLAUSE 7 (default = off). With NO strict switch set, the marker-but-no-proof
    case must ADVISE, never block. BUG GUARDED: strict behaviour leaks into the
    default, so users who never opted into hard enforcement find their dispatches
    blocked. (Pairs with the strict-on block test as a true A/B on the switch.)"""
    brief = "Plan marked clean. %s Attack it." % MARKER
    out, words, code = run_gate(dispatch(CRITIC, brief))  # default env: no switch
    assert is_advisory(out), "default must advise, got: %r" % out
    assert not is_block(out), "default must NOT block, got: %r" % out
    assert "BLOCK" not in words, "default must not log BLOCK: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 8 — debug switch adds a trace, on EVERY dispatch, without changing the
#            decision (visibility only)
# =============================================================================

@case
def test_debug_off_by_default_no_trace_on_allow():
    """CLAUSE 8 (default = off). With debug OFF, the silent-allow case (a cleared
    brief) must remain genuinely silent — no trace leaks into stdout. BUG GUARDED:
    a debug trace is emitted unconditionally, polluting the normal allow path that
    the contract says must be empty."""
    brief = "Cleared plan, attack it for failure modes."
    out, words, code = run_gate(
        dispatch(CRITIC, brief),
        receipts=[make_receipt(brief, age_seconds=60)],
    )  # debug NOT set
    assert is_silent(out), "debug-off allow must be silent, got: %r" % out
    assert "PASS" in words, "expected PASS, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_debug_surfaces_trace_on_silent_allow():
    """CLAUSE 8 (the crucial case). With debug ON, even the otherwise-SILENT allow
    of clause 4 must surface SOMETHING on stdout (a trace) — this is the one case
    where 'silent' and 'debug' interact. BUG GUARDED: the debug trace is wired only
    into the advise/block paths and never appears on the silent-allow path, so the
    most important dispatch to be able to inspect (a clean pass) stays invisible
    even with debug on."""
    brief = "Cleared plan, attack it for failure modes."
    out_dbg, words_dbg, code = run_gate(
        dispatch(CRITIC, brief),
        env_overrides={"CLAIRE_DEBUG": "1"},
        receipts=[make_receipt(brief, age_seconds=60)],
    )
    assert not is_silent(out_dbg), \
        "debug-on must surface a trace even on a silent allow, got silence"
    assert "PASS" in words_dbg, "the decision itself must be unchanged (PASS): %r" % words_dbg
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_debug_does_not_change_the_decision():
    """CLAUSE 8 (visibility only). The debug switch must NOT change WHICH decision is
    taken — only add visibility. Run the same advisory case with debug off and on;
    the logged decision word must be identical (NORECEIPT in both). BUG GUARDED: the
    debug path takes a different branch and silently alters the decision, so what you
    observe under debug isn't what happens in production."""
    brief = "Plan marked clean. %s Attack it." % MARKER
    _, words_off, code_off = run_gate(dispatch(CRITIC, brief))
    _, words_on, code_on = run_gate(
        dispatch(CRITIC, brief),
        env_overrides={"CLAIRE_DEBUG": "1"},
    )
    assert words_off == words_on == ["NORECEIPT"], \
        "decision must be identical with/without debug; off=%r on=%r" % (words_off, words_on)
    assert code_off == code_on == 0, "exit codes must match and be 0"


@case
def test_debug_no_trace_on_unrelated_dispatch():
    """CLAUSE 8 + CLAUSE 1. The debug trace fires on this tool's OWN dispatches; an
    unrelated dispatch that the gate ignores entirely must stay silent even with
    debug on (there is no decision to trace). BUG GUARDED: debug mode makes the gate
    emit a trace for every dispatch in the system, including ones it has no business
    inspecting, leaking noise onto unrelated work."""
    out, words, code = run_gate(
        dispatch("some-unrelated-helper", "Refactor the billing module."),
        env_overrides={"CLAIRE_DEBUG": "1"},
    )
    assert is_silent(out), "debug must not trace an ignored dispatch, got: %r" % out
    assert words == [], "expected no decision logged, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


# =============================================================================
# CLAUSE 9 — robustness: any error / malformed input fails OPEN (silent, exit 0)
# =============================================================================

@case
def test_malformed_json_fails_open():
    """CLAUSE 9. Garbage on stdin (not even JSON) must result in a SILENT allow and
    exit 0. A filter bug must never block a real dispatch. BUG GUARDED: a parse
    error crashes the hook or emits a deny, so a malformed payload blocks legitimate
    work — the worst possible failure for a safety filter."""
    # Bypass run_gate's json.dumps to send raw non-JSON bytes.
    workdir = tempfile.mkdtemp(prefix="claire_gate_blind_")
    try:
        hook_copy = os.path.join(workdir, "adversarial-gate.py")
        shutil.copy(HOOK, hook_copy)
        os.makedirs(os.path.join(workdir, ".receipts"), exist_ok=True)
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input="this is not json {{{ ]]",
            capture_output=True, text=True, timeout=15,
            env=_scrubbed_env(), cwd=workdir,
        )
        assert is_silent(proc.stdout), \
            "malformed input must fail OPEN (silent), got: %r" % proc.stdout
        assert proc.returncode == 0, "must exit 0 on malformed input, got %d" % proc.returncode
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@case
def test_empty_stdin_fails_open():
    """CLAUSE 9 (empty input). No input at all must also fail OPEN — silent, exit 0.
    BUG GUARDED: an empty read raises before the guard and the hook exits non-zero
    or denies, blocking a dispatch when it simply got nothing to inspect."""
    workdir = tempfile.mkdtemp(prefix="claire_gate_blind_")
    try:
        hook_copy = os.path.join(workdir, "adversarial-gate.py")
        shutil.copy(HOOK, hook_copy)
        os.makedirs(os.path.join(workdir, ".receipts"), exist_ok=True)
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input="",
            capture_output=True, text=True, timeout=15,
            env=_scrubbed_env(), cwd=workdir,
        )
        assert is_silent(proc.stdout), "empty input must be silent, got: %r" % proc.stdout
        assert proc.returncode == 0, "empty input must exit 0, got %d" % proc.returncode
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@case
def test_missing_fields_fails_open():
    """CLAUSE 9 (well-formed JSON, missing the dispatch fields). A JSON object that
    lacks tool_input / subagent_type / prompt must not crash the gate — it should
    treat it as nothing to act on and stay silent, exit 0. BUG GUARDED: the hook
    indexes a missing key, raises, and a structurally-odd-but-harmless payload
    blocks a dispatch."""
    out, words, code = run_gate({"unexpected": {"shape": True}})
    assert is_silent(out), "missing-fields payload must be silent, got: %r" % out
    assert words == [], "expected no decision logged, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


@case
def test_corrupt_receipt_does_not_break_the_gate():
    """CLAUSE 9 (robustness around the proof store). A corrupt (non-JSON) file
    sitting in the proof directory must not crash the gate or be mistaken for a
    valid clearance: a critic dispatch with the marker but only a corrupt proof
    present must still ADVISE (not silently pass, not crash). BUG GUARDED: a single
    bad file in the proof store throws and takes the whole filter down, or is
    swallowed in a way that counts as a pass."""
    workdir = tempfile.mkdtemp(prefix="claire_gate_blind_")
    try:
        hook_copy = os.path.join(workdir, "adversarial-gate.py")
        shutil.copy(HOOK, hook_copy)
        rec_dir = os.path.join(workdir, ".receipts")
        os.makedirs(rec_dir, exist_ok=True)
        with open(os.path.join(rec_dir, "broken.json"), "w") as fh:
            fh.write("{ not valid json at all ")
        brief = "Plan marked clean. %s Attack it." % MARKER
        proc = subprocess.run(
            [sys.executable, hook_copy],
            input=json.dumps(dispatch(CRITIC, brief)),
            capture_output=True, text=True, timeout=15,
            env=_scrubbed_env(), cwd=workdir,
        )
        log_path = os.path.join(workdir, "gate-fire.log")
        contents = open(log_path).read() if os.path.exists(log_path) else ""
        assert proc.returncode == 0, "corrupt proof must not crash, exit=%d" % proc.returncode
        assert "PASS" not in contents, \
            "a corrupt proof must NOT count as a clearance: log=%r" % contents
        assert not is_silent(proc.stdout), \
            "expected an advisory despite the corrupt proof, got: %r" % proc.stdout
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# =============================================================================
# Cross-cutting: receipt-text normalization (from the receipt-file contract)
# =============================================================================

@case
def test_proof_matches_after_whitespace_normalization():
    """CLAUSE 4 (proof matching is normalization-tolerant). The contract says a
    proof stores the brief NORMALIZED (lowercased, whitespace collapsed, trimmed).
    A dispatched brief that differs from a fresh proof only by case and extra
    whitespace must still be recognised as covered -> silent PASS. BUG GUARDED: the
    proof match is done on raw text, so trivial reformatting of an already-cleared
    brief defeats the clearance and re-nags the user."""
    canonical = "Tell me the genuine failure modes in my launch plan."
    messy = "  Tell me   the GENUINE failure modes\tin my LAUNCH   plan.  "
    assert _normalize(messy) == _normalize(canonical)  # sanity: same normalized text
    out, words, code = run_gate(
        dispatch(CRITIC, messy),
        receipts=[make_receipt(canonical, age_seconds=60)],
    )
    assert is_silent(out), "normalized-equal brief must be recognised as cleared: %r" % out
    assert "PASS" in words, "expected PASS on normalization-equal proof, got: %r" % words
    assert code == 0, "expected exit 0, got %d" % code


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from _runner import run
    sys.exit(run(CASES))
