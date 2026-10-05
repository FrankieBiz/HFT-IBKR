#!/usr/bin/env bash
# Record today's daily shadow decision from free live inputs. Never places orders.
#
# Run on a trading day while the market is open (09:30-16:00 New York). Safe to
# rerun: finished steps are reused, and once today's decision is recorded it is only
# printed again, because the ledger freezes one decision per session.
#
# Environment overrides:
#   ALPACA_ENV  file with APCA_API_KEY_ID / APCA_API_SECRET_KEY (default ~/.config/alpaca/paper.env)
#   CONFIG      strategy config (default: studies/spy-daily-v1/config.json with the study's
#               frozen lookback from .research-output/spy-daily-v1/selection.json, if any)
#   PORTFOLIO   shadow book you maintain (default .research-output/shadow/portfolio.json)
#   PYTHON      interpreter (default python3)
set -euo pipefail
cd "$(dirname "$0")/.."

ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
CONFIG=${CONFIG:-}
PORTFOLIO=${PORTFOLIO:-.research-output/shadow/portfolio.json}
PYTHON=${PYTHON:-python3}
ROOT=.research-output/shadow

read -r TODAY YESTERDAY < <("$PYTHON" -c '
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
today = datetime.now(ZoneInfo("America/New_York")).date()
print(today, today - timedelta(days=1))')
DAY=$ROOT/$TODAY

summary() {
  "$PYTHON" - "$1" "$DAY/config.json" <<'EOF'
import json, sys
from pathlib import Path
report = json.load(open(sys.argv[1]))
config = Path(sys.argv[2])
lookback = f"SMA {json.load(config.open())['lookback']}" if config.is_file() else 'custom config'
print(f"{report['execution_session']}: {report['status']}  signal={report['signal']} "
      f"(from {report['signal_session']} close, {lookback})  quote={report['quote_scope']}")
if report['proposal']:
    p = report['proposal']
    print(f"  proposal: {p['side']} {p['quantity']} SPY near {p['reference_price']} "
          f"(est. fees {p['estimated_fees']}) -- shadow only; nothing was sent to any broker")
for reason in report['blockers']:
    print(f"  blocked: {reason}")
EOF
}

if [[ -f $DAY/plan.json ]]; then
  summary "$DAY/plan.json"
  echo "Already recorded for $TODAY (one frozen decision per session)."
  exit 0
fi
if [[ ! -f $PORTFOLIO ]]; then
  echo "Missing $PORTFOLIO. Create it from examples/shadow/portfolio.template.json (see the WSL runbook)." >&2
  exit 2
fi
if [[ ! -f $ALPACA_ENV ]]; then
  echo "Missing $ALPACA_ENV with APCA_API_KEY_ID and APCA_API_SECRET_KEY." >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$ALPACA_ENV"
set +a
mkdir -p "$DAY"

if [[ ! -d $DAY/alpaca ]]; then
  "$PYTHON" -m quant_data fetch-alpaca --start 2016-01-01 --end "$YESTERDAY" --output-dir "$DAY/alpaca"
fi
if [[ ! -f $DAY/spy.qdata ]]; then
  "$PYTHON" -m quant_data prepare --prices "$DAY/alpaca/prices.csv" \
    --distributions "$DAY/alpaca/distributions.csv" --calendar "$DAY/alpaca/calendar.csv" \
    --metadata "$DAY/alpaca/metadata.json" --output "$DAY/spy.qdata"
fi
if [[ -z $CONFIG ]]; then
  CONFIG=$DAY/config.json
  if [[ ! -f $CONFIG ]]; then
    # The study's validation picks the lookback; until it has run, use the 200 hypothesis.
    "$PYTHON" - "$CONFIG" <<'EOF'
import json, sys
from pathlib import Path
config = json.load(open('studies/spy-daily-v1/config.json'))
selection = Path('.research-output/spy-daily-v1/selection.json')
if selection.is_file():
    config['lookback'] = json.load(selection.open())['selected_lookback']
Path(sys.argv[1]).write_text(json.dumps(config, indent=2) + '\n')
EOF
  fi
fi
# A failed earlier attempt may have left inputs from an older quote; take a fresh one.
rm -f "$DAY/schedule.json" "$DAY/snapshot.json"
"$PYTHON" -m quant_session live-inputs --bundle "$DAY/spy.qdata" --portfolio "$PORTFOLIO" \
  --schedule-out "$DAY/schedule.json" --snapshot-out "$DAY/snapshot.json"
"$PYTHON" -m quant_session plan --bundle "$DAY/spy.qdata" --config "$CONFIG" \
  --schedule "$DAY/schedule.json" --snapshot "$DAY/snapshot.json" \
  --ledger "$ROOT/ledger.sqlite" --output "$DAY/plan.json"
summary "$DAY/plan.json"
