#!/usr/bin/env python3
"""
INTEGRATION TEST — receipt writer (PostToolUse) <-> gate (PreToolUse), across the
standing-invitation CODA ASYMMETRY.

The harness appends a "[standing invitation] ..." coda to a subagent prompt AFTER the
PreToolUse gate reads it but BEFORE the PostToolUse receipt writer does. So the receipt
fingerprints brief+coda while the gate sees brief-only. Both hooks must strip the coda so
they fingerprint the brief ALONE and the receipt MATCHES the dispatched brief. Observed
live 2026-06-17: the gate kept warning NORECEIPT on a genuinely-audited brief.

We drive the two real hook scripts in one shared temp dir (so they share .receipts) and
assert the gate goes SILENT on the audited brief and still WARNS on an un-audited one.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.abspath(os.path.join(HERE, "..", "..", "hooks"))
CODA = (" [standing invitation] if you disagree with this approach or see a problem with "
        "it, say so and explain why - before or during execution")
BRIEF = ("A team must choose where to host an internal tool: keep it on the existing "
         "self-managed server at a flat monthly cost, or move it to a managed cloud service "
         "billed per usage. Both run the tool and both stay within budget. Pick one for the year.")

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def _stage(td, script, payload):
    # Hermetic: scrub the CLAIRE_* switches from the inherited env so a developer running
    # with CLAIRE_DEBUG / CLAIRE_GATE_STRICT set doesn't flip a silent PASS into a trace
    # or a block (same hardening as test_gate_depriming.py / test_audit_receipt.py).
    env = dict(os.environ)
    for var in ("CLAIRE_DEBUG", "CLAIRE_GATE_STRICT"):
        env.pop(var, None)
    proc = subprocess.run([sys.executable, os.path.join(td, script)],
                          input=json.dumps(payload), capture_output=True, text=True, timeout=15, env=env)
    return proc.returncode, proc.stdout


def _setup(td):
    for f in ("record-audit-receipt.py", "adversarial-gate.py"):
        shutil.copy(os.path.join(HOOKS, f), os.path.join(td, f))


@case
def test_audited_brief_passes_gate_silently_despite_coda():
    """The PostToolUse receipt writer sees brief+coda (auditor view); the PreToolUse gate
    sees brief-only (its view). After coda-stripping in both, the receipt must match the
    dispatched brief and the gate must pass SILENTLY (no warning)."""
    with tempfile.TemporaryDirectory() as td:
        _setup(td)
        # stage 1: receipt writer, clean verdict, prompt carries the appended coda
        _stage(td, "record-audit-receipt.py",
               {"tool_input": {"subagent_type": "claire:brief-leak-auditor", "prompt": BRIEF + CODA},
                "tool_response": "GENUINELY-NEUTRAL\nBoth options stated flatly."})
        assert os.path.isdir(os.path.join(td, ".receipts")) and os.listdir(os.path.join(td, ".receipts")), \
            "a clean audit must write a receipt"
        # stage 2: gate, adversary dispatch with the SAME brief behind the tag, NO coda
        _, out = _stage(td, "adversarial-gate.py",
                        {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                        "prompt": "Attack-license: strongest real failure mode.\n[DEPRIMED-BRIEF]\n" + BRIEF}})
        assert out.strip() == "", "gate must pass SILENTLY for an audited brief (got: %r)" % out[:200]


@case
def test_unaudited_brief_still_warns():
    """Control: a DIFFERENT brief with no matching receipt must still draw the NORECEIPT
    warning - the coda-strip must not make the gate pass everything."""
    with tempfile.TemporaryDirectory() as td:
        _setup(td)
        _stage(td, "record-audit-receipt.py",
               {"tool_input": {"subagent_type": "claire:brief-leak-auditor", "prompt": BRIEF + CODA},
                "tool_response": "GENUINELY-NEUTRAL"})
        _, out = _stage(td, "adversarial-gate.py",
                        {"tool_input": {"subagent_type": "claire:failure-mode-attacker",
                                        "prompt": "Attack-license.\n[DEPRIMED-BRIEF]\nA completely different, never-audited brief about hiring a contractor."}})
        assert "CLAIRE GATE" in out, "gate must still WARN on an un-audited brief"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
