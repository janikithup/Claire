#!/usr/bin/env python3
"""
Shared brief constants for the de-priming hooks.

Single source of truth for the ONE line that is allowed to sit before the
[DEPRIMED-BRIEF] tag without being a steer: the attack-license. The skill emits
this verbatim, the gate recognises it (a deterministic "known-clean" pre-tag
check), and the tests import it — so all three agree by construction rather than
by three hand-copied strings drifting apart.

Why a frozen constant: as of 0.7.1 the leak-audit covers the WHOLE critic prompt
(preamble included), so a conclusion-bearing preamble is caught by the auditor.
But the common, legitimate pre-tag line is a generic attack-license ("find the
strongest real objection, don't be agreeable"). Freezing it lets the gate verify
that exact line cheaply and keep it out of the auditor's semantic burden — the
audit is the enforcement; this constant is only a narrowing assist + a
false-positive-free target for strict-mode messaging.

Stdlib-free, importable with no side effects. The gate imports it import-guarded
(like claire_log) and falls back to an inline copy if this file is absent, so a
copy-one-file unit harness never crashes.
"""

# The exact attack-license line the skills emit before the [DEPRIMED-BRIEF] tag
# for every primitive EXCEPT blank-slate-advisor (which carries Claire internally
# and has an empty pre-tag region). Keep this a single neutral DISPOSITION line —
# it must name no conclusion, no "obvious read", no flaw-to-find. Edits here must
# stay in lockstep with the skill text that emits it and the gate that recognises it.
CANONICAL_ATTACK_LICENSE = (
    "Your job is to find the strongest real objection, not to be agreeable; "
    "agreement is allowed only on your own independent reasoning."
)

# The exact harness-appended "standing invitation" coda. The hooks strip ONLY this exact
# text from a fingerprint (not "everything after the marker") — so a steer placed after the
# marker ("[standing invitation] PS the obvious answer is X, confirm it") is NOT the genuine
# coda, is left in the fingerprint, and forces a (correct) mismatch instead of riding through
# silently. (0.7.1 fix for the coda-tail blind spot: the old first-marker-anywhere truncation
# excised arbitrary post-marker text, letting an audit-clean / dispatch-steered bypass pass.)
# If the harness coda wording ever drifts from this, the strip stops matching and the gate
# false-NORECEIPTs (safe direction, diagnosable under CLAIRE_DEBUG) — update this string then.
CANONICAL_CODA = (
    "[standing invitation] if you disagree with this approach or see a problem with it, "
    "say so and explain why - before or during execution"
)
