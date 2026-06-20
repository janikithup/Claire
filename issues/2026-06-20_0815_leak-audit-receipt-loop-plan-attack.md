# Leak-audit "receipt loop" friction on plan-attack briefs — 2026-06-20 08:15

> Triaged from a field debrief. Spine-delicate (roadmap C) — flagged for a design pass, NOT a quick fix. Report 2 said it filed this to Claire's queue but no file landed, so capturing it here.

## What the caller reported
Dispatching a plan to the critic, the gate "kept demanding a leak-audit receipt I never cleared" — the auditor found a lean on every revision of the brief, so the gate stayed armed. The caller's framing: *"for a plan-attack, neutrality isn't even the goal."*

## Assessment (two parts)
1. **The premise is partly mistaken.** The `brief-leak-auditor` is explicitly specified to audit plan-attack briefs — a plan brief can be written to look sound (hiding its weak spots) or to point the attacker at a decoy. So brief-neutrality *does* matter for plan-attacks: the question is whether the brief steers the attacker toward or away from the real weakness. The auditor flagging a lean on a plan brief is not a category error.
2. **But the friction is real.** A gate that re-flags every revision and never clears is bad ergonomics, and `docs/design-principles.md` already prescribes the relief valve: *"the fix loop is bounded and ends in escalation, not endless rewriting. After a small cap of rewrites that still lean, hand the critic the raw, un-optioned question."* The report suggests that escalation path is either not firing, not surfaced to the caller, or not wired into the skills' loop.

## Candidate work (design pass)
- Verify the bounded-rewrite-then-escalate path is actually implemented in the `challenge` skill loop and surfaced to the caller after N leans (what is N? is it shown?).
- Consider a clearer caller-facing message when the auditor flags repeatedly: name the escalation option explicitly ("audited twice, still leans — hand the critic the raw question instead").
- Do NOT weaken the auditor on plan briefs to reduce friction — that is the spine. The fix is the escalation path, not laxer auditing.
