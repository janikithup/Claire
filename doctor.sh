#!/usr/bin/env bash
# claire doctor — filesystem health + conflict checks for a Claire install.
#
# Run from the workspace you want to check (so the collision scan sees that
# workspace's local agents). The LIVE receipt self-test is NOT here — it needs to
# dispatch a subagent, so the /claire:doctor skill drives that part. This script
# does every check that is a pure function of the filesystem.
#
# Exit code: 0 if no FAIL lines, 1 if any FAIL. WARN lines do not fail the run.

set -u

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(pwd)"
fails=0
warns=0

if [ -t 1 ]; then
  ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
  warn() { printf '  \033[33mWARN\033[0m %s\n' "$1"; warns=$((warns+1)); }
  fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fails=$((fails+1)); }
else
  ok()   { printf '  OK   %s\n' "$1"; }
  warn() { printf '  WARN %s\n' "$1"; warns=$((warns+1)); }
  fail() { printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }
fi

CLAIRE_AGENTS="affected-actor-simulator blank-slate-advisor brief-leak-auditor dialectical-scout failure-mode-attacker over-capture-triage-verifier probe-auditor"

echo "claire doctor"
echo "  install:   $PLUGIN_ROOT"
echo "  workspace: $WORKSPACE"
echo ""

echo "Dependencies"
if command -v python3 >/dev/null 2>&1; then
  ok "python3 present ($(command -v python3)) — hooks can run"
else
  fail "python3 NOT found — the de-priming gate and receipt hooks cannot run"
fi
echo ""

echo "Install integrity"
if [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
  ok "plugin.json present"
else
  fail "plugin.json missing — this is not a valid plugin folder"
fi
if [ -f "$PLUGIN_ROOT/.claude-plugin/marketplace.json" ]; then
  fail "marketplace.json present beside plugin.json — REMOVE it; it makes the loader treat this folder as a marketplace, so Claire's commands never register"
else
  ok "no marketplace.json beside plugin.json (correct for a clone install)"
fi
for d in agents hooks skills/challenge skills/blank; do
  if [ -e "$PLUGIN_ROOT/$d" ]; then ok "component present: $d"; else fail "component missing: $d"; fi
done
echo ""

echo "Version"
if [ -x "$PLUGIN_ROOT/adv-status.sh" ]; then
  printf '  '; "$PLUGIN_ROOT/adv-status.sh" 2>/dev/null || warn "adv-status.sh did not run cleanly"
else
  warn "adv-status.sh not found/executable — cannot report version or behind-origin"
fi
echo ""

echo "Duplicate installs"
dup=0
if [ -d "$HOME/.claude" ]; then
  count=$(find "$HOME/.claude" -name plugin.json -path '*claire*' 2>/dev/null \
            | grep -v '/_build_claire/' | wc -l | tr -d ' ')
  if [ "${count:-0}" -gt 1 ]; then
    warn "Claire appears installed in $count places under ~/.claude (clone + marketplace?). Use ONE route per machine — two copies double-load Claire's hooks and agents. Keep one, remove the rest."
    find "$HOME/.claude" -name plugin.json -path '*claire*' 2>/dev/null | grep -v '/_build_claire/' | sed 's/\/.claude-plugin\/plugin.json$//' | sed 's/^/         - /'
    dup=1
  fi
fi
[ "$dup" -eq 0 ] && ok "single Claire install"
echo ""

echo "Name collisions (local agents shadowing Claire's)"
collision=0
for pair in "this workspace|$WORKSPACE/.claude/agents" "your user config|$HOME/.claude/agents"; do
  label="${pair%%|*}"; dir="${pair#*|}"
  [ -d "$dir" ] || continue
  for name in $CLAIRE_AGENTS; do
    if [ -f "$dir/$name.md" ]; then
      warn "$label has its own '$name' — it shadows Claire's HERE for a bare reference. Claire dispatches the claire:$name version explicitly, so routing is safe; this is informational."
      collision=1
    fi
  done
done
[ "$collision" -eq 0 ] && ok "no local agents share Claire's names"
echo ""

echo "Leftover old installs"
leftover=0
if [ -d "$HOME/.claude/skills" ]; then
  while IFS= read -r entry; do
    base="$(basename "$entry")"
    case "$base" in
      adversarial-toolkit|adv|margot|devils-advocate)
        warn "leftover '$base' in ~/.claude/skills — superseded by Claire; remove it to de-clutter the menu"; leftover=1 ;;
    esac
  done < <(find "$HOME/.claude/skills" -maxdepth 1 -mindepth 1 -type d 2>/dev/null)
fi
[ "$leftover" -eq 0 ] && ok "no superseded adversarial installs found"
echo ""

echo "-----------------------------------------------------------"
if [ "$fails" -gt 0 ]; then
  printf 'RESULT: %d FAIL, %d WARN — fix the FAILs above.\n' "$fails" "$warns"
elif [ "$warns" -gt 0 ]; then
  printf 'RESULT: healthy, %d WARN (informational — see above).\n' "$warns"
else
  printf 'RESULT: all clear.\n'
fi
echo "NOTE: filesystem checks only. Run /claire:doctor for the LIVE test that"
echo "      confirms de-priming enforcement is actually firing on this machine."
[ "$fails" -gt 0 ] && exit 1 || exit 0
