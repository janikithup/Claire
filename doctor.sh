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

echo "Receipt enforcement (de-priming gate teeth)"
# On the Claude Desktop app, a plugin's PostToolUse hook does NOT fire (its PreToolUse
# hook does). Claire's receipt writer is PostToolUse, so unless it is ALSO registered in
# the user settings file it never runs: no receipt is written, the gate can never go
# silent, and de-priming degrades to an unconditional nag. setup-receipts.sh wires it in.
SETTINGS="$HOME/.claude/settings.json"
reg="$(python3 - "$SETTINGS" 2>/dev/null <<'PYEOF'
import json, os, re, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("none"); sys.exit()
cmds = [h.get("command", "") for blk in d.get("hooks", {}).get("PostToolUse", [])
        for h in blk.get("hooks", []) if "record-audit-receipt.py" in h.get("command", "")]
if not cmds:
    print("none"); sys.exit()
m = re.search(r"(\S*record-audit-receipt\.py)", cmds[0])
p = os.path.expanduser(m.group(1)) if m else ""
print("ok" if (p and os.path.isfile(p)) else "stale")
PYEOF
)"
case "$reg" in
  ok)    ok "receipt writer registered in settings.json — enforcement can fire on this machine" ;;
  stale) warn "receipt writer is registered in settings.json but points at a path that no longer exists — did you switch install methods (clone <-> marketplace)? Re-point it:  bash \"$PLUGIN_ROOT/setup-receipts.sh\"  (or run /claire:doctor, which offers to)." ;;
  *)     warn "receipt writer NOT registered in settings.json — on Claude Desktop the plugin's PostToolUse hook does not fire, so NO receipt is ever written and the gate becomes an unconditional nag. Run:  bash \"$PLUGIN_ROOT/setup-receipts.sh\"  (or run /claire:doctor, which offers to do it). The live test below confirms." ;;
esac
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
