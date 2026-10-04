# Chronological Evaluation Implementation Plan

Goal: evaluate predeclared daily ETF variants without exposing holdout results during
validation. This completes the evaluation software, not empirical strategy validation.
Architecture: immutable protocol, disjoint date ranges and embargo gaps; evaluate
candidates only in development/validation; freeze the selected candidate and source,
config, protocol and input hashes; release holdout in a separate explicit command.
Stack: Python standard library and existing offline simulator.

## Protocol contract

Schema: `schema_version`, `protocol_id`, `development_start`, `development_end`,
`validation_start`, `validation_end`, `holdout_start`, `holdout_end`,
`embargo_sessions`, `candidate_lookbacks`, `selection_metric`.
All dates must be supplied sessions, starts <= ends, intervals strictly chronological
and disjoint. Between intervals require at least `embargo_sessions` supplied sessions.
Every interval needs at least two evaluated sessions. Candidate lookbacks are unique
positive integers >= 2. Every start needs at least maximum-lookback earlier sessions.
Selection metric is fixed `validation_return_under_2x_cost`; choose maximum validation
return at cost multiplier 2, ties broken by smaller lookback. This is an illustrative
predeclared selector, not a profitability/significance threshold.

No training occurs for the SMA. Earlier prices warm causal features; each interval
starts flat at initial cash. Simulation receives only bars through that interval's
end, so future holdout prices cannot affect earlier results. Report explicitly that
capital/holdings reset across intervals, and that embargo is a selection guard rather
than a general proof of independence. No supervised labels or CPCV are claimed.

Validation outputs: interval boundaries, trial count, all candidate development and
validation results at 1/2/5 costs, selected lookback and selection rationale. Holdout
results must not appear in the validation report. The frozen selection artifact
contains schema, protocol, config, code and dataset/manifest digests, selected
lookback, trial count and a canonical integrity digest. A separate holdout call must
validate all those identities against current inputs before computing results; reject
any changed selected lookback/config/protocol/data/code, malformed artifact or a
second release through the same local registry. No claim that a local hash can
prevent an operator reading or copying the original dataset is made.

Use append-only SQLite trial registry with transactions and unique run/release IDs.
Register each validation before publishing outputs, including failed/cancelled runs
where possible; finalized result hashes should be stored. Track historical attempts,
not just current candidate count. Holdout release uses a transaction, cannot be
silently rerun after a crash; an explicit documented failure entry remains consumed.
Tests cover ranges, warmup, embargo, duplicate trials/releases, tampering, prefix
invariance, no holdout disclosure, selection ties, changed identities and SQLite
integrity/restart persistence. Synthetic artifacts must remain labeled synthetic.

## Tasks

- [x] Write `tests/test_evaluation.py`, see expected absent-module failure.
- [x] Implement `quant_research/evaluation.py` protocol parser and pure interval
  evaluation using `simulate`, truncating bars at interval end.
- [x] Implement `quant_research/experiments.py` SQLite registry for append-only
  attempts and one-time holdout release; add storage/rollback/reopen tests.
- [x] Implement freeze/verify/release APIs with canonical digests and a versioned
  report contract; all input hashes correspond to consumed inputs.
- [x] Run focused tests and full suite, review against this contract then review
  code quality; address material findings.
- [x] Integrate separate CLI `evaluate` and `holdout` commands (root agent owns CLI).
- [x] Add synthetic protocol example, run validation then holdout locally, record
  evidence and the remaining historical-data/broker operational gates.

## Validation evidence — 2026-10-04

- `make check build demo`: exit 0; complete suite 123 tests passed, Python 3.14.0.
- Separate CLI evaluation, durable freeze, holdout release and stored report
  recovery passed using the portable built archive and synthetic example.
- Repeat holdout rejected; holdout recovery matches the original report byte for
  byte. Development/validation/holdout use same-period cash/buy-and-hold benchmarks.
- Independent spec and code-quality review approved the evaluation/registry APIs.
  Fixed demonstrated repeat-release identity, recomputed selection-integrity and
  saved negative-return string comparison issues. Completed holdout payloads are
  stored so a failed report publication does not require recomputation.
- Local artifacts and full log are in `.research-output/demo-76roqo4q` and
  `.research-output/final-verification.log`, ignored by git.
- This completes M3 evaluation software. No reviewed historical market dataset or
  calibrated fee/market-impact assumptions were available; empirical strategy
  validation remains outstanding. No supervised training or label purge is claimed.
