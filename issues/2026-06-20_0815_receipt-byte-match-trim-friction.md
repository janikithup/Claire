# Receipt byte-match trips when the caller trims the brief between audit and dispatch — 2026-06-20 08:15

> **RESOLVED by the 0.6.2 gate fix (2026-06-20 10:46).** The deeper version of this — the receipt fingerprinting the auditor's whole prompt vs the gate's after-tag region, bridged by a fuzzy match that both false-alarmed and false-passed — is fixed: receipt and gate now compare the canonical after-tag brief by exact equality, the skills instruct "build once, send byte-identical to both, never edit after," and `CLAIRE_DEBUG` now prints the dispatched-vs-audited diff on a NORECEIPT so a real trim is diagnosable instead of dismissed. The one-line skill reminder this issue asked for is now in challenge Step 3 / blank step 3. (CHANGELOG [Unreleased] → 0.6.2.)

> Triaged from a field debrief. Caller-side, not a gate bug — filed as a small UX-enhancement candidate. Separate change from the ambient-leak fix; not bundled.

## What happened
A `/claire:blank` dispatch tripped `[CLAIRE GATE] NORECEIPT` because the caller trimmed the brief (dropped a `"Two questions:"` header and a closing line) when composing the dispatch, *after* the leak-audit had run on the untrimmed text. The receipt is keyed to the exact audited bytes, so the trimmed dispatch didn't match. Re-dispatching the byte-identical audited text passed.

## Assessment
The gate worked exactly as designed — it caught a real mismatch between what was audited and what was sent. The lesson is caller-side. But it is a recurring, easy slip (a producer naturally tidies a brief while composing the dispatch), so a one-line reminder is cheap insurance.

## Candidate fix (one user-visible change, its own release)
Add a line to the `challenge` / `blank` skills near the dispatch step: **"Dispatch the critic the byte-identical text you audited — do not re-tidy, trim, or re-wrap the brief after the leak-audit, or the receipt won't match."** Relates to the v0.5.3 "audit the assembled brief" rule (same family: what's audited must equal what's dispatched).
