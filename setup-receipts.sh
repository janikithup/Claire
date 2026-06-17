#!/usr/bin/env bash
# claire setup-receipts — wire the de-priming RECEIPT writer into ~/.claude/settings.json.
#
# WHY THIS EXISTS: on the Claude Desktop app a plugin's PostToolUse hook does NOT fire
# (its PreToolUse hook does — verified 2026-06-17). Claire's receipt writer is a
# PostToolUse hook, so as a plugin hook it never runs: no receipt is written, the
# de-priming gate can never go silent, and it degrades to an unconditional nag. The fix
# is to register the SAME receipt writer in the user settings file, where PostToolUse
# hooks DO fire. This script does that safely and idempotently. Run once per machine —
# and again if you switch install methods (clone <-> marketplace), since the install path
# changes; this script re-points an old registration at the current install automatically.
#
# Safe by construction: the registered command is guarded with `[ -f <script> ]`, so if
# Claire is ever uninstalled the line becomes a harmless no-op instead of hanging the app
# on a missing script (the orphaned-hook failure mode).

set -u
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$PLUGIN_ROOT/hooks/record-audit-receipt.py"
SETTINGS="$HOME/.claude/settings.json"

if [ ! -f "$HOOK" ]; then
  echo "ERROR: receipt writer not found at $HOOK — run this from inside a Claire install." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found — Claire's hooks need it." >&2
  exit 1
fi

CMD="[ -f $HOOK ] && python3 $HOOK || true"

python3 - "$SETTINGS" "$CMD" <<'PY'
import json, os, sys
settings_path, desired = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
try:
    with open(settings_path) as fh:
        data = json.load(fh)
except FileNotFoundError:
    data = {}
except Exception as e:
    print(f"ERROR: could not parse {settings_path}: {e}", file=sys.stderr); sys.exit(1)

hooks = data.setdefault("hooks", {})
post = hooks.get("PostToolUse", [])

def is_ours(c): return "record-audit-receipt.py" in (c or "")

existing = [h.get("command", "") for blk in post for h in blk.get("hooks", []) if is_ours(h.get("command", ""))]

# Already registered correctly and uniquely -> nothing to do.
if existing == [desired]:
    print("Already registered — receipt enforcement is wired in settings.json. Nothing to do.")
    sys.exit(0)

# Otherwise strip EVERY existing Claire-receipt registration (handles a stale path left by
# a previous install method, or duplicates), pruning blocks that become empty, then append
# exactly one correct entry.
cleaned = []
for blk in post:
    kept = [h for h in blk.get("hooks", []) if not is_ours(h.get("command", ""))]
    if kept:
        nb = dict(blk); nb["hooks"] = kept; cleaned.append(nb)
cleaned.append({"matcher": "Agent|Task", "hooks": [{"type": "command", "command": desired}]})
hooks["PostToolUse"] = cleaned

with open(settings_path, "w") as fh:
    json.dump(data, fh, indent=2)

if existing:
    print("Re-pointed Claire's receipt registration to this install.")
else:
    print("Registered the receipt writer in", settings_path)
print("Receipt-backed de-priming enforcement will fire on new Agent/Task dispatches.")
print("Tip: run /claire:doctor to confirm a live audit writes a receipt.")
PY
