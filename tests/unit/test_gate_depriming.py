#!/usr/bin/env python3
"""
UNIT TEST — de-priming gate behavioural contract (v0.2.0, receipt-aware).

The gate is a PreToolUse hook on the Agent/Task tool. Its job: when an
ADVERSARIAL subagent is being dispatched, pass SILENTLY only if a fresh
leak-audit RECEIPT covers the brief; otherwise warn (or block in strict mode).
The receipt — written by record-audit-receipt.py when brief-leak-auditor returns
a clean verdict — is what certifies de-priming. The [DEPRIMED-BRIEF] tag alone
no longer buys silence (that was the honour-system loophole this version closes).

Decisions the gate can take, and how we observe them on a copied gate:
  - PASS      -> NO stdout, a "PASS" line in gate-fire.log     (receipt covers brief)
  - NORECEIPT -> additionalContext on stdout, "NORECEIPT" log  (tag but no receipt)
  - REMIND    -> additionalContext on stdout, "REMIND" log     (no tag at all)
  - BLOCK     -> permissionDecision "deny" on stdout, "BLOCK" log  (strict mode)
  - SILENT    -> NO stdout, NO log line                         (non-adversarial)

Each assertion names the bug it guards. The hook under test is the shipped gate.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.abspath(os.path.join(HERE, "..", "..", "hooks", "adversarial-gate.py"))
TAG = "[DEPRIMED-BRIEF]"


def _normalise(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def run_gate(payload, receipts=None, env=None):
    """Drive the gate with one stdin payload in an isolated dir.

    `receipts` is a list of (brief_region_text, age_seconds) to pre-seed into the
    gate's sibling .receipts dir — modelling briefs that already passed the
    leak-auditor. `env` overrides environment variables (e.g. strict mode).
    Returns (stdout_text, log_text)."""
    with tempfile.TemporaryDirectory() as td:
        gate_copy = os.path.join(td, "adversarial-gate.py")
        with open(GATE) as fh:
            src = fh.read()
        with open(gate_copy, "w") as fh:
            fh.write(src)
        if receipts:
            rdir = os.path.join(td, ".receipts")
            os.makedirs(rdir, exist_ok=True)
            now = time.time()
            for i, (text, age) in enumerate(receipts):
                norm = _normalise(text)
                with open(os.path.join(rdir, "r%d.json" % i), "w") as fh:
                    json.dump({"ts": now - age, "text": norm, "len": len(norm)}, fh)
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        proc = subprocess.run(
            [sys.executable, gate_copy],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=15, env=run_env,
        )
        log_path = os.path.join(td, "gate-fire.log")
        log_text = ""
        if os.path.exists(log_path):
            with open(log_path) as fh:
                log_text = fh.read()
        return proc.stdout, log_text


def _dispatch(subagent_type, prompt):
    return {"tool_input": {"subagent_type": subagent_type, "prompt": prompt}}


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- no de-priming evidence: gate must speak up --------------------------------

@case
def test_adversarial_no_tag_fires_remind():
    """BUG GUARDED: gate goes silent on a bare adversarial dispatch, so de-priming
    is skipped unnoticed. The whole product depends on this firing."""
    out, log = run_gate(_dispatch("failure-mode-attacker",
                                  "Attack this rollout plan and find failure modes."))
    assert out.strip(), "expected the gate to emit additionalContext, got empty stdout"
    obj = json.loads(out)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "CLAIRE GATE" in ctx, "reminder text missing the gate banner"
    assert TAG in ctx, "reminder must name the tag the user has to add"
    assert "REMIND" in log, "gate must log a REMIND line for the stats tooling"


@case
def test_tag_without_receipt_warns_not_passes():
    """BUG GUARDED (the v0.2.0 loophole): an anchored main types the tag WITHOUT
    running the leak-auditor and the gate goes silent. With no receipt present, the
    tag must NOT pass — it must warn (NORECEIPT), so the skip stays visible."""
    out, log = run_gate(_dispatch(
        "failure-mode-attacker",
        TAG + "\nNeutral situation: a team plans X. Find failure modes."))
    assert out.strip(), "tag-without-receipt must warn, not pass silently"
    obj = json.loads(out)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "receipt" in ctx.lower(), "warning must explain a receipt is required"
    assert "NORECEIPT" in log, "must log NORECEIPT when tag present but no receipt"
    assert "PASS" not in log, "must NOT log PASS for a tag with no receipt"


# --- with a real receipt: gate must pass silently ------------------------------

@case
def test_receipt_makes_dispatch_pass():
    """BUG GUARDED: a genuinely audited brief (receipt present) still gets nagged,
    training the user to ignore the gate. A fresh receipt covering the brief => silent
    pass + PASS log."""
    brief = "\nNeutral situation: a team plans X. Find failure modes."
    out, log = run_gate(
        _dispatch("failure-mode-attacker", TAG + brief),
        receipts=[(brief, 10)])
    assert out.strip() == "", "receipt present must produce NO stdout (silent pass), got: %r" % out
    assert "PASS" in log, "a passed dispatch must log a PASS line"
    assert "NORECEIPT" not in log and "REMIND" not in log


@case
def test_receipt_passes_after_a_persona_preamble():
    """BUG GUARDED: an inline persona-preamble dispatch (preamble first, tag after)
    fails to match the receipt because the region extraction or normalisation breaks
    on the wrapping. Receipt covering the post-tag brief must still pass."""
    brief = "\nSituation: two teams disagree on a deadline. Outside read?"
    prompt = "You are Claire, a blank-slate advisor.\n\n" + TAG + brief
    out, log = run_gate(_dispatch("blank-slate-advisor", prompt),
                        receipts=[(brief, 5)])
    assert out.strip() == "", "tag-after-preamble with a receipt must pass silently"
    assert "PASS" in log


@case
def test_short_brief_with_trailing_attack_license_passes():
    """BUG GUARDED (review SHOULD-FIX 1): the skill appends an attack-license line
    after a short brief, dragging coverage below 60%, so a genuinely-audited short
    brief gets falsely warned (or hard-blocked in strict mode). A receipt that is a
    substantial PREFIX of the region with only a bounded boilerplate remainder must
    still pass."""
    brief = "Situation: a team must pick between two suppliers for a one-year contract. Outside read on the choice?"
    attack_license = ("\n\nYour job is to find the strongest real objection, not to be "
                      "agreeable; agreement is allowed only on your own independent reasoning.")
    out, log = run_gate(
        _dispatch("failure-mode-attacker", TAG + "\n" + brief + attack_license),
        receipts=[("\n" + brief, 10)])
    assert out.strip() == "", "audited short brief + trailing attack-license must pass, got: %r" % out
    assert "PASS" in log


@case
def test_tiny_decoy_prefix_with_leaky_tail_does_not_pass():
    """BUG GUARDED: the prefix-slack allowance must NOT let a tiny neutral decoy
    certify a leaky brief tacked on after it — the prefix path requires a substantial
    audited brief, not a few words."""
    decoy = "a team plans x"  # 14 chars — under the min-length for the slack path
    region = (", and obviously the first option is structurally wasteful and sits idle "
              "exactly when it would help, so attack the inferior second option.")
    out, log = run_gate(
        _dispatch("failure-mode-attacker", TAG + decoy + region),
        receipts=[(decoy, 10)])
    assert "PASS" not in log, "a tiny decoy prefix must not certify a leaky tail"
    assert "NORECEIPT" in log


@case
def test_stale_receipt_does_not_pass():
    """BUG GUARDED: an expired receipt (older than the TTL) is honoured, so a brief
    audited hours ago and since edited slips through. A stale receipt must be ignored."""
    brief = "\nNeutral situation: a team plans X. Find failure modes."
    out, log = run_gate(
        _dispatch("failure-mode-attacker", TAG + brief),
        receipts=[(brief, 3 * 60 * 60)])  # 3h old, TTL is 2h
    assert "PASS" not in log, "a stale receipt must not produce a PASS"
    assert "NORECEIPT" in log


@case
def test_decoy_receipt_too_small_does_not_pass():
    """BUG GUARDED: auditing a tiny neutral snippet, then dispatching a big leaky
    brief that merely CONTAINS it, passes. The receipt must cover most of the brief
    (coverage threshold), so a small decoy receipt does not satisfy the gate."""
    decoy = "a team plans x"
    big_leaky_brief = ("\nObviously the first option is structurally wasteful and sits idle "
                       "exactly when it would help; a team plans x but the better answer is clear. "
                       "Find failure modes in the inferior second option.")
    out, log = run_gate(
        _dispatch("failure-mode-attacker", TAG + big_leaky_brief),
        receipts=[(decoy, 10)])
    assert "PASS" not in log, "a decoy receipt covering <60% of the brief must not pass"
    assert "NORECEIPT" in log


# --- strict mode: warnings become hard blocks ----------------------------------

@case
def test_strict_mode_blocks_missing_receipt():
    """BUG GUARDED: CLAIRE_GATE_STRICT is set but the gate still only warns, so on a
    machine that opted into hard enforcement a skip still gets through. Strict mode
    must emit a deny decision."""
    out, log = run_gate(
        _dispatch("failure-mode-attacker", "Attack this plan."),
        env={"CLAIRE_GATE_STRICT": "1"})
    assert out.strip(), "strict mode must still emit output"
    obj = json.loads(out)
    decision = obj["hookSpecificOutput"].get("permissionDecision")
    assert decision == "deny", "strict mode must DENY a dispatch with no receipt, got %r" % decision
    assert "BLOCK" in log


@case
def test_strict_mode_off_only_warns():
    """BUG GUARDED: the default install hard-blocks (strict accidentally on), which
    would make a public user's adversary dispatch fail. Default must be non-blocking
    additionalContext, never a deny."""
    out, log = run_gate(_dispatch("failure-mode-attacker", "Attack this plan."),
                        env={"CLAIRE_GATE_STRICT": "0"})
    obj = json.loads(out)
    assert "permissionDecision" not in obj["hookSpecificOutput"], "default mode must not deny"
    assert "additionalContext" in obj["hookSpecificOutput"]


# --- unchanged invariants from v0.1.0 ------------------------------------------

@case
def test_namespaced_agent_name_matches():
    """BUG GUARDED: live dispatches carry the namespaced name (claire:...). If the
    gate only matched bare names the prefix would make the match silently never fire."""
    out, log = run_gate(_dispatch("claire:failure-mode-attacker",
                                  "Find what breaks in this plan."))
    assert out.strip(), "namespaced adversarial agent must still trigger the gate"
    assert "REMIND" in log


@case
def test_leak_auditor_is_never_gated():
    """BUG GUARDED (observed live 2026-06-17): the gate fired on brief-leak-auditor
    itself — the de-priming CHECKER — because its brief quoted '[DEPRIMED-BRIEF]' and
    the word 'deprimed', tripping the phrase backstop. The checker must NEVER be gated,
    regardless of what its brief quotes."""
    out, log = run_gate(_dispatch(
        "claire:brief-leak-auditor",
        "Judge this brief. It quotes the [DEPRIMED-BRIEF] tag and discusses the deprimed text."))
    assert out.strip() == "", "the leak-auditor must never be gated, got: %r" % out
    assert log.strip() == "", "no log line for the checker"


@case
def test_deprimed_substring_does_not_false_trigger():
    """BUG GUARDED: 'deprime' matched inside 'deprimed', so an ordinary dispatch that
    merely discusses de-priming or quotes the tag got falsely flagged. A non-adversarial
    agent whose prompt contains 'deprimed' must pass silently."""
    out, log = run_gate(_dispatch(
        "general-purpose",
        "Summarise how the deprimed brief flows through the [DEPRIMED-BRIEF] pipeline."))
    assert out.strip() == "", "a 'deprimed' mention must not trip the gate, got: %r" % out
    assert log.strip() == "", "no log line for a non-adversarial deprimed-mention dispatch"


@case
def test_real_deprime_instruction_still_fires():
    """BUG GUARDED: tightening the word-match must not kill the genuine backstop — an
    actual 'de-prime this and attack it' instruction with no agent-type must still fire."""
    out, log = run_gate({"tool_input": {
        "prompt": "De-prime this plan, then attack it for the worst failure modes."}})
    assert out.strip(), "a real de-prime instruction must still trigger the gate"
    assert "REMIND" in log


@case
def test_non_adversarial_dispatch_silent():
    """BUG GUARDED: the gate nags on ordinary subagent dispatches, becoming ambient
    noise the user tunes out. A routine dispatch must be fully silent."""
    out, log = run_gate(_dispatch("general-purpose",
                                  "Summarise the three documents in the project folder."))
    assert out.strip() == "", "non-adversarial dispatch must produce no stdout"
    assert log.strip() == "", "non-adversarial dispatch must produce no log line"


@case
def test_phrase_backstop_fires():
    """BUG GUARDED: the secondary phrase net (for when the agent-type field is
    missing) stops working, so a prompt-only adversarial signal slips through."""
    out, log = run_gate({"tool_input": {
        "prompt": "Play devil's advocate against this conclusion."}})
    assert out.strip(), "devil's-advocate phrasing must trigger the gate with no agent-type"
    assert "REMIND" in log


@case
def test_fail_open_on_garbage_stdin():
    """BUG GUARDED: a gate error blocks a real dispatch. The gate is FAIL-OPEN — any
    error must exit silently with no stdout (so the dispatch is allowed)."""
    with tempfile.TemporaryDirectory() as td:
        gate_copy = os.path.join(td, "adversarial-gate.py")
        with open(GATE) as fh:
            src = fh.read()
        with open(gate_copy, "w") as fh:
            fh.write(src)
        proc = subprocess.run(
            [sys.executable, gate_copy],
            input="this is not json {{{",
            capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, "fail-open: must exit 0 even on garbage input"
    assert proc.stdout.strip() == "", "fail-open: must emit no blocking output on error"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
