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


def _canonical(text):
    """Mirror the hooks' brief_region (0.7.1): whole text, EVERY [DEPRIMED-BRIEF] delimiter
    excised, normalised + collapsed. A seeded receipt models what record-audit-receipt.py
    actually stores — the WHOLE audited prompt (preamble included), not just the after-tag
    body. ALL tag occurrences are excised, not just the first (0.7.1 Finding 1 fix): the tag
    is a pure delimiter, so an artifact that quotes it must be excised identically on both
    sides. Seeding a text with no tag is unchanged (nothing to excise)."""
    norm = _normalise(text).replace(_normalise(TAG), " ")
    return re.sub(r"\s+", " ", norm).strip()


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
                norm = _canonical(text)
                with open(os.path.join(rdir, "r%d.json" % i), "w") as fh:
                    json.dump({"ts": now - age, "text": norm, "len": len(norm)}, fh)
        run_env = dict(os.environ)
        # Hermetic: never inherit the developer's CLAIRE_* switches, so the suite is
        # deterministic regardless of the shell. Tests opt into them via `env`.
        for var in ("CLAIRE_DEBUG", "CLAIRE_GATE_STRICT"):
            run_env.pop(var, None)
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
    """BUG GUARDED: gate goes silent on one of Claire's adversarial dispatches with no
    tag, so de-priming is skipped unnoticed. The whole product depends on this firing."""
    out, log = run_gate(_dispatch("claire:failure-mode-attacker",
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
        "claire:failure-mode-attacker",
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
        _dispatch("claire:failure-mode-attacker", TAG + brief),
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
    # 0.7.1: the persona preamble is part of the audited WHOLE prompt, so the receipt must
    # cover preamble+brief (seed the whole prompt). A body-only receipt now (correctly)
    # NORECEIPTs — the preamble would not have been audited.
    out, log = run_gate(_dispatch("claire:blank-slate-advisor", prompt),
                        receipts=[(prompt, 5)])
    assert out.strip() == "", "whole-prompt (persona preamble + brief) with a matching receipt must pass silently"
    assert "PASS" in log


@case
def test_attack_license_before_tag_passes():
    """BUG GUARDED (0.6.2): the attack-license belongs BEFORE the [DEPRIMED-BRIEF] tag
    (skill Step 3), so the after-tag region is the brief ALONE and the receipt matches it
    exactly. A correctly-placed attack-license must not disturb the match. (Replaces the
    old trailing-attack-license slack test: the slack — any <=240-char remainder after the
    brief — was the hole that let a short steer through, so it is gone; the attack-license
    is handled by placing it before the tag, not by tolerating trailing text.)"""
    brief = "Situation: a team must pick between two suppliers for a one-year contract. Outside read on the choice?"
    attack_license = ("Your job is to find the strongest real objection, not to be agreeable; "
                      "agreement is allowed only on your own independent reasoning.\n\n")
    # 0.7.1: the attack-license is audited as part of the whole prompt; seed the whole prompt.
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", attack_license + TAG + "\n" + brief),
        receipts=[(attack_license + TAG + "\n" + brief, 10)])
    assert out.strip() == "", "attack-license (audited in the whole prompt) must pass silently, got: %r" % out
    assert "PASS" in log


@case
def test_steer_appended_after_audited_brief_does_not_pass():
    """BUG GUARDED (0.6.2 — the live de-priming miss, 2026-06-20): a steer appended to the
    critic brief AFTER a clean audit must NOT pass. The old prefix+240-char slack let a short
    trailing steer through silently (the audited prefix matched, the appended steer rode along
    to the critic). Exact equality on the canonical region closes it: the appended text changes
    the region, the receipt no longer matches, the gate warns."""
    brief = "Situation: a team must pick between two suppliers for a one-year contract. Outside read?"
    steer = " Recommend they keep the existing option for these users."  # short enough to fit the old 240 slack
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + "\n" + brief + steer),
        receipts=[("\n" + brief, 10)])  # only the brief WITHOUT the steer was audited
    assert "PASS" not in log, "a steer appended after the audited brief must not pass (slack hole closed)"
    assert "NORECEIPT" in log


