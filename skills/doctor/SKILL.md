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
`claire v0.4.0 · up to date`). If it reports commits behind origin, note how to update: a clone install updates
with `git pull`; a marketplace install updates by refreshing the marketplace in the
plugins panel (or `/plugin marketplace update` on the terminal).

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

## Step 2.5 — If no receipt appeared, OFFER to turn enforcement on

On the Claude Desktop app, a plugin's PostToolUse hook (the receipt writer) does NOT
fire — only its PreToolUse hook (the warn-gate) does. So out of the box, no receipt is
written and the gate can only ever warn. The fix is a one-time registration of the
receipt writer in `~/.claude/settings.json` (where PostToolUse hooks DO fire), which
the bundled `setup-receipts.sh` does safely and idempotently.

So if Step 2 produced **no fresh receipt** AND Step 1's "Receipt enforcement" check
WARNed that it isn't registered: **offer to turn it on for the user — do not make them
open a terminal.** Ask plainly, e.g. *"Claire's stronger enforcement (the gate going
silent only on a real audit) isn't switched on here yet. Want me to enable it? It adds
one line to your Claude settings file that runs the receipt writer; it's reversible and
can't hang anything."* On **yes**:

1. Run `bash "<plugin-root>/setup-receipts.sh"` and show its one-line result.
2. Re-run the Step 2 live self-test (dispatch the auditor again, check for a fresh
   receipt). It now fires mid-session — no restart needed.
3. Report that enforcement is now live.

On **no**, leave it warn-only and say so — Claire still works, the gate just always
reminds rather than going silent.

## Step 3 — Verdict

Tell the user, in plain language:

- **If a fresh receipt appeared** (originally, or after enabling in Step 2.5) →
  de-priming enforcement is live on this machine, and **strict mode
  (`CLAIRE_GATE_STRICT=1`) is safe to enable** if they want hard blocking. Say so.
- **If no receipt appeared and the user declined to enable it** → Claire runs in
  **warn-only** mode: the gate reminds on every critic dispatch but never goes silent,
  and strict mode must stay OFF (it would hard-block every dispatch). That's a fine
  default; note that `/claire:doctor` can switch on enforcement whenever they want.
- **If no receipt appeared even though it IS registered** → something deeper is off
  (e.g. the receipt writer can't read the verdict on this harness). Flag it as the one
  thing to look into; the warn-only default is unaffected.
- Roll up the filesystem FAILs/WARNs from Step 1 into one or two plain sentences
  (e.g. "you have Claire installed twice — keep one", or "your project has its own
  agents sharing Claire's names; that's fine, just informational").

Keep the whole thing short: a status line, the script output, the self-test result,
and a two-or-three-line verdict. Don't pad it.
