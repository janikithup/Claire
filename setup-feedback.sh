#!/usr/bin/env bash
# claire setup-feedback — wire the FEEDBACK-CHANNEL Stop hook into ~/.claude/settings.json,
# and pin the private queue so it can never be committed to a repo.
#
# WHY THIS EXISTS. Claire issues used to scatter into random workspaces: the agent's Write
# tool is sandboxed to the current project, so the central queue (~/.claude/claire/issues/)
# is unreachable from a session rooted elsewhere, and reports fell back into whatever repo
# was open — sometimes a PUBLIC one. The fix is a Stop hook (file-claire-issue.py) that the
# harness runs AS THE USER, outside the sandbox: it scans a turn for an emitted
# [CLAIRE-ISSUE …] marker and files it to the private queue from ANY workspace.
#
# WHY settings.json AND NOT the plugin hooks.json: a plugin Stop hook's firing on macOS
# Desktop is unproven, and Claire's 0.4.x receipt saga is the standing lesson (a plugin
# PostToolUse hook silently NEVER fired, costing four broken releases). A GLOBAL
# settings.json Stop hook is boundary-tested to fire for every workspace's sessions. So we
# register here, idempotently and uninstall-safe.
#
# Run once per machine — and again if you switch install methods (clone <-> marketplace),
# since the install path changes; this re-points an old registration at the current install.

set -u
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$PLUGIN_ROOT/hooks/file-claire-issue.py"
SETTINGS="$HOME/.claude/settings.json"
CLAIRE_DIR="$HOME/.claude/claire"

if [ ! -f "$HOOK" ]; then
  echo "ERROR: feedback hook not found at $HOOK — run this from inside a Claire install." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found — Claire's hooks need it." >&2
  exit 1
fi

# --- 1. Privacy pin: a nested .gitignore so the queue survives a parent un-ignore ----------
# ~/.claude is a tracked git repo. The queue is ignored today only by the top-level `*` rule;
# one stray un-ignore (`!claire/`) or a `git add -f` would start committing private dev notes
# (home paths, other-project names) into that repo. A nested `*` .gitignore re-asserts the
# ignore locally and is consulted the moment a parent rule re-includes the dir.
mkdir -p "$CLAIRE_DIR/issues"
GITIGNORE="$CLAIRE_DIR/.gitignore"
if [ ! -f "$GITIGNORE" ]; then
  cat > "$GITIGNORE" <<'GI'
# Claire's private region — NEVER commit to any repo.
# ~/.claude is a tracked repo (remote: claude-config). This dir holds dev issues, the event
# log, and the behavioral logbook, which may carry home paths and other-project internals.
# Belt-and-suspenders to the top-level `*` ignore: this survives a parent un-ignore rule.
*
!.gitignore
GI
  echo "Pinned the private-queue .gitignore guard at $GITIGNORE"
else
  echo "Private-queue .gitignore guard already present."
fi

# --- 2. Register the Stop hook in settings.json --------------------------------------------
# Marketplace installs live at a version-numbered path that changes every update, so register
# a version-agnostic GLOB there; a clone has a stable path and is registered directly.
# `env -u CLAIRE_ISSUE_DIR -u CLAIRE_TEST` strips the test-only queue override from the
# environment the hook runs in, so a hostile project `.claude/settings.json` env block can't
# redirect this unsandboxed hook's write out of the private queue. The trailing `; true` (glob
# form) keeps exit 0 even when the cache is cleared without re-running setup — so a missing
# script is a genuine harmless no-op, not a spurious hook error on every turn-end.
STRIP="env -u CLAIRE_ISSUE_DIR -u CLAIRE_TEST python3"
case "$PLUGIN_ROOT" in
  */plugins/cache/*)
    GLOB="$(dirname "$PLUGIN_ROOT")/*/hooks/file-claire-issue.py"
    CMD="for f in $GLOB; do [ -f \"\$f\" ] && $STRIP \"\$f\"; done; true"
    ;;
  *)
    CMD="[ -f $HOOK ] && $STRIP $HOOK || true"
    ;;
esac

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
stop = hooks.get("Stop", [])

def is_ours(c): return "file-claire-issue.py" in (c or "")

existing = [h.get("command", "") for blk in stop for h in blk.get("hooks", []) if is_ours(h.get("command", ""))]

# Already registered correctly and uniquely -> nothing to do.
if existing == [desired]:
    print("Already registered — the feedback channel is wired in settings.json. Nothing to do.")
    sys.exit(0)

# Otherwise strip EVERY existing Claire-feedback registration (stale path or duplicate),
# pruning blocks that become empty, then append exactly one correct entry. A Stop hook block
# carries no matcher (Stop is not tool-specific).
cleaned = []
for blk in stop:
    kept = [h for h in blk.get("hooks", []) if not is_ours(h.get("command", ""))]
    if kept:
        nb = dict(blk); nb["hooks"] = kept; cleaned.append(nb)
# `timeout: 10` is a backstop: even though the marker regex is now linear, a Stop hook that
# fires every turn-end globally must never be the thing that hangs a session.
cleaned.append({"hooks": [{"type": "command", "command": desired, "timeout": 10}]})
hooks["Stop"] = cleaned

with open(settings_path, "w") as fh:
    json.dump(data, fh, indent=2)

if existing:
    print("Re-pointed Claire's feedback registration to this install.")
else:
    print("Registered the feedback Stop hook in", settings_path)
print("Emitted [CLAIRE-ISSUE …] markers will now be filed to ~/.claude/claire/issues/ from any workspace.")
print("Tip: run /claire:report to file a barrier, or /claire:doctor to confirm the wiring.")
PY
