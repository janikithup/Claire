#!/usr/bin/env bash
# Install the claire workflow presets into ~/.claude/workflows/ on this machine.
# Plugins can't LOAD workflow presets, so they ride in this repo's workflows/ folder
# and this script drops them where the Workflow tool finds them. Re-run after a git pull
# to pick up updates. Safe to run repeatedly (it overwrites with the repo copies).
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/workflows"
DEST="${HOME}/.claude/workflows"
mkdir -p "$DEST"
cp "$SRC"/*.js "$DEST"/
echo "Installed $(ls "$SRC"/*.js | wc -l | tr -d ' ') claire workflow presets -> $DEST"
echo "(On Windows, copy workflows\\*.js into %USERPROFILE%\\.claude\\workflows\\ manually.)"
