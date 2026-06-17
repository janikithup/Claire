#!/usr/bin/env bash
# claire health / contribution stats — read at a glance for troubleshooting.
# Shows this machine's logs only (each machine keeps its own):
#   GATE:  PASS   = a de-primed brief was dispatched (the discipline was followed)
#          REMIND = an un-de-primed adversary dispatch was caught (de-priming skipped)
#   NUDGE: the discoverability reminder fired on an adversarial-shaped prompt
# A high REMIND share = de-priming is being skipped: the thing to investigate.
H="$(cd "$(dirname "$0")" && pwd)/hooks"
gl="$H/gate-fire.log"; nl="$H/nudge-fire.log"
echo "=== claire stats ($(date '+%Y-%m-%d %H:%M')) ==="
if [ -s "$gl" ]; then
  tot=$(grep -c . "$gl"); p=$(grep -c ' PASS ' "$gl"); r=$(grep -c ' REMIND ' "$gl")
  echo "GATE: $tot fires  —  $p PASS (de-primed)  /  $r REMIND (de-priming skipped, caught)"
  [ "$tot" -gt 0 ] && echo "      REMIND share: $(( r * 100 / tot ))%   (high = investigate)"
  echo "      by agent:"; grep -oE 'agent=[^ ]+' "$gl" | sort | uniq -c | sed 's/^/        /'
  echo "      last 5:";   tail -5 "$gl" | sed 's/^/        /'
else
  echo "GATE: no fires logged yet"
fi
echo
if [ -s "$nl" ]; then
  echo "NUDGE: $(grep -c . "$nl") fires (discoverability reminder)"
  echo "       last 5:"; tail -5 "$nl" | sed 's/^/        /'
else
  echo "NUDGE: no fires logged yet"
fi
echo
"$(cd "$(dirname "$0")" && pwd)/adv-score.sh" stats 2>/dev/null || true
