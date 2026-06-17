# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-17

### Added
- `/claire:challenge` command: structured adversarial decomposition of the current argument or plan, backed by a scoped subagent.
- `/claire:blank` command: clean-slate unconstrained reasoning session, unprimed by prior context.
- `PreToolUse` hook: enforces scoping invariants when a claire command is active; no-op otherwise.
- `PostToolUse` hook: post-execution scope cleanup; no-op when no claire command is in flight.
- `plugin.json` manifest with `alwaysOn: false` — no behaviour fires without explicit user invocation.
- `marketplace.json` self-listing with `defaultEnabled: false`.
- MIT License.
- This changelog.

[Unreleased]: https://github.com/janikithup/claire/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/janikithup/claire/releases/tag/v0.1.0
