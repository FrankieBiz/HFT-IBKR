#!/usr/bin/env bash
# Explicit operator research command. Uses the existing registry across studies;
# never reopens consumed holdout sessions or overwrites v1 study artifacts.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
source scripts/shadow_common.sh
D=$STUDY_OUTPUT
S=$STUDY_DIR
if [[ ! -f $STUDY_REGISTRY ]]; then
  # A genuinely fresh checkout may initialize the shared registry offline. Any
  # legacy artifact means missing audit history, so there is no automatic reset.
  shopt -s nullglob dotglob
  legacy_artifacts=(.research-output/spy-daily-v1/* "$D"/*)
  shopt -u nullglob dotglob
  if (( ${#legacy_artifacts[@]} > 0 )); then
    echo "Missing shared registry alongside legacy study artifacts or current study output; retain/recover original audit history. Refusing a fresh registry." >&2
    exit 2
  fi
  mkdir -p .research-output/spy-daily-v1
fi
"$PYTHON" - "$STUDY_REGISTRY" registry-preflight <<'PYREG'
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from quant_research.experiments import ExperimentRegistry
from quant_research.serde import InputError
path = Path(sys.argv[1])
try:
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            attempts = db.execute("SELECT run_id FROM events WHERE kind='holdout' AND status='reserved'").fetchall()
            for (run_id,) in attempts:
                try:
                    claimed = db.execute('SELECT count(*) FROM released_holdout_sessions WHERE run_id=?', (run_id,)).fetchone()[0]
                except sqlite3.Error:
                    claimed = 0
                if not claimed:
                    raise InputError('legacy holdout release lacks session claims; reviewed migration required; do not reopen historical dates')
    else:
        with ExperimentRegistry(path):
            pass
except (InputError, sqlite3.Error) as error:
    print(f'study registry error: {error}', file=sys.stderr)
    sys.exit(2)
PYREG
ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
if [[ ! -d $D/alpaca && -z ${APCA_API_KEY_ID:-} && -f $ALPACA_ENV ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ALPACA_ENV"
  set +a
fi
mkdir -p "$D"
[[ -d $D/alpaca ]] || "$PYTHON" -m quant_data fetch-alpaca --start 2016-01-01 --end 2026-10-02 --output-dir "$D/alpaca"
[[ -f $D/spy.qdata ]] || "$PYTHON" -m quant_data prepare --prices "$D/alpaca/prices.csv" \
  --distributions "$D/alpaca/distributions.csv" --calendar "$D/alpaca/calendar.csv" \
  --metadata "$D/alpaca/metadata.json" --output "$D/spy.qdata"
[[ -f $D/inspect.json ]] || "$PYTHON" -m quant_data inspect --bundle "$D/spy.qdata" --output "$D/inspect.json"
[[ -f $D/validation.json ]] || "$PYTHON" -m quant_research evaluate --bundle "$D/spy.qdata" \
  --config "$S/config.json" --protocol "$S/protocol.json" --registry "$STUDY_REGISTRY" \
  --selection "$D/selection.json" --output "$D/validation.json" --run-id spy-trend-v2-validation-1
[[ -f $D/robustness.json ]] || "$PYTHON" -m quant_research robustness --bundle "$D/spy.qdata" \
  --config "$S/config.json" --protocol "$S/protocol.json" --output "$D/robustness.json"
[[ -f $D/holdout.json ]] || "$PYTHON" -m quant_research holdout --bundle "$D/spy.qdata" \
  --config "$S/config.json" --protocol "$S/protocol.json" --registry "$STUDY_REGISTRY" \
  --selection "$D/selection.json" --output "$D/holdout.json" --run-id spy-trend-v2-holdout-1
"$PYTHON" scripts/study_verdict.py "$D/holdout.json"
readiness
