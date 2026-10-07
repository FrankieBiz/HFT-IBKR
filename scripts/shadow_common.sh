#!/usr/bin/env bash
# Shared offline operator gate. Source only after changing to the repository root.
STUDY_OUTPUT=${STUDY_OUTPUT:-.research-output/spy-trend-v2}
STUDY_DIR=${STUDY_DIR:-studies/spy-trend-v2}
# Deliberately fixed: changing studies cannot create a fresh holdout registry.
STUDY_REGISTRY=.research-output/spy-daily-v1/experiments.sqlite

readiness() {
  local args=(--bundle "$STUDY_OUTPUT/spy.qdata" --config "$STUDY_DIR/config.json"
    --protocol "$STUDY_DIR/protocol.json" --selection "$STUDY_OUTPUT/selection.json"
    --holdout "$STUDY_OUTPUT/holdout.json" --registry "$STUDY_REGISTRY")
  [[ -z ${CONFIG:-} ]] || args+=(--planning-config "$CONFIG")
  [[ -z ${1:-} ]] || args+=(--config-out "$1")
  (( $# == 0 )) || shift
  "$PYTHON" -m quant_session.readiness "${args[@]}" "$@"
}