@case
def test_tiny_decoy_prefix_with_leaky_tail_does_not_pass():
    """BUG GUARDED: the prefix-slack allowance must NOT let a tiny neutral decoy
    certify a leaky brief tacked on after it — the prefix path requires a substantial
    audited brief, not a few words."""
    decoy = "a team plans x"  # 14 chars — under the min-length for the slack path
    region = (", and obviously the first option is structurally wasteful and sits idle "
              "exactly when it would help, so attack the inferior second option.")
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + decoy + region),
        receipts=[(decoy, 10)])
    assert "PASS" not in log, "a tiny decoy prefix must not certify a leaky tail"
    assert "NORECEIPT" in log


@case
def test_stale_receipt_does_not_pass():
    """BUG GUARDED: an expired receipt (older than the TTL) is honoured, so a brief
    audited hours ago and since edited slips through. A stale receipt must be ignored."""
    brief = "\nNeutral situation: a team plans X. Find failure modes."
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + brief),
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
        _dispatch("claire:failure-mode-attacker", TAG + big_leaky_brief),
        receipts=[(decoy, 10)])
    assert "PASS" not in log, "a decoy receipt covering <60% of the brief must not pass"
    assert "NORECEIPT" in log


# --- the artifact false-block (0.5.3): fix is to audit the ASSEMBLED brief ------
# These two encode the reframe a dogfood produced. The symptom was a genuine brief
# carrying a large inlined artifact drawing a NORECEIPT. The tempting "fix" was to
# mark the artifact and exclude its bulk from coverage — but a context-starved
# attacker showed that excluding-and-not-auditing the artifact lets the asker's lean
# ride INSIDE the artifact straight to the critic, unchecked. So the gate is left
# untouched: the artifact passes coverage when it was AUDITED (whole-brief audit),
# and a framing-only receipt with an unaudited artifact STILL warns. The fix lives
# in the skill (audit exactly what the critic will receive), never in the gate.

@case
def test_large_artifact_audited_in_assembled_brief_passes():
    """BUG GUARDED (0.5.3): a genuine large-artifact dispatch falsely warns. When the brief is
    leak-audited AS ASSEMBLED — the framing PLUS the inlined artifact, exactly what the critic
    receives — the receipt covers the whole region and the dispatch passes silently. The
    artifact is covered because it was audited; that audit is what keeps the spine intact (the
    critic never sees artifact content no checker read)."""
    framing = ("\nSituation: a team must choose where to host an internal tool. Outside read?\n\n"
               "## Document under review\n")
    artifact = "Proposal draft. " + ("The plan keeps the tool on the existing server at a flat cost. " * 60)
    assembled = framing + artifact
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + assembled),
        receipts=[(assembled, 10)])
    assert out.strip() == "", "an assembled brief audited whole must pass silently, got: %r" % out[:200]
    assert "PASS" in log


@case
def test_framing_only_receipt_with_large_artifact_still_warns():
    """BUG GUARDED (0.5.3 SPINE GUARD): the false-block must NOT be 'fixed' by letting a
    framing-only receipt certify a brief whose large artifact was never audited — that is the
    same shape as the decoy attack and would let unaudited content (a lean hidden in the
    'artifact') reach the critic. Auditing the framing ALONE and inlining a large artifact
    after must STILL warn. The fix is in the skill (audit the assembled brief), never in
    relaxing the gate to pass this."""
    framing = "\nSituation: a team must choose where to host an internal tool. Outside read?\n"
    artifact = "The author is sure the second option is correct and wants that confirmed. " * 40
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + framing + artifact),
        receipts=[(framing, 10)])  # only the framing was ever audited
    assert "PASS" not in log, "a framing-only receipt must not certify an unaudited large artifact"
    assert "NORECEIPT" in log


