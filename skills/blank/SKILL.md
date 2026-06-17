---
name: blank
description: A cold, no-context outside read on a decision or judgement call. You describe the situation; main translates it into neutral plain language, shows you that neutral brief, and hands ONLY that to Claire (the blank-slate advisor), who reasons from nothing else and returns an honest outside recommendation. Use when you want an unanchored second opinion on a call you are sitting with.
---

# /claire:blank — cold outside read (Claire)

A shortcut to the blank-slate primitive in `/claire:challenge`. Steps:

0. **Version line.** Run the status script `adv-status.sh` (at the plugin root — the parent of the `skills/` directory this skill lives in) and print its one-line output at the very top of your response (e.g. `claire v0.2.0 · up to date`). This lets the user confirm, across machines, that this machine is on the latest version. If it reports commits behind origin, surface that the plugin can be updated with `git pull` before proceeding.
1. Take the user's decision / situation (in `$ARGUMENTS` or the surrounding message).
2. Apply the de-priming checklist from `/claire:challenge` Step 2 — translate the situation into neutral, two-sided, jargon-free plain language; strip your own lean and the options you have already ruled out.
3. Leak-check the brief, then show it: dispatch `brief-leak-auditor` with the brief body only (it reads the brief and judges whether it leaks your lean). If it leans, follow the bounded fix loop in `/claire:challenge` Step 3.1 — paste the auditor's neutral rewrite verbatim, re-audit, cap at 2 cycles, and escalate to the user if it still leans rather than proceeding. A clean verdict writes the receipt the gate needs; the `[DEPRIMED-BRIEF]` tag alone does not satisfy it. Then print the `[DEPRIMED-BRIEF]` block, per `/claire:challenge` Step 3. Do NOT self-certify the brief as neutral — that is the failure this step exists to stop.
4. Dispatch `claire:blank-slate-advisor` (the namespaced name — never bare `blank-slate-advisor`, which a workspace's own same-named local agent could shadow) with the leak-checked neutral brief, `[DEPRIMED-BRIEF]` on its own line before the situation — no files, no rationale, no history.
   - **Fallback when `blank-slate-advisor` is not loaded** (its agent-file changes need a session restart on CLI/headless, so after a `git pull` the named agent may be absent): dispatch the built-in **`Plan`** agent on **Opus** instead — preferred over `Explore` (same read-only tools and CLAUDE.md-skip, but a reason-toward-a-recommendation disposition, not search). Build the prompt as: **the persona taken VERBATIM from `agents/blank-slate-advisor.md` — its body, below the frontmatter; do NOT paraphrase, condense, or rewrite it** — then one line, *"You may have read tools available; do not use them — reason only from the brief"* — then `[DEPRIMED-BRIEF]` and the brief. **Never reconstruct the persona from memory:** the verbatim body is the vetted cold read and carries the no-added-priors guardrail; a paraphrase drifts and can smuggle in the priors that guardrail exists to block.
5. Return Claire's read verbatim, then offer to unpack it. If the user wants to track whether her calls hold up over time, log it for outcome-scoring: `adv-score.sh add blank "<one-line topic>"` (prints an id), and later `adv-score.sh verdict <id> right|wrong|partial`. See README → Outcome scoring.

The de-priming standard lives in `/claire:challenge` Step 2 — this skill points to it rather than restating it, so there is one canonical copy.
