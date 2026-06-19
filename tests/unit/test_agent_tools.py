#!/usr/bin/env python3
"""
UNIT TEST — claire agent tool-declaration integrity.

BUG GUARDED (found 2026-06-19, filed from a field session that used Claire to
cold-read a long document): three context-starved critics declared `tools: []`.
Empirically an EMPTY tools list is read by the harness as "inherit ALL tools", NOT
"none" — the session registry showed those agents as "All tools", while agents that
declare a real list (e.g. `tools: TaskCreate`) show exactly that. So `tools: []` is a
footgun: an agent whose own prompt says "work entirely from the brief" was silently
granted full tool access, and when pointed at a file path it FABRICATED the file's
contents and critiqued the fiction (tool_uses: 0, caught only by luck).

To restrict an agent, declare the real allowed tools (e.g. `tools: TaskCreate`, the
project's prompt-only marker) or OMIT the field to inherit all tools intentionally —
never `tools: []`. These tests pin both halves at the deterministic (manifest) layer;
the behavioural "refuses to fabricate a missing artifact" property is eval-layer.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "agents"))

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def _agent_files():
    return [os.path.join(AGENTS_DIR, f)
            for f in os.listdir(AGENTS_DIR) if f.endswith(".md")]


def _tools_decl(text):
    m = re.search(r"(?m)^tools:\s*(.+?)\s*$", text)
    return m.group(1).strip() if m else "(absent)"


@case
def test_no_agent_declares_empty_tools_list():
    """An empty `tools: []` is read as ALL tools, not none — the opposite of intent for a
    context-starved critic. No shipped agent may declare it."""
    offenders = []
    for path in _agent_files():
        with open(path) as fh:
            if _tools_decl(fh.read()) == "[]":
                offenders.append(os.path.basename(path))
    assert not offenders, ("agents declaring `tools: []` (grants ALL tools — use a real "
                           "restriction like `tools: TaskCreate`, or omit to inherit all): %s"
                           % offenders)


@case
def test_promptonly_critics_declare_a_real_restriction():
    """An agent that tells itself it works only from the brief / has no file access must
    BACK that with a real tools restriction (a non-empty list), so the runtime matches the
    design — otherwise it silently gets all tools and can fabricate from a file path."""
    claim = re.compile(r"work entirely from the brief|no file or web access|you have no tool",
                       re.IGNORECASE)
    bad = []
    for path in _agent_files():
        with open(path) as fh:
            text = fh.read()
        if claim.search(text):
            decl = _tools_decl(text)
            if decl in ("[]", "(absent)"):
                bad.append((os.path.basename(path), decl))
    assert not bad, ("prompt-only critics lacking a real tools restriction "
                     "(declare e.g. `tools: TaskCreate`): %s" % bad)


@case
def test_missing_artifact_guard_present_in_promptonly_critics():
    """BUG GUARDED (silent fabrication): a context-starved critic pointed at an artifact not
    in its brief must be instructed to STOP, not reconstruct it from memory. Every
    work-from-the-brief critic must carry an explicit no-fabrication guard."""
    claim = re.compile(r"work entirely from the brief|no file or web access", re.IGNORECASE)
    guard = re.compile(r"not present in your brief|never (invent|reconstruct)|do not reconstruct",
                       re.IGNORECASE)
    missing = []
    for path in _agent_files():
        with open(path) as fh:
            text = fh.read()
        if claim.search(text) and not guard.search(text):
            missing.append(os.path.basename(path))
    assert not missing, "prompt-only critics missing the no-fabrication guard: %s" % missing


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
