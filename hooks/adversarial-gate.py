#!/usr/bin/env python3
"""
claire de-priming gate.

PreToolUse hook on the Agent/Task tool. FAIL-OPEN: any error => allow silently,
so a gate bug can never block a real dispatch.

When an ADVERSARIAL subagent dispatch is detected without the [DEPRIMED-BRIEF]
tag anywhere in its prompt, inject the de-priming checklist as non-blocking
context (a reminder) so the de-priming step cannot be silently skipped.
When the tag IS present, pass through and log a PASS line.
Non-adversarial dispatches pass through silently.
"""
import sys, os, json, datetime

ADVERSARIAL_AGENTS = {
    "blank-slate-advisor", "failure-mode-attacker", "affected-actor-simulator",
    "probe-auditor", "dialectical-scout", "over-capture-triage-verifier",
}
# brief-leak-auditor is DELIBERATELY NOT listed: it is the de-priming CHECKER (it
# reads a brief to judge whether it leaks the author's lean), not an adversary that
# needs a de-primed brief. Gating it would circularly demand a [DEPRIMED-BRIEF] tag on
# the very tool that verifies de-priming. Any agent-list sync check should treat this
# one agents/ file as an intentional non-member, not a missing entry.

# Secondary net for the rare case where the agent-type field does not carry the
# custom agent's name (harness-dependent). Deliberately NARROW — only markers
# that essentially never appear in ordinary, non-adversarial briefs — so the gate
# stays silent on routine subagent dispatches (targeted, never ambient). The
# exact agent-name match above is the real detector; this is only a thin backstop.
ADVERSARIAL_PHRASES = (
    "devil's advocate", "steel-man", "steelman", "de-prime", "deprime",
    "blank-slate advisor",
)

TAG = "[DEPRIMED-BRIEF]"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gate-fire.log")


def log(line):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (ts, line))
    except Exception:
        pass


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    ti = data.get("tool_input", data) or {}

    # agent-type may arrive under several keys depending on harness version
    atype = (ti.get("subagent_type") or ti.get("agentType") or ti.get("agent_type")
             or data.get("subagent_type") or "")
    prompt = ti.get("prompt") or ti.get("description") or ""
    pl = prompt.lower()

    # Live dispatches carry the NAMESPACED agent name (e.g. "claire:blank-slate-advisor").
    # Strip any "namespace:" prefix before matching the bare-name set, or the
    # name-match silently never fires.
    atype_bare = str(atype).strip().split(":")[-1]
    is_adv = (atype_bare in ADVERSARIAL_AGENTS) or any(p in pl for p in ADVERSARIAL_PHRASES)
    if not is_adv:
        return  # not an adversarial dispatch — silent pass

    # Accept the tag ANYWHERE in the prompt, not just as the literal first line:
    # an inline persona-preamble dispatch must put the persona before the brief,
    # so the tag can never lead there. Position adds nothing — it's a
    # self-attestation either way.
    if TAG in prompt:
        log("PASS agent=%s" % (atype or "?"))
        return  # de-primed brief declared — pass through silently

    log("REMIND agent=%s (no %s)" % (atype or "?", TAG))
    msg = (
        "[CLAIRE GATE] This looks like an adversarial / outside-perspective dispatch, "
        "but the " + TAG + " tag is absent — the de-priming step may have been skipped.\n"
        "Before dispatching, apply the de-priming checklist (/claire:challenge Step 2):\n"
        "  - strip your own rationale and the answer you expect\n"
        "  - state every live option fairly (neutral framing, not just omitting your conclusion)\n"
        "  - de-jargon to plain language an outsider reads cold\n"
        "  - situation first, so the adversary forms its own read before any claim\n"
        "  - if this tests whether a specific behaviour fires, run probe-auditor on the brief first\n"
        "Then run brief-leak-auditor on the brief (it reads only the brief and judges whether it "
        "leaks your lean), fix any lean it names, show the user the NEUTRAL BRIEF block, and "
        "re-dispatch with " + TAG + " present in the prompt (it may follow a persona "
        "preamble for an inline dispatch — it need not be the literal first line).\n"
        "Do NOT reply 'my brief is already neutral, moving on' — a producer cannot reliably judge "
        "their own brief's neutrality (proven: high-confidence leaks the author could not see), so "
        "self-certifying is exactly the bypass this gate exists to stop."
    )
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open: never block a dispatch on a gate error
