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
| A test / probe of whether some behaviour fires — "is this rigged" | `claire:probe-auditor` FIRST (always) |
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
- [ ] **Demand-characteristics branch.** If the dispatch is testing whether a specific behaviour fires, run `claire:probe-auditor` on the brief FIRST (pass the prompt, the capability tested, and the expected-if-fired output), then dispatch the de-primed version. Use the namespaced name — a bare `probe-auditor` resolves to a workspace-local agent of the same name (if one exists) instead of Claire's, and the de-priming gate only fires on the `claire:` form.

If, while writing the brief, you find yourself wanting to include *why your approach is better* — that is the anchor leaking. Strip it and restart this step.

## Step 3 — Leak-check, show the neutral brief, then dispatch

You cannot audit your own de-priming — you share the anchor, and a brief that *feels* balanced to you routinely leaks its preferred answer (proven repeatedly: a producer rated their own brief neutral while a fresh reader found a high-confidence lean). So de-priming is never self-certified — it is checked by a fresh reader, then shown to the user.

1. **Leak-check (mandatory, before any dispatch).** Pick a fresh, unique receipt id — any short token (e.g. `a9f3k2`). Assemble the brief the critic will reason from: any persona / attack-license preamble **plus** the brief body. Dispatch `brief-leak-auditor` with `[CLAIRE-RECEIPT:<id>]` on its own line, then that preamble + body, verbatim (its own persona is in the agent file; it judges whether anything in the preamble *or* the body betrays your lean, and ignores the receipt-id line as ambient). On a clean verdict a short-lived **receipt** is written, keyed by that id, storing exactly the brief the auditor just judged. You then dispatch the critic carrying the **same** `[CLAIRE-RECEIPT:<id>]`, and the gate **injects that stored audited brief into the critic, replacing whatever else is in the dispatch** — so the critic reasons only from text the auditor cleared. Two consequences worth internalising: (a) the brief the **auditor** reads is exactly what the **critic** gets, so audit the brief you actually want critiqued; (b) you do **not** need to keep the critic's prompt identical to the audited one — the gate overwrites it — you need only the same id on both, and a genuinely clean audit. Do NOT skip this on the grounds that "my brief is already neutral", "the adversary will catch any lean anyway", or "the attacker is structurally de-primed — a minimum-context critic can't be steered" — that is the exact rationalisation that defeats the gate; the producer's self-assessment is the unreliable thing this step exists to replace. The third ground is wrong on its own terms: context-starving and leak-checking are **orthogonal** — starvation controls what the critic carries *in* (its own priors), while the leak-audit controls whether the *brief* leans, and the brief is the one channel a starved critic must trust. A starved attacker handed a leaning brief is still steered. (Mechanism: a clean verdict writes the receipt; the gate injects on the **receipt**, not on the id alone. Quoting an id without an actual clean audit writes no receipt, so the gate fails closed — there is no shortcut around this step.)

   **Audit the FULLY ASSEMBLED brief — everything the critic will reason from, artifact included.** When the thing under review is a document you paste in — a plan, a draft, a chapter — assemble the whole brief *first* (your framing **plus** that pasted document), then audit *that*. The brief the auditor reads is exactly what the gate injects into the critic, so a lean hidden inside the document (an "the author is sure X" aside, a "previous reviewers agreed" note) is exactly what the leak-check exists to catch. Do **not** audit the framing alone: the gate injects the **audited** brief, so an un-audited document would never reach the critic — and if you audit a small decoy, only the decoy reaches it. The artifact is not exempt from the check; it is the most important part of it.

   **When the brief does NOT pass first try — the fix loop is bounded and ends in escalation, never silent proceed:**
   - The auditor returns `LEAN-<x>`, the exact tells, and a neutral rewrite of the leaning passage. **Paste its rewrite verbatim** into the brief — do not re-write the passage yourself; you are the anchored party and a fresh self-rewrite re-introduces the lean it just caught. The auditor only rewrites the passage it flagged, so re-read the *rest* of the brief against its tells too.
   - **Re-audit. Cap at 2 rewrite cycles (3 audits total).** Each re-audit may surface a *different* lean — that is normal, not failure; apply its rewrite and continue within the cap.
   - **If it still leans after the cap, STOP — do not proceed silently.** That persistent lean is the signal that you are too anchored on this topic to neutralise it yourself. Surface it to the user in plain language: show the current brief, name the lean the auditor keeps finding, and say you cannot neutralise it in the allotted tries. Then offer the user the call — reframe it themselves, hand the raw situation to `blank-slate-advisor` (which forms its own frame and is immune to a brief's lean because it shares none of your stake), or proceed knowingly with the lean acknowledged. The point of the cap is to convert "loop forever / give up quietly" into "a human decides, with the lean named."
2. **Show the user the neutral brief.** Print it as a fenced block headed "NEUTRAL BRIEF FOR THE ADVERSARY" — the preamble + body exactly as audited — and end with one line: *"Does this brief tell the adversary what to find? Redirect if so."*
3. **Dispatch** the chosen primitive **by its namespaced name** — `claire:failure-mode-attacker`, `claire:blank-slate-advisor`, etc. — never the bare name. A workspace may have its own same-named local agent that would otherwise shadow Claire's and silently run instead; the `claire:` prefix guarantees you get Claire's version, and it is what lets the gate recognise the dispatch. Put `[CLAIRE-RECEIPT:<id>]` — the same id you audited under — in the prompt; the gate looks it up and **overwrites the whole prompt with the stored audited brief**, so nothing else you write in the dispatch reaches the critic. The gate injects silently only when a fresh receipt covers that id; an id with no receipt, or no id at all, draws a reminder (or a hard block if `CLAIRE_GATE_STRICT=1` is set on this machine) — never a silent pass. If you hit a NORECEIPT on an id you believe you audited clean, the audit either did not return clean or the receipt expired (2-hour TTL) — re-audit under a fresh id.
4. For every primitive EXCEPT `blank-slate-advisor` (which carries Claire internally), include the attack-license line in the brief — emitted **verbatim** as the canonical line: *"Your job is to find the strongest real objection, not to be agreeable; agreement is allowed only on your own independent reasoning."* It is the frozen `CANONICAL_ATTACK_LICENSE` (`hooks/claire_brief.py`); it is part of the brief the auditor reads and the critic receives. It must name no conclusion, no "obvious read", and no specific flaw to find — that would be a steer, not a license, and the auditor will (correctly) flag it.

**If a chosen primitive's agent isn't loaded** (e.g. pulled-but-not-restarted): do **not** fall back to a built-in `Plan`/`Explore` agent. That path is not `claire:`-typed, and under injection the gate would overwrite its inlined persona with the audited brief (de-fanging the critic) — a silently degraded critic is worse than none. Instead, tell the user the Claire agents aren't loaded on this machine and to restart so the plugin agents load, then re-run. For `blank-slate-advisor` specifically see `/claire:blank` step 4.

**Debug mode (`CLAIRE_DEBUG`).** If a `[CLAIRE TRACE]` block appears in your context, the user has turned the debug switch on and wants to see the machinery. After Claire's read, add a clearly-marked **TRACE** section that surfaces the apparatus: the `brief-leak-auditor` verdict verbatim, the gate/receipt `[CLAIRE TRACE]` lines, and the raw dispatch (the agent name and the receipt id used). When no `[CLAIRE TRACE]` block is present (normal use), keep all of that behind the scenes — show only the neutral brief and Claire's read. The switch only changes what is *shown*; it never changes how the brief is de-primed or how the critic is dispatched.

Return the adversary's output to the user, then offer to unpack any part of it. If the user wants to track whether the call holds up, log it for outcome-scoring: `adv-score.sh add <kind> "<one-line topic>"` (prints an id), and later `adv-score.sh verdict <id> right|wrong|partial`. See README → Outcome scoring.
