#!/usr/bin/env bash
# Gate immutable historical evidence, then freeze one offline shadow decision.
# Cached plans must match verified ledger bytes. No broker orders are sent.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
if [[ ${HFT_RUNNER_LOCK_OWNER:-} != "$PPID" ]] || ! "$PYTHON" scripts/runner_lock.py --verify-held; then
  exec "$PYTHON" scripts/runner_lock.py daily_shadow.sh "$@"
fi
CONFIG=${CONFIG:-}
PORTFOLIO=${PORTFOLIO:-.research-output/shadow/portfolio.json}
ROOT=.research-output/shadow
source scripts/shadow_common.sh
# This must precede credential reads, downloads and cached-plan presentation.
PRICE_FEED=$(readiness "" --feed-only)

read -r TODAY YESTERDAY < <("$PYTHON" -c '
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
today = datetime.now(ZoneInfo("America/New_York")).date()
print(today, today - timedelta(days=1))')
DAY=$ROOT/$TODAY
mkdir -p "$DAY"
readiness "$DAY/config.json" >/dev/null
[[ -n $CONFIG ]] || CONFIG=$DAY/config.json
if [[ -f $DAY/spy.qdata ]]; then
  readiness "" --daily-bundle "$DAY/spy.qdata" >/dev/null
fi

summary() {
  "$PYTHON" - "$DAY/plan.json" "$CONFIG" "$ROOT/ledger.sqlite" "$TODAY" <<'PY'
import hashlib, json, sys
from pathlib import Path
from quant_research.__main__ import source_identity
from quant_research.serde import InputError
from quant_session.ledger import DecisionLedger
try:
    content = DecisionLedger(sys.argv[3]).get(sys.argv[4])
    if Path(sys.argv[1]).read_bytes() != content:
        raise InputError('cached plan differs from verified ledger bytes')
    report = json.loads(content)
    config_bytes = Path(sys.argv[2]).read_bytes()
    expected_hashes = {'config': hashlib.sha256(config_bytes).hexdigest()}
    for package in ('quant_session', 'quant_research', 'quant_data'):
        expected_hashes[package+'_source'] = source_identity(package=package)['source_sha256']
    if any(report['source_hashes'].get(key) != value for key, value in expected_hashes.items()):
        raise InputError('cached decision config/source identity mismatch')
    lookback = json.loads(config_bytes)['lookback']
    print(f"{report['execution_session']}: {report['status']}  signal={report['signal']} "
          f"(from {report['signal_session']} close, SMA {lookback})  quote={report['quote_scope']}")
    if report['proposal']:
        p = report['proposal']
        print(f"  proposal: {p['side']} {p['quantity']} SPY near {p['reference_price']} "
              f"(est. fees {p['estimated_fees']}) -- shadow only; nothing was sent to any broker")
    for reason in report['blockers']:
        print(f"  blocked: {reason}")
except (InputError, OSError, ValueError, KeyError, TypeError) as error:
    print(f'shadow report error: {error}', file=sys.stderr)
    sys.exit(2)
PY
}

if [[ -f $DAY/plan.json ]]; then
  readiness "" --daily-bundle "$DAY/spy.qdata" >/dev/null
  summary
  echo "Already recorded for $TODAY (one frozen decision per session)."
  exit 0
fi
if [[ ! -f $PORTFOLIO ]]; then
  echo "Missing $PORTFOLIO. Create it from examples/shadow/portfolio.template.json." >&2
  exit 2
fi
ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
if [[ ! -f $ALPACA_ENV ]]; then
  echo "Missing $ALPACA_ENV with APCA_API_KEY_ID and APCA_API_SECRET_KEY." >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
. "$ALPACA_ENV"
set +a
[[ -d $DAY/alpaca ]] || "$PYTHON" -m quant_data fetch-alpaca --start 2016-01-01 --end "$YESTERDAY" --output-dir "$DAY/alpaca" --feed "$PRICE_FEED"
[[ -f $DAY/spy.qdata ]] || "$PYTHON" -m quant_data prepare --prices "$DAY/alpaca/prices.csv" \
  --distributions "$DAY/alpaca/distributions.csv" --calendar "$DAY/alpaca/calendar.csv" \
  --metadata "$DAY/alpaca/metadata.json" --output "$DAY/spy.qdata"
readiness "" --daily-bundle "$DAY/spy.qdata" >/dev/null
rm -f "$DAY/schedule.json" "$DAY/snapshot.json"
"$PYTHON" -m quant_session live-inputs --bundle "$DAY/spy.qdata" --portfolio "$PORTFOLIO" \
  --schedule-out "$DAY/schedule.json" --snapshot-out "$DAY/snapshot.json"
"$PYTHON" -m quant_session plan --bundle "$DAY/spy.qdata" --config "$CONFIG" \
  --schedule "$DAY/schedule.json" --snapshot "$DAY/snapshot.json" \
  --ledger "$ROOT/ledger.sqlite" --output "$DAY/plan.json"
summary
