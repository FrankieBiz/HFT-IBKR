#!/usr/bin/env bash
# Run the pre-registered spy-daily-v1 study once and print its verdict.
# Finished steps are reused; the holdout is released once and only re-read afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}
ALPACA_ENV=${ALPACA_ENV:-$HOME/.config/alpaca/paper.env}
D=.research-output/spy-daily-v1
S=studies/spy-daily-v1

if [[ -z ${APCA_API_KEY_ID:-} && -f $ALPACA_ENV ]]; then
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
  --config $S/config.json --protocol $S/protocol.json --registry "$D/experiments.sqlite" \
  --selection "$D/selection.json" --output "$D/validation.json" --run-id validation-1
[[ -f $D/holdout.json ]] || "$PYTHON" -m quant_research holdout --bundle "$D/spy.qdata" \
  --config $S/config.json --protocol $S/protocol.json --registry "$D/experiments.sqlite" \
  --selection "$D/selection.json" --output "$D/holdout.json" --run-id holdout-1
"$PYTHON" scripts/study_verdict.py "$D/holdout.json"
