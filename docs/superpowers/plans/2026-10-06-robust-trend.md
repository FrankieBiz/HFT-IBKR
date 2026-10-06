# Robust trend implementation plan

> Execute reviewable units in this workspace. Use test-driven-development and
> requesting-code-review. User has delegated design decisions and authorized
> implementation; no additional design approval or external actions are required.

**Goal:** Turn the existing SPY baseline into a bounded research/shadow overlay
with enforced evidence, persistent entry halts and useful robustness diagnostics.

**Architecture:** Preserve the signal and original study. Add separate diagnostics
and readiness modules, and serialize risk memory with ledger decision recording.

**Tech stack:** Python standard library, Decimal, SQLite, Bash, unittest.

## Tasks

- [x] Review design and plan against existing contracts.
- [x] Add `studies/spy-trend-v2/{config,protocol}.json` and research protocol notes.
  Preserve v1. Use 25%/30% entry allocation and a 10% entry halt. Run IDs differ;
  the study runner shares v1's registry to prevent reused historical holdouts.
- [x] Add `quant_session/readiness.py`, readiness regression tests and update
  `scripts/{run_study,run_daily,daily_shadow}.sh`. Missing or unapproved evidence
  must stop before external calls. Bind actual config, protocol, selected lookback,
  source hash, dataset and frozen evidence; validate reports against the registry.
- [x] Add heartbeat and offline health checking with deadline/freshness tests.
- [x] Add `quant_research/robustness.py` and CLI command with expanding-window
  walk-forward and deterministic paired block resampling. Exclude holdout entirely,
  bind source identities and test future-data invariance and known path arithmetic.
- [x] Add atomic ledger-backed planning and persistent observed peak/halt state in
  `quant_session/{ledger,planner,__main__}.py`. Test recovery, lower declared peaks,
  corruption, exact retry, changed inputs and serialized planning.
- [x] Rewrite current overview/setup; reconcile delivery and operator documentation.
  Add current status/remaining work and explicitly describe deferred strategy modules.
- [x] Run focused regressions during each task; run `make check build demo` after
  integration. Review final diff independently and fix substantive findings.
- [x] Record final verification evidence and report user-facing changes/limits.

Implementation ownership: diagnostics worker owns research diagnostics/CLI/tests;
readiness worker owns runner scripts/readiness/health/tests; primary owns study
files, ledger/planner/session CLI and documentation. Workers must demonstrate
failing regressions before implementation and avoid overlapping file edits.

## Completion evidence (2026-10-06)

`make check build demo` exited 0. All 263 tests passed; compilation and
`git diff --check` passed. Bash syntax checks and local document-link checks passed.
Independent design/plan, risk, robustness and operations reviews found and resolved
manual-halt mark loss, cached-memory validation, cross-day deadline forgetting,
missing-registry audit resets and hidden calendar reread failures. Final reviewer
reported no remaining blockers.

Portable artifact SHA-256:
`b86fef37ce57af8907cc769ae59c5ec86b0704de49088e91e7602fc5c026dbeb`.
Synthetic demo: `.research-output/demo-5kx92cin/summary.json`, status
`offline_workflows_passed`. It includes robustness diagnostics, all 14 control
scenarios, frozen holdout/recovery and shadow BUY/HOLD/SELL/BLOCKED rehearsals.
Original `studies/spy-daily-v1` files have no diff.

No historical download/study, credentials, broker account, external notification,
deployment or order submission was used. Historical screening, realistic cost/data
calibration, prospective shadow evidence and independent monitor scheduling remain
empirical/operator work; software verification does not establish profitability.
