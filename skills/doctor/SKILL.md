---
name: doctor
description: Health-check and conflict-check a Claire install. Runs filesystem checks (dependencies, install integrity, duplicate installs, agent-name collisions with the current workspace, leftover old tools) AND a live self-test that confirms Claire's de-priming enforcement is actually firing on this machine — so you know whether strict mode is safe to turn on here. Use after installing or updating Claire, when switching install methods, or when something about Claire seems off. Invoke via /claire:doctor.
---

# /claire:doctor — is Claire healthy and unconflicted on this machine?

Two layers: the filesystem checks (a script) and one live test that only a running
dispatch can do. Run both, then give the user a plain verdict.

## Step 0 — Version line

Run `adv-status.sh` (at the plugin root — the parent of the `skills/` directory
this skill lives in) and print its one-line output at the top (e.g.
`claire v0.4.0 · up to date`). If it reports commits behind origin, note that
`git pull` updates the plugin.

## Step 1 — Filesystem checks

Run the bundled `doctor.sh` **from the user's current workspace** (so its
collision scan sees that workspace's local agents) and show its output verbatim:

```
bash "<plugin-root>/doctor.sh"
```

It checks: `python3` present; `plugin.json` present and no stray `marketplace.json`
beside it; components intact; version / behind-origin; **duplicate installs** (the
same Claire installed in more than one place under `~/.claude` — e.g. a clone *and*
a marketplace copy — which double-loads her hooks and agents); **name collisions**
(local agents in this workspace or your user config that share Claire's agent
names); and leftover superseded tools. WARN lines are informational; FAIL lines
need fixing.

## Step 2 — Live self-test (does enforcement actually fire here?)

This is the check the script cannot do. It verifies that the de-priming *receipt*
mechanism works on this machine — which is what tells you whether strict mode is
safe to enable.

1. Note the current moment, and list any existing receipts: `ls -t "<plugin-root>/hooks/.receipts/" 2>/dev/null`.
2. Dispatch **`claire:brief-leak-auditor`** (namespaced) with this fixed, obviously
   neutral brief as the entire prompt — nothing else:

   > A team must choose between two suppliers that are documented equally well, on
   > equal terms. What is the outside view on how to decide?

   It should return a clean verdict (GENUINELY-NEUTRAL) — this brief carries no lean.
3. After it returns, check the receipts folder again:
   `ls -t "<plugin-root>/hooks/.receipts/"`. A **new** `*.json` file (newer than
   step 1) means the PostToolUse receipt hook fired and recorded the clean audit.

## Step 3 — Verdict

Tell the user, in plain language:

- **If a fresh receipt appeared** → de-priming enforcement is live on this machine,
  and **strict mode (`CLAIRE_GATE_STRICT=1`) is safe to enable** if they want hard
  blocking. Say so.
- **If no receipt appeared** → the receipt hook isn't writing on this machine
  (most likely the tool-result payload shape differs from what the hook reads).
  Claire's gate still **warns** on a skipped audit (it fails safe), so day-to-day
  use is fine — but **do not enable strict mode here**, because it would hard-block
  legitimate dispatches that never earn a receipt. Note it as the one thing to look
  into, and that it does not affect the warn-only default.
- Roll up the filesystem FAILs/WARNs from Step 1 into one or two plain sentences
  (e.g. "you have Claire installed twice — keep one", or "your project has its own
  agents sharing Claire's names; that's fine, just informational").

Keep the whole thing short: a status line, the script output, the self-test result,
and a two-or-three-line verdict. Don't pad it.
