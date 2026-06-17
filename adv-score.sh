#!/usr/bin/env bash
# adv-score.sh — outcome scoring for adversary calls.
# Records whether an adversary's call actually turned out RIGHT over time — the
# only *measured* form of independence (a flag that fires is not a flag that was
# correct). Append-only event log; per-machine (gitignored), like the gate logs.
# Fail-soft: bad input prints usage and exits non-zero; it never corrupts the log.
#
# Usage:
#   adv-score.sh add <kind> "<short description>"      # log a call; prints its id
#   adv-score.sh verdict <id> <right|wrong|partial> ["note"]
#   adv-score.sh list [pending]                        # all calls, or only unscored
#   adv-score.sh stats                                 # hit-rate summary (default)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$ROOT/hooks/outcomes.tsv"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

cmd="${1:-stats}"
case "$cmd" in
  add)
    kind="${2:-blank}"; desc="${3:-}"
    if [ -z "$desc" ]; then echo "usage: adv-score.sh add <kind> \"<description>\"" >&2; exit 2; fi
    kind="$(printf '%s' "$kind" | tr '\t\n' '  ')"
    desc="$(printf '%s' "$desc" | tr '\t\n' '  ')"
    id="$(date +%s)-$(( RANDOM % 1000 ))"
    printf 'CALL\t%s\t%s\t%s\t%s\n' "$id" "$(ts)" "$kind" "$desc" >> "$LOG"
    echo "$id"
    ;;
  verdict)
    id="${2:-}"; v="${3:-}"; note="${4:-}"
    case "$v" in right|wrong|partial) ;; *) echo "usage: adv-score.sh verdict <id> <right|wrong|partial> [note]" >&2; exit 2;; esac
    if [ -z "$id" ]; then echo "missing id" >&2; exit 2; fi
    if [ ! -f "$LOG" ] || ! grep -q "^CALL"$'\t'"$id"$'\t' "$LOG"; then echo "no such call id: $id" >&2; exit 2; fi
    note="$(printf '%s' "$note" | tr '\t\n' '  ')"
    printf 'VERDICT\t%s\t%s\t%s\t%s\n' "$id" "$(ts)" "$v" "$note" >> "$LOG"
    echo "recorded: $id -> $v"
    ;;
  list)
    only="${2:-}"
    [ -f "$LOG" ] || { echo "(no calls logged yet)"; exit 0; }
    awk -F'\t' -v only="$only" '
      $1=="CALL"{ if(!($2 in seen)){seen[$2]=1; order[++n]=$2} desc[$2]=$5; kind[$2]=$4 }
      $1=="VERDICT"{ verd[$2]=$4; vnote[$2]=$5 }
      END{
        for(i=1;i<=n;i++){ id=order[i]; v=(id in verd)?verd[id]:"pending";
          if(only=="pending" && v!="pending") continue;
          printf "%s  [%s]  %-7s  %s%s\n", id, kind[id], v, desc[id], (vnote[id]!=""?"  ("vnote[id]")":"") }
      }' "$LOG"
    ;;
  stats|*)
    echo "=== adversary outcome scores ($(date '+%Y-%m-%d %H:%M')) ==="
    if [ ! -s "$LOG" ]; then echo "SCORE: no calls logged yet"; exit 0; fi
    awk -F'\t' '
      $1=="CALL"{ if(!($2 in seen)){seen[$2]=1; order[++n]=$2} }
      $1=="VERDICT"{ verd[$2]=$4 }
      END{
        scored=0; right=0; wrong=0; partial=0; pending=0;
        for(i=1;i<=n;i++){ id=order[i];
          if(id in verd){ scored++; v=verd[id];
            if(v=="right")right++; else if(v=="wrong")wrong++; else partial++ }
          else pending++ }
        printf "SCORE: %d calls  —  %d scored / %d pending\n", n, scored, pending;
        if(scored>0){
          acc=(right+0.5*partial)/scored*100;
          printf "       right %d  /  partial %d  /  wrong %d   ->  hit-rate %.0f%%\n", right, partial, wrong, acc;
          print  "       (partial counts as half; low rate on scored calls = firing but not landing)"
        }
      }' "$LOG"
    ;;
esac
