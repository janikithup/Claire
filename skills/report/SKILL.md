---
name: report
description: File a Claire feedback note — a barrier, a misfire, or a judgement about a read — to Claire's private queue from ANY workspace, without it scattering into the repo you're in. Use when a Claire skill or agent fell short (errored, refused, gave a weak read, the gate felt wrong) and you want it captured for Claire's development. Invoke via /claire:report <what happened>. The note is filed by a hook that runs outside the tool sandbox, so it reaches the central queue even from another project.
---

# /claire:report — file a Claire feedback note to the private queue

The problem this solves: when a Claire barrier is hit while working in another project, the
assistant's file-writing is sandboxed to *that* project, so a note written by hand lands in
whatever repo is open — scattering Claire's feedback around, sometimes into a public repo.
This skill never writes a file itself. It **emits a marker** in the reply, and a Stop hook
(which the app runs as you, outside the sandbox) files it to `~/.claude/claire/issues/` from
any workspace.

## Step 0 — Version line

Run `adv-status.sh` (at the plugin root — the parent of the `skills/` directory this skill
lives in) and print its one-line output at the top (e.g. `claire v0.9.0 · up to date`).

## Step 1 — Shape the note

From the user's `<what happened>` (the text after the command, or the surrounding message),
write a tight report with three things, in plain language:

- **what was invoked** — the skill/agent and the situation (e.g. "`/claire:challenge` on a
  research plan");
- **how it fell short** — the actual shortfall (errored, refused, the read was thin, the gate
  REMINDed a clean handshake, …);
- **the workaround**, if any.

Pick a short kebab-case **slug** that names the issue (e.g. `challenge-prose-args-crash`).
Keep the body to a few sentences — match the size of the problem.

## Step 2 — Emit the marker (do NOT write a file)

First, tell the user in **one line** that it will be filed to their private Claire queue when
the turn ends — e.g. *"Filing to your Claire queue at turn-end: `your-chosen-slug`."* (Do not
claim it is already on disk; the hook writes it as the turn closes.)

Then end the reply with the marker block as the **final thing in the message** — flush-left
(no indentation), unfenced, with nothing after it:

[CLAIRE-ISSUE slug=your-chosen-slug]
the real report — what was invoked, how it fell short, the workaround — in a sentence or three
[/CLAIRE-ISSUE]

The filer accepts ONLY a marker that is the LAST block of the turn, at the left margin, with a
real (more-than-a-few-words) body. A marker shown mid-message, indented, fenced, or with any
prose after it is treated as documentation and ignored — which is why the confirmation line
goes **before** the marker, never after.

## Notes

- **Works from any workspace.** The filing hook is registered globally, so this captures a
  barrier hit in a research project, an app repo, anywhere — the note still lands in the one
  central queue, never in the host repo.
- **Private by construction.** The queue sits under `~/.claude/claire/`, which is git-ignored
  and carries its own ignore guard, so a feedback note can't ride into any repo.
- **No file is written by hand.** If you ever cannot emit the marker (e.g. the user wants it
  somewhere specific), say so — do not fall back to writing into the current workspace.
- If `/claire:doctor` reports the feedback hook isn't registered on this machine, run
  `setup-feedback.sh` at the plugin root once to wire it in.
