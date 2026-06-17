# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2026-06-17

### Fixed
- **Receipt-backed de-priming enforcement now actually fires on the Claude Desktop app.** The receipt writer is a PostToolUse hook, and a plugin's PostToolUse hooks do not fire on Desktop (its PreToolUse hooks do) — so no receipt was ever written, the gate could never go silent, and de-priming degraded to an unconditional nag on every dispatch. Three fixes land together: (1) a new **`setup-receipts.sh`** registers the receipt writer in `~/.claude/settings.json`, where PostToolUse hooks *do* fire — run it once per machine; the registration is uninstall-safe (a missing script becomes a no-op, never a hang) and idempotent. (2) The clean-vs-leaning verdict is now read **by position**: the leak-auditor discusses leans even when it passes (e.g. "I considered a faint LEAN-One but am declining … GENUINELY-NEUTRAL"), so a clean pass is recognised by `GENUINELY-NEUTRAL` appearing *before* any `LEAN-<option>` token, instead of scanning for the word "lean" anywhere and wrongly suppressing the receipt. (3) Both hooks **strip the harness-appended "[standing invitation]" coda** before fingerprinting — it is added to a subagent prompt between the gate's read and the receipt writer's read, and would otherwise make the two fingerprints never match. `/claire:doctor` now checks the settings.json registration. Verified end-to-end live.
- `.gitattributes` pins LF line endings on `.sh`/`.py` (and all text) so the scripts run on Linux regardless of a checkout machine's git `autocrlf` setting — a seedbox clone had received CRLF-mangled scripts that failed to execute.

## [0.4.1] - 2026-06-17

### Changed
- Cleaner plugin description — dropped the internal hook/receipt mechanics from the user-facing blurb.

### Added
- `docs/design-principles.md` — the *why* behind how Claire shows her critic (synthesize on agreement, preserve on disagreement; translate, never outvote) and why the brief gets a separate audit rather than self-certification, captured from findings during the build.
- A "Where the name comes from" note in the README (the `.claire` typo origin and the Challenge Officer title).
- ROADMAP items D (make her presence felt) and E (a `CLAIRE_DEBUG` hatch); a presentation rule + pointer in `CLAUDE.md`.

## [0.4.0] - 2026-06-17

### Added
- **`/claire:doctor`** — a health- and conflict-check for a Claire install. Filesystem checks (dependencies, install integrity, **duplicate installs**, agent-name collisions with the current workspace, leftover old tools) via `doctor.sh`, plus a **live self-test** that dispatches the leak-auditor and confirms a receipt is written — i.e. that de-priming enforcement is actually firing on this machine, which tells you whether strict mode is safe to enable here.

### Changed
- **The de-priming gate now acts only on Claire's own (`claire:`-namespaced) critics**, not on a workspace's same-named local agents. Installing Claire no longer injects de-priming reminders into an unrelated project that happens to have its own `failure-mode-attacker` (etc.), and her skills now dispatch the `claire:`-prefixed agents so she always uses her own version even where a same-named local agent exists. The doctor's live self-test is the per-machine backstop if a harness ever fails to namespace.

## [0.3.0] - 2026-06-17

### Added
- **Chat edition** (`chat/`) — a prompt-only custom Agent Skill that brings Claire's de-priming discipline and cold-critic persona to regular Claude chat (claude.ai / the Claude apps), where hooks and separate subagents don't exist. It de-primes in two visible phases within one conversation, and is honest that it's the discipline, not the enforced separation of the plugin. Install via claude.ai → Settings → Skills, or paste into a Project's custom instructions. See `chat/README.md`.

## [0.2.1] - 2026-06-17

### Fixed
- **The gate no longer fires on the leak-auditor itself.** A brief that quoted the `[DEPRIMED-BRIEF]` tag or used the word "deprimed" tripped the backstop word-match (`deprime` matched inside `deprimed`), so dispatching `brief-leak-auditor` — the de-priming *checker* — drew a false warning. The checker is now never gated, and the phrase backstop matches only at word boundaries, so ordinary discussion of de-priming no longer false-triggers.

### Added
- **Strip-authorship-signals** step in the de-priming checklist (`/claire:challenge`): don't reveal that the asker built the thing under review — a reviewer who can tell the author is asking softens the critique regardless of wording. Surfaced by Claire's own leak-auditor, which passed a review brief as neutral but flagged the residual authorship-leak.
- Regression tests for the leak-auditor-never-gated and word-boundary cases.

### Changed
- CI: validate only `plugin.json` (and assert `marketplace.json` stays absent, as the clone-install requires); run the project's own test runner instead of pytest. Fixes the red `validate-manifests` job left over from removing `marketplace.json`.

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

[Unreleased]: https://github.com/janikithup/Claire/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/janikithup/Claire/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/janikithup/Claire/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/janikithup/Claire/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/janikithup/Claire/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/janikithup/Claire/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/janikithup/Claire/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/janikithup/Claire/releases/tag/v0.1.0
