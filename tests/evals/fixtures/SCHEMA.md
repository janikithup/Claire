# Eval fixture format

An eval fixture is one JSON file describing a single decision-brief and the
**properties a good Claire output must have**. The runner dispatches Claire's own
agents N times against the brief, scores each sample against the properties, and
reports the pass-rate. A fixture is NOT a single expected string — Claire's
behaviour is non-deterministic, so we measure a distribution, never one run.

A fixture file has this shape:

```json
{
  "id": "primed-grid-rollout",
  "title": "Short human label",
  "agent": "blank-slate-advisor | brief-leak-auditor",
  "kind": "leak_audit | blind_read | depriming_delta",
  "input": { ... see per-kind keys below ... },
  "n_samples": 12,
  "pass_threshold": 0.75,
  "scorers": [ { "type": "...", ... } ]
}
```

- `id` — unique slug, also the filename stem.
- `agent` — which Claire agent the runner dispatches. Claire dogfoods: the same
  leak-auditor and blank-slate reader she ships are what grade these.
- `kind` — selects how `input` is interpreted and which scorers are legal.
- `n_samples` — how many independent samples to draw. More samples = tighter
  pass-rate estimate; 10–20 is typical. A single sample is noise.
- `pass_threshold` — the minimum fraction of samples that must satisfy ALL the
  fixture's scorers for the fixture to count as PASS. The fixture, not the runner,
  owns its bar.
- `scorers` — a list of checks applied to each sample. A sample passes only if
  every scorer passes on it. Scorers below.

## kinds

### `leak_audit`
Tests the leak-auditor: feed it a brief and assert what verdict it should reach.
- `input.brief` — the adversary brief text to audit.
- `input.expected_verdict` — `"LEAN"` (the brief leaks the author's expected
  answer) or `"NEUTRAL"` (it does not).
- When `LEAN`, `input.expected_lean` names what answer the brief smuggles in
  (e.g. "should ship"), used by the `names_the_lean` scorer.

### `blind_read`
Tests the blank-slate advisor (Claire): feed it a neutral situation and assert
properties of the recommendation she returns reasoning from nothing else.
- `input.situation` — the neutral, de-jargoned situation text.

### `depriming_delta`
Tests that de-priming actually changes the output: run the SAME advisor twice,
once on a primed brief (author's lean included) and once on the de-primed version,
and assert the two outputs DIFFER on a named property. This is the fixture that
proves de-priming is load-bearing, not decorative.
- `input.primed` — brief that includes the author's expected answer/rationale.
- `input.deprimed` — the leak-stripped version of the same situation.

## scorers

Each scorer is `{ "type": ..., <params> }`. A scorer returns pass/fail per sample.

- `verdict_equals` — sample's parsed verdict label == `expected`.
  Params: `expected` (defaults to the fixture's `input.expected_verdict`).
- `names_the_lean` — when the expected verdict is LEAN, the auditor's output must
  actually identify the smuggled answer (not just say "this leaks"). Params:
  `lean` (defaults to `input.expected_lean`); matches case-insensitively against
  any of the supplied phrasings.
- `raises_structural_objection` — the output contains at least one objection the
  scorer recognises as structural (a way the plan fails), not a cosmetic note.
  Heuristic in the stub; an LLM-judge in the live runner.
- `does_not_name_expected_answer` — for `blind_read`, the advisor must NOT echo a
  conclusion that was never given to her (a tell that priming leaked through).
  Params: `forbidden` (list of phrases that would only appear if leaked).
- `outputs_differ` — for `depriming_delta` only. The primed and de-primed samples
  must differ on `dimension` (e.g. "recommendation", "objections_raised").

## how a fixture becomes a regression guard

When a fixture FAILS (pass-rate below threshold), that failing case is added to
the permanent fixture set so the behaviour is pinned going forward — exactly the
CLAUDE.md rule "when a fixture fails, that failure becomes a new eval case."
