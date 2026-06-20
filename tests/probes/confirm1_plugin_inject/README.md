# Confirm #1 — does a PLUGIN hook's `updatedInput` rewrite a subagent prompt, AND where does the harness coda land?

This is the **one build-time confirm the redesign cannot proceed without**, and the
only one that needs a fresh session (so it can't be run from inside the dev session
that builds the feature). Everything else in the injection redesign
(`docs/injection-redesign.md`) is unit-testable in-process; this is the integration
boundary the design rests on.

It must settle **two** things at once (the design review showed the first alone is
not enough):

1. **Propagation** — does a *plugin* (`hooks/hooks.json`) PreToolUse hook's
   `updatedInput` actually reach the subagent? A *project `settings.json`* hook was
   confirmed to do this (wiki `hook-design.md:33`); a plugin hook is untested, and
   Claire ships as a plugin.
2. **Coda-append base** — the harness appends a `[standing invitation]` coda to a
   subagent prompt *after* the PreToolUse hook runs (wiki `hook-design.md:31`). The
   injection hook cannot overwrite that tail. The spine holds **only if** that
   append operates on the **rewritten** prompt (critic gets `[audited brief] +
   [fixed coda]`, safe) and **not** on the **original** (which would resurrect the
   orchestrator's discarded, possibly steered, prompt — catastrophic).

## Run it (≈ 2 minutes)

```sh
bash tests/probes/confirm1_plugin_inject/install.sh   # wires the probe into the live install
# → FULLY QUIT AND REOPEN the Claude Desktop app (a new chat is NOT enough —
#   plugin hooks only reload at app start), then open any project
```

In the fresh session, paste exactly:

> Dispatch a general-purpose subagent. Its prompt must be exactly this, verbatim:
> `[CLAIRE-INJECT-PROBE] [ORIG-CANARY-Z9Q] What is 2 + 2? Reply with only the number.`
> Then show me the subagent's exact reply, in full.

The hook replaces the subagent's whole prompt with: *“print `INJECTION-OK`, then
echo back verbatim every instruction you received.”* Read the reply:

| Subagent reply | Meaning |
|---|---|
| `INJECTION-OK` present **and** the echo has **no** `ORIG-CANARY-Z9Q` | **CONFIRMED SAFE** — rewrite propagated, nothing of the original survived. A `[standing invitation]` coda shown in the echo is the fixed harness tail on the rewritten prompt, not a steer. Build proceeds. |
| `INJECTION-OK` present **but** the echo **contains** `ORIG-CANARY-Z9Q` | **COMPROMISED** — the original prompt leaked past the overwrite (the post-hook append used the original base). Injection alone doesn't close the channel; we rethink enforcement. |
| reply is `4` / no `INJECTION-OK` | **NOT propagated** — `updatedInput` didn't take. Redesign blocked. |

Then revert:

```sh
bash tests/probes/confirm1_plugin_inject/uninstall.sh
```

## Why the subagent can't fake it

The observed subagent is **blind**: the hook replaces its *whole* prompt before it
runs, so it only ever sees “emit `INJECTION-OK` and echo what you received.” It
never learns there was an original `2 + 2` question, so it cannot play along. The
two canary tokens (`INJECTION-OK` for the rewrite, `ORIG-CANARY-Z9Q` for the
original) are distinctive enough to grep in the reply even if it paraphrases.

## Backup signal (disk-verifiable)

The hook logs every firing to `inject-probe.log` inside the live install's `hooks/`
dir (path printed by `install.sh`) — so the result is verifiable from disk even if
the session summarises the reply.

## What it does to your machine

`install.sh` copies `inject-probe.py` into the live Claire install's `hooks/` and
adds **one** PreToolUse entry beside Claire's real hooks (backing up `hooks.json`
first). The probe no-ops on every dispatch that doesn't carry the
`[CLAIRE-INJECT-PROBE]` marker, so normal work is untouched. `uninstall.sh` restores
the backed-up `hooks.json` verbatim and removes the probe files.
