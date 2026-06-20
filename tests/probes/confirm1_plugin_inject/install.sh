#!/usr/bin/env bash
# Wire the confirm-#1 probe into the LIVE Claire plugin install, so a PLUGIN
# PreToolUse hook is registered at the next session start. Reversible via
# uninstall.sh (which restores the backed-up hooks.json verbatim).
#
# Safe: it only ADDS one PreToolUse entry next to Claire's real hooks and copies
# one script in. It backs up the original hooks.json first. The probe hook no-ops
# on every dispatch except one carrying the [CLAIRE-INJECT-PROBE] marker.
set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
  echo "ERROR: could not locate the live Claire install (looked in installed_plugins.json and the cache)." >&2
  exit 1
fi

echo "Live Claire install: $ROOT"
HOOKS_JSON="$ROOT/hooks/hooks.json"

cp "$PROBE_DIR/inject-probe.py" "$ROOT/hooks/inject-probe.py"
echo "Copied inject-probe.py -> $ROOT/hooks/"

# Back up hooks.json once (don't clobber an existing backup), then add the entry.
python3 - "$HOOKS_JSON" <<'PY'
import json, sys, os
path = sys.argv[1]
bak = path + ".probe-bak"
with open(path) as fh:
    cfg = json.load(fh)
if not os.path.exists(bak):
    with open(bak, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print("Backed up hooks.json -> %s" % os.path.basename(bak))
entry = {
    "matcher": "Agent|Task",
    "hooks": [{"type": "command",
               "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/inject-probe.py\""}],
}
pre = cfg.setdefault("hooks", {}).setdefault("PreToolUse", [])
cmds = json.dumps(pre)
if "inject-probe.py" in cmds:
    print("Probe entry already present — nothing to add.")
else:
    pre.append(entry)
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print("Added probe PreToolUse entry to hooks.json")
PY

cat <<EOF

PROBE INSTALLED. Next steps:

  1. FULLY QUIT AND REOPEN the Claude Desktop app (a NEW CHAT is not enough —
     plugin hooks only reload at app start; a mid-session add fires but does
     NOT rewrite). Then open any project.

  2. In that fresh session, paste exactly:

       Dispatch a general-purpose subagent. Its prompt must be exactly this,
       verbatim: [CLAIRE-INJECT-PROBE] [ORIG-CANARY-Z9Q] What is 2 + 2? Reply with
       only the number. Then show me the subagent's exact reply, in full.

  3. Read the subagent's reply:
       - "INJECTION-OK" present AND the echo does NOT contain ORIG-CANARY-Z9Q
            -> CONFIRMED SAFE. Rewrite propagated; the original did not survive.
               (Any "[standing invitation]" coda in the echo is the fixed harness
               tail on the REWRITTEN prompt — not a steer.)
       - "INJECTION-OK" present BUT the echo DOES contain ORIG-CANARY-Z9Q
            -> COMPROMISED. The original prompt leaked past the overwrite; the
               injection approach needs rework.
       - reply is "4" / no INJECTION-OK
            -> NOT propagated. Redesign blocked.
       Cross-check with the log:
             cat "$ROOT/hooks/inject-probe.log"

  4. When done, revert with:  bash "$PROBE_DIR/uninstall.sh"
EOF
