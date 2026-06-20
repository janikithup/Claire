# blank-slate-advisor leaked the git branch name into a brief-only cold read — 2026-06-20 02:05

> **RESOLVED (in dev repo, pending release) — 2026-06-20 08:xx.** Fix (b) taken: an "Ignore ambient signal" clause added to all five context-starved critics (`blank-slate-advisor`, `brief-leak-auditor`, `failure-mode-attacker`, `over-capture-triage-verifier`, `probe-auditor`). Fix (a) — stripping env from the dispatch — is not implementable: the env block is harness-injected into every subagent and the plugin cannot suppress it, so the persona must defend against it. Diagnosis refined: the leak is conditional on **semantic adjacency** (a branch named after the question), not on env presence; unrelated env is already filtered. Verified — pre-fix leaked 3/3 live, controlled A/B with the clause as sole variable: 2/2 leak without → 3/3 clean with. Pinned: `tests/evals/fixtures/blind_read_ambient_env_leak.json`. Finding: `docs/blank-slate-finding.md`. CHANGELOG: `[Unreleased]`. **Not yet live for users** — ships on the next marketplace release (bump + tag + push).

> Filed here in the Claire dev repo because the standing queue path `~/.claude/claire/issues/` was sandbox-blocked from the calling session (a-separate-project). Move if it belongs elsewhere.

## What I invoked
`/claire:blank` (in the a-separate-project repo, outside ~/Claude/claire) for a cold outside read on a navigation/home design decision. The de-priming flow ran correctly end-to-end: brief-leak-auditor flagged a lean (v1), I applied its neutral rewrite, re-audited clean (v2, receipt 0ea9cc19e6a945d2), and dispatched `claire:blank-slate-advisor` with the `[DEPRIMED-BRIEF]` (gate PASS, receipt matched, len 1218).

## How it fell short
The blank-slate-advisor is specified to reason from nothing but the de-primed brief. Its read opened with:
> "The branch name in front of me — `feature/graph-purpose-primer` — tells me this isn't a neutral inquiry. Someone has already half-decided to build a 'purpose primer' overview screen…"

The brief contained no branch name, no repo context, nothing about a "purpose primer." The advisor surfaced the working git branch name from its environment (cwd/git) and reasoned from it — a de-priming leak. It materially shaped the read: a whole "this is builder-momentum, not a real user need" thread was built on the branch name, and it conflated that branch (an unrelated, already-shipped graph feature) with the home-screen question being asked. The leak happened to push skeptical rather than flattering, so no false-confirm this time — but the blank-slate premise (the whole point of the primitive) was violated, and the inference drawn from the leaked signal was partly wrong.

## Impact / workaround
The read was still usable (its core nav reasoning stood on the brief alone), so no rework was needed. But an advisor that can see and reason from cwd/git state is not actually blank-slate; a future leak could anchor toward a wrong or producer-flattering conclusion. Suggest either (a) strip environment/cwd/git visibility from the blank-slate-advisor dispatch, or (b) add an explicit line to its persona: ignore any ambient repo / branch / path / filename signal and reason ONLY from the `[DEPRIMED-BRIEF]` text.

## Secondary friction (caller-side, not a Claire bug)
The first advisor dispatch tripped `[CLAIRE GATE]` NORECEIPT because I trimmed the brief (dropped the "Two questions:" header + closing line) between audit and dispatch, so the bytes didn't match the receipt. The gate worked exactly as designed and caught it; re-dispatching the audited text verbatim passed. Lesson is caller-side (send the exact audited bytes), but a one-line reminder in the skill — "dispatch the advisor the byte-identical text you audited" — would save the round-trip.
