# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-17

### Changed
- **The de-priming gate no longer trusts a self-typed marker.** Previously a critic dispatch carrying the `[DEPRIMED-BRIEF]` marker passed the gate silently — but the main agent types that marker itself, so it could skip the leak-check and still pass. The gate now requires a *receipt* proving the leak-auditor actually cleared the exact brief; the marker alone buys nothing. This closes the loophole an anchored agent used to rationalise past the de-priming step.

### Added
- `record-audit-receipt.py` (PostToolUse hook): writes a short-lived, git-ignored receipt — a fingerprint of the brief — only when `brief-leak-auditor` returns a clean verdict. The gate reads these receipts.
- **`CLAIRE_GATE_STRICT=1`**: opt-in environment variable that makes the gate *block* a critic dispatch lacking a receipt (PreToolUse deny) instead of warning. Off by default, so a public install never hard-blocks; recommended on your own machines.
- **Bounded, escalating fix loop** in `/claire:challenge` and `/claire:blank` for a brief that fails the leak-check: paste the auditor's own neutral rewrite verbatim, re-audit, cap at two cycles, and escalate to the user with the persistent lean named — never silently proceed.
- Unit tests for the receipt writer and the receipt-aware gate (including stale-receipt, decoy-coverage, and strict-mode cases).

## [0.1.0] - 2026-06-17

### Added
- `/claire:challenge` command: routes a plan, claim or decision to the right kind of critic (plan-attacker, cold outside read, actor role-play, source-vs-claim check, two-sides face-off, probe audit), de-priming the brief first.
- `/claire:blank` command: a cold, no-context outside read from a context-starved advisor.
- Seven scoped subagents (blank-slate-advisor, failure-mode-attacker, affected-actor-simulator, brief-leak-auditor, dialectical-scout, over-capture-triage-verifier, probe-auditor).
- `adversarial-gate.py` (PreToolUse hook): reminds the main agent to de-prime and leak-check before an adversarial dispatch. Fail-open.
- `adv-nudge.py` (UserPromptSubmit hook): surfaces a one-line pointer when a prompt reads like a request for a critique. Fail-open.
- `plugin.json` manifest. Deliberately not always-on — nothing fires without an explicit `/claire` invocation.
- MIT License.
- This changelog.

[Unreleased]: https://github.com/janikithup/Claire/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/janikithup/Claire/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/janikithup/Claire/releases/tag/v0.1.0
