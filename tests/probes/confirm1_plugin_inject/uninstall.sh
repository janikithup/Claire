#!/usr/bin/env bash
# Revert the confirm-#1 probe: restore the backed-up hooks.json verbatim and
# remove the probe script + log from the live Claire install.
set -euo pipefail

ROOT="$(python3 - <<'PY'
import json, os, glob
reg = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
root = None
try:
    with open(reg) as fh:
        data = json.load(fh)
    for entries in data.get("plugins", {}).values():
        for e in entries:
            p = e.get("installPath")
            if p and "claire" in p and os.path.isdir(p):
                root = p
except Exception:
    pass
if not root:
    cands = sorted(glob.glob(os.path.expanduser(
        "~/.claude/plugins/cache/claire-marketplace/claire/*")))
    cands = [c for c in cands if os.path.isdir(os.path.join(c, "hooks"))]
    root = cands[-1] if cands else ""
print(root)
PY
)"

if [ -z "$ROOT" ] || [ ! -d "$ROOT/hooks" ]; then
  echo "ERROR: could not locate the live Claire install." >&2
  exit 1
fi

HOOKS_JSON="$ROOT/hooks/hooks.json"
BAK="$HOOKS_JSON.probe-bak"

if [ -f "$BAK" ]; then
  mv "$BAK" "$HOOKS_JSON"
  echo "Restored hooks.json from backup."
else
  # No backup (e.g. installed by hand) — surgically drop the probe entry instead.
  python3 - "$HOOKS_JSON" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as fh:
    cfg = json.load(fh)
pre = cfg.get("hooks", {}).get("PreToolUse", [])
cfg["hooks"]["PreToolUse"] = [
    e for e in pre if "inject-probe.py" not in json.dumps(e)]
with open(path, "w") as fh:
    json.dump(cfg, fh, indent=2)
print("Removed probe entry from hooks.json (no backup found).")
PY
fi

rm -f "$ROOT/hooks/inject-probe.py" "$ROOT/hooks/inject-probe.log"
echo "Removed inject-probe.py and its log."
echo "Probe reverted. Restart your session to drop the (now-unregistered) hook."
