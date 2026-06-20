#!/usr/bin/env python3
"""
CONFIRM #1 PROBE — does a PLUGIN PreToolUse hook's updatedInput actually rewrite a
subagent's prompt in the live harness, AND does the harness's post-hook coda
append to the REWRITTEN prompt (safe) or the ORIGINAL one (catastrophic)?

This is the load-bearing build-time confirm for the injection redesign
(docs/injection-redesign.md). The redesign overwrites the critic's prompt via
hookSpecificOutput.updatedInput from a PLUGIN hook. Two facts make a naive
"does the rewrite land?" test insufficient:

  1. A project settings.json hook's updatedInput was confirmed to rewrite a
     subagent prompt (wiki hook-design.md:33), but a PLUGIN hook is UNTESTED.
  2. The harness appends a "[standing invitation]" coda to a subagent prompt
     AFTER the PreToolUse hook runs (wiki hook-design.md:31). So the injection
     hook structurally cannot overwrite that tail. The de-priming spine holds
     ONLY IF that post-hook append operates on the REWRITTEN prompt (so the
     critic gets [audited brief] + [fixed harness coda]) and NOT on the original
     (which would resurrect the orchestrator's discarded — possibly steered —
     prompt). This probe must SEE which.

HOW IT IS DEMAND-CHARACTERISTIC-FREE
  The observed subagent is BLIND. Its whole prompt is replaced before it runs; it
  only ever sees an instruction to emit a token and echo back what it received. It
  never learns there was an original question, so it cannot play along. The result
  is decided entirely by what the harness actually delivered to it.

WIRING (install.sh)
  Registered as a PLUGIN PreToolUse hook on Agent/Task in the live install's
  hooks/hooks.json, beside Claire's real hooks. MUST be present at SESSION START
  (a mid-session add fires but does not rewrite — wiki hook-design.md:33).

BEHAVIOUR
  - Fires only when the dispatched prompt contains the marker [CLAIRE-INJECT-PROBE]
    (never touches an ordinary dispatch).
  - On the marker: REPLACES the whole prompt with an instruction to (a) print the
    token INJECTION-OK, then (b) echo, verbatim in a fenced block, every
    instruction the subagent received. Keeps subagent_type (emitting the FULL
    tool_input is safe whether the harness merges or replaces).
  - Logs received + emitted prompts to inject-probe.log beside this file.
  - Fail-open on any error (never blocks a real dispatch).

READING THE RESULT — ask the fresh session to dispatch a general-purpose subagent
with this exact prompt (note the two canary tokens):
    [CLAIRE-INJECT-PROBE] [ORIG-CANARY-Z9Q] What is 2 + 2? Reply with only the number.
Then read the subagent's reply:
    - Has "INJECTION-OK"  AND the echo does NOT contain "ORIG-CANARY-Z9Q"
        -> CONFIRMED SAFE. The rewrite propagated and nothing of the original
           survived. Any "[standing invitation]" coda shown in the echo is the
           fixed harness tail appended to the REWRITTEN prompt — not a steer.
    - Has "INJECTION-OK"  AND the echo DOES contain "ORIG-CANARY-Z9Q"
        -> COMPROMISED. The rewrite landed but the original prompt also reached
           the subagent (the post-hook append used the original base). Injection
           alone does not close the channel — the redesign needs rework.
    - Has neither / replies "4"
        -> NO PROPAGATION. updatedInput did not take. Redesign blocked.
  Cross-check against inject-probe.log (it records exactly what the hook emitted).
"""
import sys, os, json, datetime

MARKER = "[CLAIRE-INJECT-PROBE]"
# The rewrite: emit a token (propagation signal) + echo the full received prompt
# (coda / original-leak diagnostic). Contains NO marker, NO original canary.
REWRITE = (
    "Do exactly two things, in this order, and nothing else.\n"
    "1. Output the single token INJECTION-OK on its own line.\n"
    "2. Then, inside a fenced code block, repeat back VERBATIM and IN FULL every "
    "instruction you were given in this message — every line, exactly as received, "
    "start to end. Do not summarise, omit, or add anything. Then stop."
)
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "inject-probe.log")


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
    prompt = ti.get("prompt") or ti.get("description") or ""

    if MARKER not in prompt:
        return  # not the probe dispatch — silent pass, never touch real work

    new_input = dict(ti)
    new_input["prompt"] = REWRITE

    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": new_input,
    }}
    log("FIRED  received_prompt=%r  emitted_prompt=%r  subagent_type=%r"
        % (prompt[:200], REWRITE[:80] + "...", ti.get("subagent_type")))
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("ERROR (fail-open): %r" % e)
        sys.exit(0)  # fail-open: never block a dispatch on a probe error
