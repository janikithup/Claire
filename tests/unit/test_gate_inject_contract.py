#!/usr/bin/env python3
"""
UNIT TEST — de-priming gate OUTPUT contract against a FROZEN EXTERNAL schema.

dev-aid #1 (devaids backlog, 2026-06-21). The gate's injection path REPLACES the whole
Agent/Task tool_input via updatedInput. The class of bug that shipped broken twice
(0.8.0/0.8.1, hotfixed 0.8.2) was the replacement DROPPING a field the harness REQUIRES
('description'), so the harness rejected the dispatch downstream of the gate's fail-open
net — a hard block worse than not injecting.

Why a SCHEMA contract and not just `assert ui['description']`:
test_gate_injection.py::test_inject_preserves_required_dispatch_fields already pins the ONE
field we know broke. That works "from the same source as the bug" — it only catches what the
author remembered. THIS test validates the gate's output against an INDEPENDENT, frozen copy
of the Agent tool's input schema (tests/contracts/agent_tool_input.schema.json). If the gate
ever drops ANY required field — or the harness adds a new required field (you update the
frozen file) the gate doesn't carry — this reports it, without the author predicting which.

Layer: deterministic plumbing (unit-tested), per CLAUDE.md "two layers, two ways of testing".
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.abspath(os.path.join(HERE, "..", "contracts", "agent_tool_input.schema.json"))

# Reuse the canonical gate driver from the injection test — one harness, no duplication.
# Insert HERE so the import resolves under the bare _runner, direct exec, and pytest alike.
sys.path.insert(0, HERE)
from test_gate_injection import run_gate, _hook_out  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


_TYPES = {"string": str, "boolean": bool, "object": dict, "number": (int, float), "array": list}


def validate(obj, schema):
    """Tiny zero-dependency validator: required-presence (non-empty) + declared type.
    Returns a list of violation strings; [] means valid. Deliberately small — the suite
    runs on a bare python3 with no jsonschema package (see tests/unit/_runner.py)."""
    if not isinstance(obj, dict):
        return ["payload is not an object"]
    out = []
    for field in schema.get("required", []):
        if field not in obj:
            out.append("missing required field: %s" % field)
        elif obj[field] is None or obj[field] == "" or \
                (isinstance(obj[field], str) and not obj[field].strip()):
            out.append("required field is empty: %s" % field)
    for field, spec in schema.get("properties", {}).items():
        if field in obj and obj[field] is not None:
            want = _TYPES.get(spec.get("type"))
            if want and not isinstance(obj[field], want):
                out.append("field %s: expected %s, got %s"
                           % (field, spec.get("type"), type(obj[field]).__name__))
    return out


def _full_dispatch(prompt):
    """A COMPLETE Agent dispatch — description + prompt + subagent_type — as a real critic
    call carries. The contract is about PRESERVING the fields the caller actually supplied."""
    return {"tool_input": {
        "subagent_type": "claire:failure-mode-attacker",
        "description": "outside read on the vendor decision",
        "prompt": prompt,
    }}


@case
def test_frozen_schema_is_well_formed_and_demands_description():
    """GUARD: someone 'fixes' a failing contract test by gutting the frozen schema. The
    external source of truth must keep description AND prompt required — this fails if the
    contract file itself is weakened."""
    schema = load_schema()
    assert schema.get("type") == "object", "frozen schema must be an object schema"
    req = schema.get("required", [])
    assert "description" in req and "prompt" in req, \
        "the frozen Agent-tool contract must require description AND prompt; got %r" % req


@case
def test_validator_catches_a_dropped_required_field():
    """GUARD — proves this test has teeth ('would this fail if the bug came back?'). The
    validator MUST report a missing required field; if it passed vacuously the whole contract
    test would be theatre (the exact failure the devaids backlog was filed about)."""
    schema = load_schema()
    # Build a complete input from the schema's OWN required list, so this guard stays valid
    # if the frozen contract legitimately gains a new required field (the maintenance action
    # the schema file's _maintenance note describes) rather than failing with a misleading
    # "complete input must validate clean".
    good = {f: "x" for f in schema.get("required", [])}
    good.setdefault("subagent_type", "claire:failure-mode-attacker")
    assert validate(good, schema) == [], "a complete input must validate clean"
    a_required = schema["required"][0]
    broken = dict(good)
    del broken[a_required]
    viol = validate(broken, schema)
    assert any(a_required in v for v in viol), \
        "validator must flag a dropped required field; got %r" % viol


@case
def test_injected_input_satisfies_frozen_agent_schema():
    """BUG GUARDED (0.8.0/0.8.1 hard-block, hotfixed 0.8.2): the gate's injected updatedInput
    must satisfy the Agent tool's REQUIRED-field contract — validated against the frozen
    external schema, not against the gate's own code. A dropped required field reappears here
    as a contract violation, whichever field it is."""
    brief = "Situation: a team must pick one of two vendors for a year. Outside read?"
    out, _ = run_gate(_full_dispatch("[CLAIRE-RECEIPT:ctr01] decoy steer"),
                      receipts=[("ctr01", brief, 10)])
    ui = _hook_out(out)["updatedInput"]
    assert ui["prompt"] == brief, "prompt must be the audited brief"
    viol = validate(ui, load_schema())
    assert viol == [], "injected updatedInput violates the Agent-tool contract: %s" % viol


@case
def test_injection_preserves_subagent_type_claire_invariant():
    """BUG GUARDED (Claire invariant beyond the bare harness schema): subagent_type is
    OPTIONAL to the harness but load-bearing for Claire — it selects WHICH critic runs. The
    overwrite must keep it, or the audited brief is delivered to the wrong (or default) agent."""
    brief = "Situation: pick a vendor. Outside read?"
    out, _ = run_gate(_full_dispatch("[CLAIRE-RECEIPT:ctr02] x"),
                      receipts=[("ctr02", brief, 10)])
    ui = _hook_out(out)["updatedInput"]
    assert ui.get("subagent_type") == "claire:failure-mode-attacker", \
        "the critic identity (subagent_type) must survive injection"


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
