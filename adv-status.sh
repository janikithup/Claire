#!/usr/bin/env bash
# adv-status.sh — one-line version + update status for claire.
# Surfaced on each /claire:blank or /claire:challenge invocation so you can confirm,
# across machines, that you are running the latest version.
# Single source of truth for the version: .claude-plugin/plugin.json.
# Fail-open: ALWAYS prints a line; never errors out a caller. An update check
# that could not run reports "update check unavailable" — never a false "up to date".
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_JSON="$ROOT/.claude-plugin/plugin.json"
TS_FILE="$ROOT/hooks/.update-check.ts"
THROTTLE=21600   # hit the network at most once per 6h

# --- version (single source of truth: plugin.json) ---
# Pure-sed extraction — no python dependency (on some Windows machines `python3`
# is a no-op Microsoft Store stub, which silently yielded "v?").
VER="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PLUGIN_JSON" 2>/dev/null | head -1)"
[ -z "${VER:-}" ] && VER="?"

# --- pick a timeout wrapper if one exists (macOS ships neither by default) ---
TIMEOUT=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT="timeout 8"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT="gtimeout 8"; fi

# --- update check: throttle only the network fetch; recompute "behind" locally every run ---
checked=0
behind=0
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  now="$(date +%s)"
  last=0; [ -f "$TS_FILE" ] && last="$(cat "$TS_FILE" 2>/dev/null || echo 0)"
  case "$last" in (''|*[!0-9]*) last=0;; esac
  if [ $(( now - last )) -ge "$THROTTLE" ]; then
    # $TIMEOUT unquoted on purpose: empty -> plain `git fetch`; set -> `timeout 8 git fetch`
    if $TIMEOUT git -C "$ROOT" fetch --quiet origin 2>/dev/null; then
      printf '%s' "$now" > "$TS_FILE" 2>/dev/null
    fi
  fi
  # Recompute against the local remote-tracking ref (instant; reflects the last fetch OR a git pull),
  # so right after a pull this reads "up to date" immediately without waiting on the throttle.
  if git -C "$ROOT" rev-parse --abbrev-ref "@{u}" >/dev/null 2>&1; then
    b="$(git -C "$ROOT" rev-list --count "HEAD..@{u}" 2>/dev/null || echo '')"
    case "$b" in (''|*[!0-9]*) : ;; (*) behind="$b"; checked=1 ;; esac
  fi
fi

if [ "$checked" = 1 ]; then
  if [ "$behind" -gt 0 ]; then
    status=" · ${behind} commit(s) behind origin — run: git -C \"$ROOT\" pull"
  else
    status=" · up to date"
  fi
else
  status=" · (update check unavailable — git pull to be sure)"
fi

printf 'claire v%s%s\n' "$VER" "$status"
