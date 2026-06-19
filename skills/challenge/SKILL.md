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
- [ ] **Strip authorship signals.** Don't reveal that you (or whoever is asking) built or authored the thing under review — present it as found or third-party. A reviewer who can tell the author is the one asking softens the critique no matter how neutral the wording is; intimate "here's exactly how it works" detail leaks authorship just as a stated opinion would. (Surfaced 2026-06-17 when Claire's own leak-auditor passed a review brief as neutral but flagged the residual authorship-leak.)
- [ ] **Situation first.** Present the facts before any question or claim, so the adversary forms its own read before it sees what it is asked to react to.
- [ ] **Demand-characteristics branch.** If the dispatch is testing whether a specific behaviour fires, run `probe-auditor` on the brief FIRST (pass the prompt, the capability tested, and the expected-if-fired output), then dispatch the de-primed version.

If, while writing the brief, you find yourself wanting to include *why your approach is better* — that is the anchor leaking. Strip it and restart this step.

## Step 3 — Leak-check, show the neutral brief, then dispatch

You cannot audit your own de-priming — you share the anchor, and a brief that *feels* balanced to you routinely leaks its preferred answer (proven repeatedly: a producer rated their own brief neutral while a fresh reader found a high-confidence lean). So de-priming is never self-certified — it is checked by a fresh reader, then shown to the user.

1. **Leak-check (mandatory, before any dispatch).** Dispatch `brief-leak-auditor` with the brief body **and nothing else** — no wrapper instructions, no "please audit this"; the persona is in the agent file, and the receipt mechanism below fingerprints exactly the text you send, so extra wrapping breaks the match. The auditor reads only the brief and judges whether it betrays your lean. Do NOT skip this on the grounds that "my brief is already neutral" or "the adversary will catch any lean anyway" — that is the exact rationalisation that defeats the gate; the producer's self-assessment is the unreliable thing this step exists to replace. (Mechanism, v0.2.0: a clean verdict writes a short-lived *receipt* — a fingerprint of the passed brief. The gate checks for that receipt, **not** the tag. Typing `[DEPRIMED-BRIEF]` without an actual clean audit no longer silences the gate — so there is no shortcut around this step.)

   **Audit the FULLY ASSEMBLED brief — everything the critic will receive, artifact included.** When the thing under review is a document you paste in — a plan, a draft, a chapter — assemble the whole brief *first* (your framing **plus** that pasted document), then audit *that*. The text you audit must be byte-identical to the text you send the critic after the `[DEPRIMED-BRIEF]` line. Do **not** audit the framing alone and inline the document afterwards: the document reaches the critic, so a lean hidden inside it (an "the author is sure X" aside, a "previous reviewers agreed" note) is exactly what the leak-check exists to catch — and the gate will (correctly) warn `NORECEIPT` on a brief whose pasted bulk was never audited, because from the gate's view that is indistinguishable from auditing a small decoy and dispatching a large leaky brief. The artifact is not exempt from the check; it is the most important part of it.

   **When the brief does NOT pass first try — the fix loop is bounded and ends in escalation, never silent proceed:**
   - The auditor returns `LEAN-<x>`, the exact tells, and a neutral rewrite of the leaning passage. **Paste its rewrite verbatim** into the brief — do not re-write the passage yourself; you are the anchored party and a fresh self-rewrite re-introduces the lean it just caught. The auditor only rewrites the passage it flagged, so re-read the *rest* of the brief against its tells too.
   - **Re-audit. Cap at 2 rewrite cycles (3 audits total).** Each re-audit may surface a *different* lean — that is normal, not failure; apply its rewrite and continue within the cap.
   - **If it still leans after the cap, STOP — do not proceed silently.** That persistent lean is the signal that you are too anchored on this topic to neutralise it yourself. Surface it to the user in plain language: show the current brief, name the lean the auditor keeps finding, and say you cannot neutralise it in the allotted tries. Then offer the user the call — reframe it themselves, hand the raw situation to `blank-slate-advisor` (which forms its own frame and is immune to a brief's lean because it shares none of your stake), or proceed knowingly with the lean acknowledged. The point of the cap is to convert "loop forever / give up quietly" into "a human decides, with the lean named."
2. **Show the user the neutral brief.** Print it as a fenced block whose FIRST line is literally `[DEPRIMED-BRIEF]`, headed "NEUTRAL BRIEF FOR THE ADVERSARY", and end with one line: *"Does this brief tell the adversary what to find? Redirect if so."*
3. **Dispatch** the chosen primitive **by its namespaced name** — `claire:failure-mode-attacker`, `claire:blank-slate-advisor`, etc. — never the bare name. A workspace may have its own same-named local agent that would otherwise shadow Claire's and silently run instead; the `claire:` prefix guarantees you get Claire's version, and it is also what lets the de-priming gate recognise the dispatch. Structure the Agent prompt so that **everything after the `[DEPRIMED-BRIEF]` line is EXACTLY the leak-checked brief the auditor cleared, verbatim, and nothing else** — any persona preamble or attack-license line goes BEFORE the `[DEPRIMED-BRIEF]` line, never after the brief. The gate matches the post-tag text against the audit receipt; text appended after the brief weakens that match and can trip a false reminder. The gate passes silently only when a fresh receipt covers this brief; a tag with no receipt, or no tag at all, draws a reminder (or a hard block if `CLAIRE_GATE_STRICT=1` is set on this machine).
4. For every primitive EXCEPT `blank-slate-advisor` (which carries Claire internally), add one attack-license line **before the `[DEPRIMED-BRIEF]` line** (with any persona preamble): the adversary's job is to find the strongest *real* objection, not to be agreeable; agreement is allowed only on its own independent reasoning.

**Fallback when a chosen primitive's agent isn't loaded** (e.g. pulled-but-not-restarted): dispatch the built-in `Plan` agent on Opus, using that agent's definition body **VERBATIM** as the preamble (never paraphrased — improvising drifts and drops the agent's guardrails) plus a *"do not use any tools you may have; reason only from the brief"* line, then `[DEPRIMED-BRIEF]` + brief. For `blank-slate-advisor` specifically see `/claire:blank` step 4.

**Debug mode (`CLAIRE_DEBUG`).** If a `[CLAIRE TRACE]` block appears in your context, the user has turned the debug switch on and wants to see the machinery. After Claire's read, add a clearly-marked **TRACE** section that surfaces the apparatus: the `brief-leak-auditor` verdict verbatim, the gate/receipt `[CLAIRE TRACE]` lines, and the raw dispatch (the agent name and the exact brief sent). When no `[CLAIRE TRACE]` block is present (normal use), keep all of that behind the scenes — show only the neutral brief and Claire's read. The switch only changes what is *shown*; it never changes how the brief is de-primed or how the critic is dispatched.

Return the adversary's output to the user, then offer to unpack any part of it. If the user wants to track whether the call holds up, log it for outcome-scoring: `adv-score.sh add <kind> "<one-line topic>"` (prints an id), and later `adv-score.sh verdict <id> right|wrong|partial`. See README → Outcome scoring.
