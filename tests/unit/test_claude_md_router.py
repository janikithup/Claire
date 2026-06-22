#!/usr/bin/env python3
"""
UNIT TEST — CLAUDE.md is a router whose pointers stay coherent with docs/.

CLAUDE.md was restructured (0.12.0) into an index that points at docs/ for mechanism
instead of inlining it. The known failure mode of an index (surfaced by Claire's own
critic) is DRIFT: a pointer outlives the doc it names (dangling), or a doc is added
with no pointer (invisibly absent). This pins both directions so the index can't rot
silently — the machinery that replaces the written "add a pointer when you build
machinery" note.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
DOCS_DIR = os.path.join(ROOT, "docs")

CASES = []
def case(fn):
    CASES.append(fn); return fn


def _claude_md():
    with open(CLAUDE_MD) as fh:
        return fh.read()


def _referenced_docs(text):
    """Every docs/<name>.md path named anywhere in CLAUDE.md."""
    return set(re.findall(r"docs/([A-Za-z0-9_-]+\.md)", text))


def _docs_on_disk():
    return {f for f in os.listdir(DOCS_DIR) if f.endswith(".md")}


@case
def test_every_pointer_resolves():
    """BUG GUARDED (dangling pointer): a docs/ link in CLAUDE.md points at a file that does
    not exist — a reader follows it into a 404. Every pointer must resolve to a real file."""
    refs = _referenced_docs(_claude_md())
    assert refs, "CLAUDE.md names no docs/ pointers — the router map is missing"
    missing = sorted(r for r in refs if not os.path.isfile(os.path.join(DOCS_DIR, r)))
    assert not missing, "CLAUDE.md points at docs that do not exist: %s" % missing


@case
def test_every_doc_is_referenced():
    """BUG GUARDED (invisibly-absent doc): a file is added to docs/ but no pointer names it,
    so it is unreachable from the index — the exact drift the router note tries to prevent.
    Every docs/*.md must be named somewhere in CLAUDE.md."""
    refs = _referenced_docs(_claude_md())
    orphans = sorted(_docs_on_disk() - refs)
    assert not orphans, "docs/ files with no pointer in CLAUDE.md: %s" % orphans


if __name__ == "__main__":
    from _runner import run
    sys.exit(run(CASES))