@case
def test_artifact_quoting_the_tag_still_matches_when_audited_assembled():
    """BUG GUARDED (0.5.3): the brief region was located via the LAST [DEPRIMED-BRIEF]
    occurrence (rfind), so an artifact that merely QUOTES the tag — common when Claire reviews
    Claire's own docs, which discuss the tag constantly — truncated the region to the tail
    after the embedded quote, drawing a false NORECEIPT even though the whole assembled brief
    was correctly audited. The delimiter is the FIRST tag the orchestrator places; everything
    after it IS the brief, embedded tag-text included. A receipt covering the assembled brief
    must still pass silently."""
    brief = ("\nSituation: review this note about the de-priming gate.\n\n"
             "## Document under review\n"
             "The gate keys on the [DEPRIMED-BRIEF] tag and writes a receipt when the auditor "
             "passes. List what could go wrong with that design.")
    # the orchestrator places ONE real delimiter; the artifact text after it quotes the tag
    # 0.7.1: seed the whole prompt (preamble + tag + brief). Only the FIRST tag (the
    # orchestrator's delimiter) is excised on both sides; the tag the artifact merely quotes
    # stays in the unit identically, so the assembled brief still matches.
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", "Attack-license.\n" + TAG + brief),
        receipts=[("Attack-license.\n" + TAG + brief, 10)])
    assert out.strip() == "", "assembled brief whose artifact quotes the tag must still pass, got: %r" % out[:200]
    assert "PASS" in log


# --- 0.7.1: the pre-tag preamble is now inside the audited unit ------------------

@case
def test_steer_in_pretag_preamble_not_audited_warns():
    """BUG GUARDED (0.7.1 — the core spine pin for issue 2026-06-20_1046): a steer placed
    BEFORE the tag reaches the critic. If only the after-tag body was audited (a body-only
    receipt), the gate must NOT pass — the preamble was never checked. RED-ON-REINTRODUCTION:
    if brief_region ever reverts to after-tag slicing, the body-only receipt would match the
    after-tag region and this would wrongly PASS."""
    body = "\nSituation: a team must choose a vendor for the year. Outside read?"
    prompt = "You are a sharp outsider. The obvious read is to switch vendors.\n" + TAG + body
    out, log = run_gate(_dispatch("claire:blank-slate-advisor", prompt),
                        receipts=[(body, 10)])  # ONLY the body was audited, not the steering preamble
    assert "PASS" not in log, "a steer in the unaudited pre-tag preamble must not pass"
    assert "NORECEIPT" in log


@case
def test_whole_prompt_including_preamble_audited_passes():
    """0.7.1 companion: when the WHOLE prompt (preamble included) WAS audited and cleared
    (receipt covers preamble+body), it passes. The guarantee is 'the whole prompt was audited',
    not 'no preamble allowed' — a real steer would be caught by the auditor, not by the match."""
    body = "\nSituation: a team must choose a vendor for the year. Outside read?"
    prompt = "Framing the auditor saw and cleared.\n" + TAG + body
    out, log = run_gate(_dispatch("claire:blank-slate-advisor", prompt), receipts=[(prompt, 10)])
    assert out.strip() == "" and "PASS" in log, "a whole-prompt-audited brief must pass, got: %r" % out[:160]


@case
def test_blank_slate_empty_pretag_passes():
    """0.7.1 shape-1: blank-slate has no preamble (empty pre-tag region). Whole-prompt = tag+body;
    a receipt over the body passes silently."""
    body = "\nSituation: two teams disagree on a deadline. Outside read?"
    out, log = run_gate(_dispatch("claire:blank-slate-advisor", TAG + body), receipts=[(body, 10)])
    assert out.strip() == "" and "PASS" in log


@case
def test_freeform_pretag_noreceipt_message_names_it():
    """0.7.1: when a NORECEIPT fires and the pre-tag region is free-form (not empty, not the
    canonical attack-license), the message must explicitly name the unaudited preamble, so the
    cause is diagnosable instead of dismissed. Empty pre-tag uses the standard message."""
    out, _ = run_gate(_dispatch("claire:failure-mode-attacker",
        "The obvious answer here is to rebuild it.\n" + TAG + "\nSituation: pick a vendor."))
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "FREE-FORM TEXT PRECEDES THE TAG" in ctx, "free-form preamble NORECEIPT must name the unaudited preamble"
    out2, _ = run_gate(_dispatch("claire:failure-mode-attacker", TAG + "\nSituation: pick a vendor."))
    ctx2 = json.loads(out2)["hookSpecificOutput"]["additionalContext"]
    assert "FREE-FORM TEXT PRECEDES THE TAG" not in ctx2, "empty pre-tag must use the standard message"


