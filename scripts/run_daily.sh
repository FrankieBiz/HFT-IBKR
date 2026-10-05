#!/usr/bin/env bash
# Start it and leave it running. It runs the one-time study if needed, then on every
# trading day records the shadow decision one minute after the open, and pushes
# status to your phone or browser through ntfy. Never places orders. Stop with Ctrl-C.
#
#   ./scripts/run_daily.sh           run until stopped
#   ./scripts/run_daily.sh --check   verify keys, calendar and notifications, then exit
#   ./scripts/run_daily.sh --once    handle today only, then exit
#
# Notifications: put NTFY_TOPIC=<private random name> in ~/.config/hft-ibkr/notify.env.
# Only status text is sent (decision, verdict, errors); never keys or account data.
set -uo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}
ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
NOTIFY_ENV=${NOTIFY_ENV:-$HOME/.config/hft-ibkr/notify.env}
NTFY_SERVER=${NTFY_SERVER:-https://ntfy.sh}
MODE=${1:-}
LOG=.research-output/shadow/run.log
mkdir -p .research-output/shadow

notify() {  # notify TITLE MESSAGE
  printf '%s  [%s] %s\n' "$(date '+%F %T %Z')" "$1" "$2" | tee -a "$LOG"
  if [[ -n ${NTFY_TOPIC:-} ]]; then
    curl -fsS -m 20 -H "Title: $1" --data-binary "$2" "$NTFY_SERVER/$NTFY_TOPIC" >/dev/null \
      || printf '%s  (notification not delivered)\n' "$(date '+%F %T %Z')" >>"$LOG"
  fi
}

if [[ ! -f $ALPACA_ENV ]]; then
  echo "Missing $ALPACA_ENV (see the WSL runbook, step 3)." >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$ALPACA_ENV"
[[ -f $NOTIFY_ENV ]] && . "$NOTIFY_ENV"
set +a
[[ -n ${NTFY_TOPIC:-} ]] || echo "Note: no NTFY_TOPIC set; status goes only to $LOG." >&2

clock() {  # prints "<open|closed|after> <seconds to run> <seconds to next wake>"
  "$PYTHON" -m quant_session market-clock 2>>"$LOG"
}

if [[ $MODE == --check ]]; then
  if ! read -r state run_in wake_in < <(clock); then
    echo "FAILED: could not read the Alpaca calendar; check keys and network (details in $LOG)." >&2
    exit 2
  fi
  [[ -f .research-output/shadow/portfolio.json ]] || echo "Warning: create .research-output/shadow/portfolio.json (runbook step 6)." >&2
  notify "HFT-IBKR check" "Setup check passed on $(hostname). Market today: $state; next run in $((run_in / 60)) min."
  exit 0
fi

notify "HFT-IBKR started" "Running on $(hostname). Checking the study, then waiting for the open."
if [[ ! -f .research-output/spy-daily-v1/holdout.json ]]; then
  if out=$(./scripts/run_study.sh 2>&1); then
    notify "Study verdict" "$("$PYTHON" scripts/study_verdict.py --brief .research-output/spy-daily-v1/holdout.json)"
  else
    notify "Study FAILED" "$(tail -n 8 <<<"$out")"
  fi
fi

while true; do
  if ! read -r state run_in wake_in < <(clock); then
    notify "Calendar check FAILED" "Will retry in 10 minutes. $(tail -n 3 "$LOG")"
    sleep 600
    continue
  fi
  case $state in
    open)
      if ((run_in > 0)); then
        notify "Waiting for the open" "Today's decision will be recorded in $((run_in / 60)) min (one minute after the open)."
        sleep "$run_in"
      fi
      if out=$(./scripts/daily_shadow.sh 2>&1); then
        notify "Today's decision" "$(tail -n 8 <<<"$out")"
      else
        notify "Daily run FAILED" "$(tail -n 8 <<<"$out")"
      fi
      ;;
    closed) notify "Market closed today" "No session today; sleeping until tomorrow morning." ;;
    after) notify "Market already closed" "Today's session is over; sleeping until tomorrow morning." ;;
  esac
  [[ $MODE == --once ]] && exit 0
  # Re-read the clock for tomorrow; a day-long sleep can't drift past the next open.
  read -r _ _ wake_in < <(clock) || wake_in=3600
  sleep "$wake_in"
done
