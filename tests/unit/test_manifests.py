#!/usr/bin/env python3
"""
UNIT TEST — release-manifest integrity.

Guards the manifest a user's Claude Code actually reads when loading Claire:
plugin.json. A typo breaks the load with a cryptic error, so we check it in CI on
every commit.

NOTE on marketplace.json — it lives in a SEPARATE repo. Claire's primary install
IS a marketplace (janikithup/claire-marketplace), but that marketplace.json sits in
its own repo, never beside this plugin.json: a `.claude-plugin/marketplace.json`
next to plugin.json makes the loader treat the folder as a *marketplace* rather
than a *plugin* (and also breaks the clone-into-skills-dir alternative install), so
the commands never register. This repo therefore ships NO marketplace.json on
purpose. The cross-repo version check — plugin.json vs the marketplace repo's
`version` field, the lag that stranded 0.6.1->0.7.1 — CANNOT live here (the sibling
repo isn't present in CI); it is enforced by `./release.sh --check`. These tests
cover only the within-repo manifest.

Two kinds of check:
  1. VALIDITY — plugin.json is parseable JSON with the load-bearing fields.
  2. SYNC     — plugin.json's version equals the latest released CHANGELOG entry,
                catching the classic bug: bumping the manifest but forgetting the
                changelog (or vice versa), shipping undocumented changes.

Targets the REAL staged release artifact at the project root, not a fixture.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN_JSON = os.path.join(STAGING, ".claude-plugin", "plugin.json")
CHANGELOG = os.path.join(STAGING, "CHANGELOG.md")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- validity ----------------------------------------------------------------

@case
def test_plugin_json_is_valid():
    """BUG GUARDED: a stray comma or missing brace makes plugin.json unparseable,
    so the plugin won't load at all. Also checks the load-bearing fields exist."""
    m = load_json(PLUGIN_JSON)
    assert m.get("name"), "plugin.json must carry a non-empty name"
    assert SEMVER.match(str(m.get("version", ""))), \
        "plugin.json version must be semver x.y.z, got %r" % m.get("version")
    assert m.get("description"), "plugin.json must carry a description"
    # plugin.json is intentionally minimal (name/description/version/author): plugin
    # components (skills/agents/hooks) are auto-discovered at the plugin root, not
    # declared here. The "never always-on" promise is carried by the description and
    # the fact that no component fires without an explicit /claire invocation.


@case
def test_no_marketplace_json_present():
    """BUG GUARDED: a marketplace.json creeps back in beside plugin.json, which makes
    the loader read the folder as a marketplace and silently drop Claire's commands.
    The real marketplace.json lives in the SEPARATE claire-marketplace repo; both
    install paths require its ABSENCE here."""
    mkt = os.path.join(STAGING, ".claude-plugin", "marketplace.json")
    assert not os.path.exists(mkt), (
        "marketplace.json must NOT exist beside plugin.json — it breaks the "
        "git-clone-into-skills-dir install by making the loader treat the folder "
        "as a marketplace rather than a plugin.")


# --- version <-> changelog sync ---------------------------------------------

def _latest_changelog_version():
    """Return the newest RELEASED version heading in CHANGELOG.md.

    Keep-a-Changelog format: '## [x.y.z] - DATE'. We skip '## [Unreleased]'
    deliberately — an unreleased section is allowed to be ahead.
    """
    pat = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]")
    with open(CHANGELOG) as fh:
        for line in fh:
            m = pat.match(line.strip())
            if m:
                return m.group(1)
    return None


@case
def test_plugin_version_matches_changelog():
    """BUG GUARDED — THE CLASSIC RELEASE BUG: the manifest version is bumped but
    CHANGELOG.md isn't (or vice versa), shipping a version whose changes are
    undocumented. The top released changelog entry must equal plugin.json's version."""
    pv = load_json(PLUGIN_JSON)["version"]
    cv = _latest_changelog_version()
    assert cv is not None, "no released [x.y.z] heading found in CHANGELOG.md"
    assert pv == cv, (
        "version out of sync: plugin.json=%s but newest CHANGELOG entry=%s. "
        "Bump the changelog and the manifest together." % (pv, cv))


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from _runner import run
    sys.exit(run(CASES))