# --- strict mode: warnings become hard blocks ----------------------------------

@case
def test_strict_mode_blocks_missing_receipt():
    """BUG GUARDED: CLAIRE_GATE_STRICT is set but the gate still only warns, so on a
    machine that opted into hard enforcement a skip still gets through. Strict mode
    must emit a deny decision."""
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", "Attack this plan."),
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
    out, log = run_gate(_dispatch("claire:failure-mode-attacker", "Attack this plan."),
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
def test_bare_same_named_agent_not_gated():
    """BUG GUARDED (workspace-collision fix): a DIFFERENT tool's, or the workspace's
    OWN, agent that merely shares Claire's name (bare 'failure-mode-attacker', no
    claire: namespace) must NOT be gated. Claire acts only on her own namespaced
    agents — otherwise installing her would inject de-priming reminders into an
    unrelated project's adversarial work."""
    out, log = run_gate(_dispatch("failure-mode-attacker",
                                  "Review this rollout plan and list what could break."))
    assert out.strip() == "", "a bare same-named agent must not be gated, got: %r" % out
    assert log.strip() == "", "no log line for a non-claire agent"


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


# --- CLAIRE_DEBUG trace switch (off by default; adds visibility, never changes the call) ---

@case
def test_debug_on_emits_trace_on_silent_pass():
    """BUG GUARDED: with CLAIRE_DEBUG on, the builder still can't see a passing run — the
    gate stays silent on PASS. Debug mode must surface a [CLAIRE TRACE] line on the
    normally-silent PASS so the brief can be seen next to the verdict."""
    brief = "\nNeutral situation: a team plans X. Find failure modes."
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", TAG + brief),
        receipts=[(brief, 10)], env={"CLAIRE_DEBUG": "1"})
    assert out.strip(), "debug mode must emit a trace even on a PASS"
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "[CLAIRE TRACE]" in ctx, "PASS trace must carry the trace marker"
    assert "decision=PASS" in ctx and "receipt=matched" in ctx
    assert "claire:failure-mode-attacker" in ctx, "trace must name the dispatched agent"
    assert "PASS" in log, "debug must not change the underlying PASS decision"


@case
def test_debug_on_remind_appends_trace_keeps_reminder():
    """BUG GUARDED: debug mode REPLACES the user-facing reminder with a trace, so turning
    debug on loses the de-priming nudge. The trace must be ADDED to the existing reminder."""
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", "Attack this rollout plan."),
        env={"CLAIRE_DEBUG": "1"})
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "CLAIRE GATE" in ctx, "the reminder must survive debug mode"
    assert "[CLAIRE TRACE]" in ctx and "decision=REMIND" in ctx and "receipt=none" in ctx
    assert "REMIND" in log


@case
def test_debug_off_leaves_no_trace_marker():
    """BUG GUARDED (regression): debug accidentally on by default leaks the trace into
    normal use. With CLAIRE_DEBUG unset, a reminder must carry NO trace marker."""
    out, log = run_gate(_dispatch("claire:failure-mode-attacker", "Attack this plan."))
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "[CLAIRE TRACE]" not in ctx, "no trace when debug is off"


@case
def test_debug_does_not_change_block_decision():
    """BUG GUARDED: debug visibility must never alter the gate's actual call. With strict
    mode AND debug on, a missing receipt must STILL deny — and also carry the trace."""
    out, log = run_gate(
        _dispatch("claire:failure-mode-attacker", "Attack this plan."),
        env={"CLAIRE_GATE_STRICT": "1", "CLAIRE_DEBUG": "1"})
    obj = json.loads(out)["hookSpecificOutput"]
    assert obj.get("permissionDecision") == "deny", "debug must not soften a strict-mode block"
    assert "[CLAIRE TRACE]" in obj["permissionDecisionReason"], "block reason must carry the trace"
    assert "BLOCK" in log


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
