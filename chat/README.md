# Claire — chat edition (for regular Claude chat, not Claude Code)

The main Claire is a **Claude Code** plugin: it dispatches a genuinely separate,
context-starved critic and machine-enforces that the critic's brief was stripped
of the answer you expect. None of that machinery exists in regular Claude chat
(claude.ai or the Claude apps) — no hooks, no separate agents.

This folder is the closest thing that **does** work in chat: a prompt-only custom
**Agent Skill** carrying Claire's de-priming discipline and her cold-critic
persona. It's the practice without the guardrails — the same model, in one
conversation, deliberately de-priming itself in two visible phases. Weaker than
the plugin, but it makes Claude genuinely push back instead of agreeing.

## Install (claude.ai — paid plans: Pro / Max / Team)

1. Download this `chat/` folder (it contains `SKILL.md`).
2. In **claude.ai → Settings → Skills**, add a custom skill and upload the folder
   (or its `SKILL.md`). The exact upload step may differ by app version — follow
   the current claude.ai Skills UI.
3. In any chat, ask for a critique — *"what am I missing here"*, *"poke holes in
   this"*, *"is this a good idea"* — and Claire kicks in: she restates your
   situation stripped of the answer you want, then critiques it cold.

## No paid plan, or want the simplest route — use a Project

Any plan can use a **Project** instead of a Skill: create a new Project and paste
the body of `SKILL.md` (everything below the `---` frontmatter) into its custom
instructions. Every chat in that Project then runs the de-priming discipline.

## What it does NOT do

- No separate critic and no machine-checked brief — de-priming is **self-applied,
  not enforced**. A single model can still talk itself back toward agreeing.
- For the enforced version, use the Claude Code plugin:
  https://github.com/janikithup/Claire
