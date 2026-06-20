#!/usr/bin/env bash
# release.sh — publish a Claire release to BOTH repos in one step.
#
# A Claire release lives in TWO repos, and forgetting the second strands every
# user on the old version:
#
#   1. this plugin repo   — plugin.json version, a vX.Y.Z tag, a GitHub Release
#   2. claire-marketplace — the "version" field in its .claude-plugin/marketplace.json
#
# The Desktop plugins panel shows users that marketplace "version" field as
# "latest" and only OFFERS an update when it climbs. The plugin source is a bare
# repo URL, so the CODE comes from main HEAD — but the version NUMBER users see
# comes ONLY from the marketplace manifest. Bumping plugin.json without bumping the
# marketplace silently strands everyone on the old version. (That exact lapse
# stranded 0.6.1 through 0.7.1 — four releases no user could install.)
#
# Usage:
#   ./release.sh           publish the version currently in plugin.json
#   ./release.sh --check   verify plugin.json, marketplace.json, the latest tag,
#                          and the CHANGELOG all agree (non-destructive)
#
# This script assumes plugin.json is ALREADY bumped and committed on main (the
# bump is the last commit of the feature, per CLAUDE.md). It PUBLISHES what is
# committed; it does not author the bump or the CHANGELOG entry.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_DIR="${CLAIRE_MARKETPLACE_DIR:-$PLUGIN_DIR/../claire-marketplace}"
PLUGIN_REPO="janikithup/Claire"

# --- version readers (single source of truth each) ---------------------------
json_version() {  # first "version": "..." in $1
  grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$1" | head -1 \
    | sed 's/.*"\([0-9][^"]*\)".*/\1/'
}
plugin_version()  { json_version "$PLUGIN_DIR/.claude-plugin/plugin.json"; }
market_version()  { json_version "$MARKETPLACE_DIR/.claude-plugin/marketplace.json"; }
latest_tag()      { git -C "$PLUGIN_DIR" tag -l 'v*' | sort -V | tail -1; }
changelog_top()   { grep -o '## \[[0-9][^]]*\]' "$PLUGIN_DIR/CHANGELOG.md" | head -1 | sed 's/## \[\(.*\)\]/\1/'; }

# --- non-destructive consistency check ---------------------------------------
# The guard for the bug this script exists to kill: plugin.json moved but the
# marketplace (or tag, or CHANGELOG) did not. At rest, all four MUST agree.
check() {
  local pv mv tag cl ok=1
  pv="$(plugin_version)"; mv="$(market_version)"; tag="$(latest_tag)"; cl="$(changelog_top)"
  printf 'plugin.json      : %s\n' "$pv"
  printf 'marketplace.json : %s   (%s)\n' "$mv" "$MARKETPLACE_DIR"
  printf 'latest tag       : %s\n' "$tag"
  printf 'CHANGELOG top    : %s\n' "$cl"
  [ -n "$mv" ]        || { echo "MISMATCH: could not read marketplace.json (is $MARKETPLACE_DIR present?)"; ok=0; }
  [ "$pv" = "$mv" ]   || { echo "MISMATCH: plugin.json ($pv) != marketplace.json ($mv)  <-- the stranding bug"; ok=0; }
  [ "v$pv" = "$tag" ] || { echo "MISMATCH: plugin.json ($pv) != latest tag ($tag)"; ok=0; }
  [ "$pv" = "$cl" ]   || { echo "MISMATCH: plugin.json ($pv) != CHANGELOG top ($cl)"; ok=0; }
  if [ "$ok" = 1 ]; then echo "OK — all four sources agree on $pv"; else echo "FAIL — sources disagree"; return 1; fi
}

# --- full publish ------------------------------------------------------------
release() {
  local v tag notes
  v="$(plugin_version)"; tag="v$v"
  echo "Releasing $tag from $PLUGIN_DIR"

  # preconditions — fail loud, before touching anything
  [ "$(git -C "$PLUGIN_DIR" branch --show-current)" = "main" ] || { echo "ABORT: plugin repo not on main"; exit 1; }
  if ! { git -C "$PLUGIN_DIR" diff --quiet && git -C "$PLUGIN_DIR" diff --cached --quiet; }; then
    echo "ABORT: plugin repo has uncommitted changes — bump + commit first (the bump is the last commit, not this script's job)"; exit 1
  fi
  [ -d "$MARKETPLACE_DIR/.claude-plugin" ] || { echo "ABORT: marketplace repo not at $MARKETPLACE_DIR (set CLAIRE_MARKETPLACE_DIR)"; exit 1; }
  [ "$(changelog_top)" = "$v" ] || { echo "ABORT: CHANGELOG top is '$(changelog_top)', expected '$v' — add the [$v] entry first"; exit 1; }
  git -C "$PLUGIN_DIR" rev-parse "$tag" >/dev/null 2>&1 && { echo "ABORT: tag $tag already exists"; exit 1; }
  command -v gh >/dev/null || { echo "ABORT: gh CLI not found"; exit 1; }

  # tests — the unit layer must be green (the eval layer is run by hand, per tests/README.md)
  echo "Running unit tests…"
  ( cd "$PLUGIN_DIR" && python3 -m pytest tests/unit -q ) || { echo "ABORT: unit tests failed"; exit 1; }

  # CHANGELOG notes for this version (everything under "## [v]" up to the next "## [")
  notes="$(awk -v v="$v" '
    $0 ~ "^## \\["v"\\]" {grab=1; next}
    grab && /^## \[/ {exit}
    grab {print}
  ' "$PLUGIN_DIR/CHANGELOG.md")"
  [ -n "$(printf '%s' "$notes" | tr -d '[:space:]')" ] || { echo "ABORT: no CHANGELOG notes found for $v"; exit 1; }

  # 1) plugin repo: tag, push commit + tag, cut the GitHub Release
  git -C "$PLUGIN_DIR" tag "$tag"
  git -C "$PLUGIN_DIR" push origin main
  git -C "$PLUGIN_DIR" push origin "$tag"
  printf '%s\n' "$notes" | gh release create "$tag" --repo "$PLUGIN_REPO" --title "$tag" --notes-file -

  # 2) marketplace repo: bump the plugin entry's version, commit, push
  [ "$(git -C "$MARKETPLACE_DIR" branch --show-current)" = "main" ] || { echo "ABORT: marketplace repo not on main"; exit 1; }
  local mfile="$MARKETPLACE_DIR/.claude-plugin/marketplace.json"
  perl -i -pe 'if (!$d && s/("version"\s*:\s*)"[^"]*"/${1}"'"$v"'"/) { $d=1 }' "$mfile"
  git -C "$MARKETPLACE_DIR" add .claude-plugin/marketplace.json
  git -C "$MARKETPLACE_DIR" commit -m "claire $v"
  git -C "$MARKETPLACE_DIR" push origin main

  # 3) confirm the REMOTES actually serve $v (a green push is "accepted", not "live")
  echo "Verifying remotes…"
  local rp rm
  rp="$(curl -fsSL "https://raw.githubusercontent.com/janikithup/Claire/main/.claude-plugin/plugin.json"          | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1)"
  rm="$(curl -fsSL "https://raw.githubusercontent.com/janikithup/claire-marketplace/main/.claude-plugin/marketplace.json" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1)"
  echo "  remote plugin.json      -> $rp"
  echo "  remote marketplace.json -> $rm"
  echo
  echo "Done. Users get $v on their next marketplace refresh (panel: refresh marketplace, then Update claire)."
}

case "${1:-}" in
  --check) check ;;
  "")      release ;;
  *)       echo "Usage: $0 [--check]"; exit 2 ;;
esac
