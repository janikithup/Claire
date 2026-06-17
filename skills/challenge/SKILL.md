---
name: challenge
description: Give me an adversary / an outside read on this. Routes "challenge X" to the right kind of critic (a cold outside read, a plan-attacker, an actor role-play, a source-vs-claim check, a two-sides face-off, or a check that a test isn't rigged), strips the brief of the answer you expect so the critic genuinely challenges instead of confirming, and shows you that neutral brief before dispatching. Use for "attack this", "outside view on this", "what am I missing", "how would X react", "is my test rigged" requests.
---

# /claire:challenge — route, de-prime, dispatch an adversary

You (the main agent) are the anchored party — you often authored, or formed a view on, the thing under review. A model cannot de-bias its own brief just by intending to; "challenge this freely" does not strip the anchor. So this skill makes de-priming an explicit, visible step, not a good intention.

## Step 0 — Version line

Run the status script `adv-status.sh` (at the plugin root — the parent of the `skills/` directory this skill lives in) and print its one-line output at the top of your response (e.g. `claire v0.2.0 · up to date`). This lets the user confirm, across machines, that this machine is on the latest version; if it reports commits behind origin, surface that `git pull` will update the plugin.

## Step 1 — Pick the primitive (inference-first)

Read what the user actually has in front of them and route by its shape. Do not make the user know the primitive names.

| What the user has | Route to |
|---|---|
| A plan / proposed approach — "what could go wrong" | `failure-mode-attacker` (fast, minimum-context) or the `adversarial-review` workflow (parallel per-dimension) |
| An unspecified decision / judgement call — "outside view" | `blank-slate-advisor` (via the procedure below; this is what `/claire:blank` does) |
| A specific named person who would be affected — "how would they react" | `affected-actor-simulator` |
| A claim drawn from a source — "does the source actually say this" | `over-capture-triage-verifier`, or the `voir-dire` workflow |
| Two genuinely-tensioned directions — "argue both sides" | a `dialectical-scout` pair, or the `adversarial-decomposition-chain` workflow |
| A test / probe of whether some behaviour fires — "is this rigged" | `probe-auditor` FIRST (always) |
| An assumption set — "stress my assumptions" | the `assumption-stress-test` workflow |
| "What am I missing entirely" | the `counter-evidence-map` / `value-conflict-map` workflows |

If two rows match or the situation is unclear, ask the user in plain language — phrase the options by what they DO, never by primitive name ("Attack the plan and find what's most likely to fail / Outside view from scratch / How would [person] react / Check the claim against its source").

The `...-workflow` entries are dynamic-workflow presets. They are NOT bundled in this plugin (a plugin cannot ship workflows); they fire only where `~/.claude/workflows/` carries them. If a named workflow is not available in this workspace, fall back to the nearest subagent in the table.

## Step 2 — De-prime the brief (apply every time, before any dispatch)

Write the adversary's brief against this checklist:

- [ ] **Strip your rationale and your expected answer.** Write what the situation IS, not what you concluded.
- [ ] **State every live option fairly.** Each gets a neutral factual description — not a framing that leans toward your preferred one. Omitting your conclusion is not enough; a "balanced" brief that still tilts still primes.
- [ ] **De-jargon.** Replace every project / workspace shortform with plain language an outsider reads cold. No rule names, skill names, internal labels.
- [ ] **Situation first.** Present the facts before any question or claim, so the adversary forms its own read before it sees what it is asked to react to.
- [ ] **Demand-characteristics branch.** If the dispatch is testing whether a specific behaviour fires, run `probe-auditor` on the brief FIRST (pass the prompt, the capability tested, and the expected-if-fired output), then dispatch the de-primed version.

If, while writing the brief, you find yourself wanting to include *why your approach is better* — that is the anchor leaking. Strip it and restart this step.

## Step 3 — Leak-check, show the neutral brief, then dispatch

You cannot audit your own de-priming — you share the anchor, and a brief that *feels* balanced to you routinely leaks its preferred answer (proven repeatedly: a producer rated their own brief neutral while a fresh reader found a high-confidence lean). So de-priming is never self-certified — it is checked by a fresh reader, then shown to the user.

1. **Leak-check (mandatory, before any dispatch).** Dispatch `brief-leak-auditor` on the de-primed brief. It reads only the brief and judges whether it betrays your lean. If it finds one: rewrite the leaning passage (use its neutral rewrite) and re-audit until it passes. Do NOT skip this on the grounds that "my brief is already neutral" or "the adversary will catch any lean anyway" — that is the exact rationalisation that defeats the gate; the producer's self-assessment is the unreliable thing this step exists to replace.
2. **Show the user the neutral brief.** Print it as a fenced block whose FIRST line is literally `[DEPRIMED-BRIEF]`, headed "NEUTRAL BRIEF FOR THE ADVERSARY", and end with one line: *"Does this brief tell the adversary what to find? Redirect if so."*
3. **Dispatch** the chosen primitive with `[DEPRIMED-BRIEF]` as the literal first line of the Agent prompt, followed by the leak-checked neutral brief. (The gate hook reads that tag; absent it, the gate reminds you to de-prime and leak-check.)
4. For every primitive EXCEPT `blank-slate-advisor` (which carries Claire internally), add one attack-license line to the dispatch: the adversary's job is to find the strongest *real* objection, not to be agreeable; agreement is allowed only on its own independent reasoning.

**Fallback when a chosen primitive's agent isn't loaded** (e.g. pulled-but-not-restarted): dispatch the built-in `Plan` agent on Opus, using that agent's definition body **VERBATIM** as the preamble (never paraphrased — improvising drifts and drops the agent's guardrails) plus a *"do not use any tools you may have; reason only from the brief"* line, then `[DEPRIMED-BRIEF]` + brief. For `blank-slate-advisor` specifically see `/claire:blank` step 4.

Return the adversary's output to the user, then offer to unpack any part of it. If the user wants to track whether the call holds up, log it for outcome-scoring: `adv-score.sh add <kind> "<one-line topic>"` (prints an id), and later `adv-score.sh verdict <id> right|wrong|partial`. See README → Outcome scoring.
