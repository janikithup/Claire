#!/usr/bin/env python3
"""
UNIT TEST — release-manifest integrity.

These guard the files a marketplace consumer actually reads when installing Claire:
plugin.json (the plugin's own manifest) and marketplace.json (the self-listing).
A typo in either breaks the install with a cryptic error, so we check them in CI
on every commit.

Two kinds of check:

  1. VALIDITY  — each manifest is parseable JSON and carries the fields the
                 marketplace requires, with sane values.
  2. SYNC      — the version in plugin.json, the version in marketplace.json, and
                 the latest released entry in CHANGELOG.md all agree. This is the
                 test that catches the classic release bug: bumping the manifest
                 but forgetting the changelog (or vice versa), which ships a
                 version whose changes are undocumented.

Targets the REAL staged release artifacts at the project root, not a fixture —
so the test protects what actually gets published.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN_JSON = os.path.join(STAGING, ".claude-plugin", "plugin.json")
MARKETPLACE_JSON = os.path.join(STAGING, ".claude-plugin", "marketplace.json")
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
    # declared here. The "never always-on" promise is carried by the marketplace
    # entry's defaultEnabled:false (checked below) and the description, not by an
    # alwaysOn flag in this manifest.


@case
def test_marketplace_json_is_valid():
    """BUG GUARDED: marketplace.json is malformed or missing the plugin entry, so
    the listing breaks. Checks the entry shape a marketplace consumer relies on."""
    m = load_json(MARKETPLACE_JSON)
    plugins = m.get("plugins")
    assert isinstance(plugins, list) and plugins, "marketplace.json needs a non-empty plugins[]"
    entry = plugins[0]
    assert entry.get("name"), "marketplace plugin entry must have a name"
    assert SEMVER.match(str(entry.get("version", ""))), \
        "marketplace entry version must be semver, got %r" % entry.get("version")
    src = entry.get("source") or {}
    assert src.get("source") == "github" and src.get("repo"), \
        "marketplace entry must point at a github repo source"
    # Claire must not auto-enable on install.
    assert entry.get("defaultEnabled") is False, \
        "marketplace entry must declare defaultEnabled:false"


@case
def test_manifest_names_agree():
    """BUG GUARDED: plugin.json and marketplace.json drift to different plugin
    names after a rename, so the listing points at a plugin that won't resolve."""
    p = load_json(PLUGIN_JSON)
    mkt = load_json(MARKETPLACE_JSON)["plugins"][0]
    assert p["name"] == mkt["name"], \
        "name mismatch: plugin.json=%r marketplace.json=%r" % (p["name"], mkt["name"])


# --- version <-> changelog sync ---------------------------------------------

def _latest_changelog_version():
    """Return the newest RELEASED version heading in CHANGELOG.md.

    Keep-a-Changelog format: '## [x.y.z] - DATE'. We skip the '## [Unreleased]'
    heading deliberately — an unreleased section is allowed to be ahead.
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


@case
def test_marketplace_version_matches_plugin():
    """BUG GUARDED: marketplace.json lists an older version than the plugin actually
    is, so installers fetch a stale pin. The two manifests' versions must match."""
    pv = load_json(PLUGIN_JSON)["version"]
    mv = load_json(MARKETPLACE_JSON)["plugins"][0]["version"]
    assert pv == mv, \
        "version out of sync: plugin.json=%s marketplace.json=%s" % (pv, mv)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from _runner import run
    sys.exit(run(CASES))
