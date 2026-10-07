#!/usr/bin/env bash
# Operator runner: authenticate completed study evidence before external setup.
# --check checks readiness then setup; --once handles today. No implicit study.
# Waits update a local heartbeat every 30 seconds; check_shadow_health.py must be
# independently scheduled to detect a stopped runner and overdue decisions.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
MODE=${1:-}
case "$MODE" in ''|--check|--once) ;; *) echo 'Usage: run_daily.sh [--check|--once]' >&2; exit 2;; esac
if [[ ${HFT_RUNNER_LOCK_OWNER:-} != "$PPID" ]] || ! "$PYTHON" scripts/runner_lock.py --verify-held; then
  exec "$PYTHON" scripts/runner_lock.py run_daily.sh "$@"
fi
source scripts/shadow_common.sh
readiness >/dev/null
LOG=.research-output/shadow/run.log
HEARTBEAT=.research-output/shadow/heartbeat.json
mkdir -p .research-output/shadow
RUNNER_STATUS=starting
heartbeat() { RUNNER_STATUS=$1; "$PYTHON" -m quant_session.health --path "$HEARTBEAT" --status "$1" "${@:2}"; }
finish() {
  local result=$?
  trap - EXIT
  if (( result != 0 )); then heartbeat failed || true; else heartbeat stopped || true; fi
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
heartbeat starting

ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
NOTIFY_ENV=${NOTIFY_ENV:-$HOME/.config/hft-ibkr/notify.env}
NTFY_SERVER=${NTFY_SERVER:-https://ntfy.sh}
if [[ ! -f $ALPACA_ENV ]]; then echo "Missing $ALPACA_ENV." >&2; exit 2; fi
set -a
# shellcheck disable=SC1090
. "$ALPACA_ENV"
[[ ! -f $NOTIFY_ENV ]] || . "$NOTIFY_ENV"
set +a
notify() {
  printf '%s  [%s] %s\n' "$(date '+%F %T %Z')" "$1" "$2" | tee -a "$LOG"
  if [[ -n ${NTFY_TOPIC:-} ]]; then
    curl -fsS -m 20 -H "Title: $1" --data-binary "$2" "$NTFY_SERVER/$NTFY_TOPIC" >/dev/null \
      || printf '%s  (notification not delivered)\n' "$(date '+%F %T %Z')" >>"$LOG"
  fi
}
clock() { "$PYTHON" -m quant_session market-clock 2>>"$LOG"; }
clock_read() {
  local result
  result=$(clock) || return 2
  read -r state run_in wake_in <<<"$result"
  [[ $state =~ ^(open|closed|after)$ && $run_in =~ ^[0-9]+$ && $wake_in =~ ^[0-9]+$ ]]
}
wait_with_heartbeat() {
  local left=$1 chunk
  while (( left > 0 )); do
    heartbeat "$RUNNER_STATUS"
    chunk=$left
    (( chunk <= 30 )) || chunk=30
    sleep "$chunk"
    left=$((left - chunk))
  done
  heartbeat "$RUNNER_STATUS"
}
session_today() {
  "$PYTHON" -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("America/New_York")).date())'
}
expected_today() {
  local session deadline
  read -r session deadline < <("$PYTHON" - "$run_in" "$state" <<'PY'
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import sys
now = datetime.now(timezone.utc)
delay = 0 if sys.argv[2] == 'after' else int(sys.argv[1]) + 600
print(now.astimezone(ZoneInfo('America/New_York')).date(),
      (now + timedelta(seconds=delay)).isoformat())
PY
)
  local status=waiting
  [[ $RUNNER_STATUS != failed ]] || status=failed
  heartbeat "$status" --expected-session "$session" --expected-deadline "$deadline"
}

if [[ $MODE == --check ]]; then
  if ! clock_read; then echo "FAILED: could not read calendar (details in $LOG)." >&2; exit 2; fi
  notify 'Shadow setup check' "Historical readiness and setup passed. Market today: $state."
  exit 0
fi
notify 'Shadow runner started' 'Historical evidence verified; waiting for the session.'
handled_session=
while true; do
  # Recheck source/evidence before each external calendar read and notification.
  readiness >/dev/null
  if ! clock_read; then
    heartbeat failed
    notify 'Calendar check FAILED' 'Will retry in 10 minutes; see local log.'
    [[ $MODE != --once ]] || exit 2
    wait_with_heartbeat 600
    continue
  fi
  case $state in
    open)
      current_session=$(session_today)
      if [[ $handled_session != "$current_session" ]]; then
        target_session=$current_session
        expected_today
        wait_with_heartbeat "$run_in"
        # The scheduled delay can cross a close or a New York date boundary.
        if (( run_in > 0 )); then
          readiness >/dev/null
          if ! clock_read; then heartbeat failed; exit 2; fi
          current_session=$(session_today)
        fi
        if [[ $state == open && $current_session == "$target_session" ]] && (( run_in == 0 )); then
          handled_session=$target_session
          for attempt in 1 2 3; do
            if (( attempt > 1 )); then
              # Keep the failed heartbeat visible throughout the retry delay.
              wait_with_heartbeat 600
              readiness >/dev/null
              if ! clock_read; then
                heartbeat failed
                notify 'Calendar check FAILED' 'Daily retries stopped; see local log.'
                break
              fi
              current_session=$(session_today)
              [[ $state == open && $current_session == "$target_session" ]] && (( run_in == 0 )) || break
            fi
            heartbeat running
            if out=$(./scripts/daily_shadow.sh 2>&1); then
              heartbeat ok
              notify "Today's shadow decision" "$(tail -n 8 <<<"$out")"
              break
            else
              heartbeat failed
              notify 'Daily run FAILED' "$(tail -n 8 <<<"$out")"
              [[ $MODE != --once ]] || exit 2
            fi
          done
        fi
      fi
      ;;
    closed) notify 'Market closed today' 'No session today; waiting until tomorrow morning.' ;;
    after) expected_today; notify 'Market already closed' 'Session over; independent health checks verify expected decisions.' ;;
  esac
  [[ $MODE != --once ]] || exit 0
  readiness >/dev/null
  if ! clock_read; then
    heartbeat failed
    notify 'Calendar reread FAILED' 'Will retry in one hour; see local log.'
    wake_in=3600
  fi
  wait_with_heartbeat "$wake_in"
done
