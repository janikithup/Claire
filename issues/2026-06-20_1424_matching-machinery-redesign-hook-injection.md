# Replace fingerprint-matching with hook-injection of the canonical brief — SPRINT KICKOFF — 2026-06-20 14:24

> **This is the next sprint.** 0.7.1 shipped (closes the pre-tag channel via whole-prompt audit + fingerprint-matching). This sprint removes the *fingerprint-matching itself* — the brittle layer that has generated every spine "mole" (coda asymmetry → pre-tag preamble → coda-tail → tag-quoting false-NORECEIPT → valence under-catch). Replace it with a deterministic hook that INJECTS the audited brief into the critic.

## Why (the recurring hole-shape)
The de-priming gate today proves "audited == dispatched" by computing a normalised text *fingerprint* of the brief on both sides (`brief_region`, `strip_coda`, excise-tags, `is_clean_verdict`) and comparing by exact equality. Every hole has been an edge case in that normalisation — because the orchestrator builds the auditor-text and critic-text *separately* and the harness mutates one (the coda). Patching normalisation is whack-a-mole.

## The mechanism (TESTED VIABLE — 2026-06-20)
A PreToolUse hook's `updatedInput` **does** rewrite a subagent's prompt — confirmed when the hook is loaded at **session start** (a subagent answered the rewritten arithmetic `10 + 10` → 20; a Read `file_path` rewrite A→B also took effect). The earlier same-session negative was a mid-session-load confound. Recorded in internal hook-design notes (2026-06-20).

## The design
- On a CLEAN leak-audit, the canonical de-primed brief is the **single source of truth** (the receipt *is* the brief, not a fingerprint of it).
- A PreToolUse gate hook on the critic dispatch **injects** that canonical brief — the **whole critic prompt, persona included** — via `updatedInput`, overwriting whatever the orchestrator supplied.
- Consequences: the critic stays **fully tool-less** (maximum context-starvation, no file access — beats the deny-pinned-file fallback); the orchestrator **cannot** send un-audited text (the hook replaces it); and the entire `strip_coda` / excise-tags / `brief_region` / fingerprint-match machinery — every mole's habitat — is **deleted**.

## Build-time confirms (do these first — each is load-bearing)
1. **Plugin-hook `updatedInput` propagation.** The 2026-06-20 test used a PROJECT `settings.json` hook. Claire ships as a plugin (`hooks/hooks.json`). Plugin PreToolUse fires on Desktop (wiki line 29) but plugin-hook *rewrite* propagation is untested — confirm before building on it. The hook must be present at session START (mid-session add fires but doesn't rewrite).
2. **The handshake.** How the injection hook knows WHICH audited brief to inject for a given dispatch — a receipt-id the orchestrator passes, that the hook looks up. Design this so an orchestrator can't point it at the wrong/forged receipt.
3. **Whole-prompt injection.** Inject the entire critic prompt (persona + brief) from a canonical template, not just a brief-slot — else a steer in the surrounding instructions survives.

## Fold in (0.7.1 known residuals — close them in this redesign)
- **Plan/Explore fallback ungated.** Non-`claire:`-typed dispatch the gate never fires on; de-priming there is honour-system. The injection hook's matcher must cover (or the design must address) this path.
- **`is_clean_verdict` verdict-parser fail-closed echo.** The 48-char/keyword heuristic false-warns when a clean audit echoes the literal `LEAN-…` example. Same brittle-heuristic family — anchor verdict parsing to the auditor's declared verdict LINE (the contract puts it first) instead of scan-anywhere.

## Test/eval plan
- Two-layer per CLAUDE.md: the injection hook is **plumbing** → unit-test test-first (does the canonical brief reach the critic byte-for-byte? does a forged/mismatched receipt-id get rejected? does a steer in orchestrator-supplied text get overwritten?). The auditor's neutrality judgement stays **eval-gated** (the 3-arm fixtures carry over).
- Re-gate adversarially in a fresh context before shipping, exactly as 0.7.1 was.

## History / pointers
- Pre-tag channel + 0.7.1 fix: `issues/2026-06-20_1046_pre-tag-preamble-unaudited-channel.md` (resolved by 0.7.1).
- Tested mechanism + the startup-load caveat: internal hook-design notes (2026-06-20).
- Reusable re-gate harness: `tests/evals/regate_0_7_1.js`.
