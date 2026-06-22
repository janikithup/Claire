# How the de-priming is enforced — the gate and the modes

This is the canonical reference for *how* Claire enforces the de-priming spine (the
one rule in `CLAUDE.md`). The design history — why this replaced an earlier
fingerprint-matching gate — lives in `injection-redesign.md`; this file describes the
behaviour as it stands.

## The gate

The spine is not left to good intentions; a hook enforces it. Before any of Claire's
own critics runs, the **de-priming gate** (`hooks/adversarial-gate.py`, a PreToolUse
hook on the Agent/Task tool) checks that the critic's brief was leak-audited clean.

- **The receipt/injection handshake.** A clean leak-audit writes a short-lived
  *receipt* holding the exact audited brief, keyed by a one-off id the orchestrator
  carries on both the audit and the critic dispatch (`[CLAIRE-RECEIPT:<id>]`). On
  dispatch the gate looks the id up and **overwrites the critic's prompt with the
  stored audited brief** — so the critic provably reasons only from text the checker
  cleared, never from whatever the (anchored) orchestrator wrote. The receipt is
  written by `hooks/record-audit-receipt.py` (a PostToolUse hook); on Claude Desktop a
  plugin's PostToolUse hook does not fire, so the writer is *also* registered in user
  settings by `setup-receipts.sh`.

- **Detection is exact identity only.** The gate treats a dispatch as a de-priming
  dispatch in exactly two cases: the agent type is one of Claire's own
  `claire:`-namespaced critics, or the prompt carries a `[CLAIRE-RECEIPT]` marker.
  There is **no keyword/phrase matching** — a guesser that fired on words like "devil's
  advocate" both false-positived on unrelated work and false-negatived on real
  critiques that missed the magic words. So the gate guards Claire's *own* critics by
  name, not the act of seeking criticism through any agent. (The keyword net was
  removed in 0.12.0.)

- **Two failure states.** A de-priming dispatch with **no** receipt id is a **REMIND**;
  one carrying an id but **no fresh clean** receipt is a **NORECEIPT**. Both mean the
  leak-check was skipped or never passed.

- **Block by default.** Both failure states **deny** (PreToolUse deny) by default — a
  skipped or failed de-priming hard-stops. This is safe to default on *because*
  detection is exact identity: a block can only ever land on a genuine Claire dispatch,
  never on unrelated work.

- **Fail-open on error.** Any *error* inside the gate lets the dispatch through
  silently — a gate bug must never block real work. This is distinct from block-by-
  default: a correctly-detected skipped de-priming blocks; an exception allows.

The lockout to know about: with block-by-default, an install that is **not writing
receipts** (e.g. the PostToolUse writer was never registered) denies *every* audited
dispatch — Claire becomes unusable until the writer is wired in (`setup-receipts.sh`)
or the gate is softened (below). `/claire:doctor` diagnoses exactly this.

## Modes (environment variables)

All three are off / unset by default.

- **`CLAIRE_GATE_STRICT` — block mode.** Block-by-default is on whenever this is unset
  or set to anything other than `0`/`false`. Set **`CLAIRE_GATE_STRICT=0`** to soften
  both failure states back to advisory warnings (the dispatch proceeds) — the escape
  hatch for an install whose receipts aren't landing. (`=1` is still accepted and means
  the same as the default; the meaningful setting now is `=0`.)

- **`CLAIRE_DEBUG` — debug mode.** Surfaces the machinery: `[CLAIRE TRACE]` lines from
  the gate and receipt writer showing the decision, nonce, and verdict. Off by default;
  a normal install never sees traces. Only changes what is *shown*, never how the brief
  is de-primed.

- **`CLAIRE_AUTO` — autonomous mode.** For long unattended / AFK runs: when armed, a
  standing per-judgement-call instruction is injected so Claire fires on every judgement
  call instead of waiting to be invoked. Off by default; interactive use is invoke-only.

(Path overrides — `CLAIRE_DIR`, `CLAIRE_AGENTS`, `CLAIRE_ISSUE_DIR`, `CLAIRE_LOG_DIR`,
`CLAIRE_MARKETPLACE_DIR`, and the test-only `CLAIRE_TEST` — are wiring, not modes.)
