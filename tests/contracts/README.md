# tests/contracts/ — frozen external contracts

Files here are **frozen, transcribed copies of external schemas** the Claire plugin
must conform to — kept deliberately *separate from Claire's own code* so a test can
check Claire against an independent source of truth, not against the same source that
produced a bug.

This is the point of dev-aid #1 in `~/.claude/claire/issues/2026-06-21_0034_devaids-backlog.md`:
most ways of catching the "gate dropped a required field" bug keep working from the same
source as the bug. Only a contract validated against an *external* schema imports an
independent check.

## agent_tool_input.schema.json

The Claude Code **Agent / Task** tool input schema (the fields that tool requires).
Claire's de-priming gate (`hooks/adversarial-gate.py`) rewrites the whole Agent
`tool_input` when it injects an audited brief; if the rewrite drops a field the harness
*requires*, the harness rejects the dispatch **after** the gate's fail-open net — a hard
block that shipped broken in 0.8.0/0.8.1 and was hotfixed in 0.8.2 (the dropped
`description` field).

`tests/unit/test_gate_inject_contract.py` validates the gate's output against this file.

**When the Agent tool schema changes upstream:** update this file (and bump the date in
its `_source`), then run the unit suite. A failing contract test means **fix the gate**,
not weaken this file — unless the harness genuinely dropped a requirement.
