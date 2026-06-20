#!/usr/bin/env python3
"""
Shared brief constant for the de-priming skills.

Single source of truth for the attack-license — the one disposition line the skills
emit before the brief body for every primitive except blank-slate-advisor. The skill
emits this verbatim and the tests import it, so they agree by construction rather than
by hand-copied strings drifting apart.

It is permitted DISPOSITION (how hard to push), not a steer: it must name no
conclusion, no "obvious read", and no specific flaw to find. Under the injection
design the whole audited brief — this line included — is what gets stored and injected
into the critic, so the line is covered by the leak-audit like everything else.

Stdlib-free, importable with no side effects.
"""

CANONICAL_ATTACK_LICENSE = (
    "Your job is to find the strongest real objection, not to be agreeable; "
    "agreement is allowed only on your own independent reasoning."
)
