# Trading Desk Reliability Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans to implement these tasks with regression-first verification and independent review.

**Goal:** Repair verified operational defects, expose actual study evidence, and reduce repeated dashboard work without changing the frozen economic experiment.

**Architecture:** Keep study display verification in a focused app module. Share the fill snapshot check between display and accounting. Recovery exports stored, verified artifacts before any new intake; daily retries remain bounded and calendar gated.

**Tech Stack:** Python standard library, SQLite, Bash, vanilla browser assets; existing unittest and Playwright fixture checks.

Specification: `docs/superpowers/specs/2026-10-07-reliability.md`.

## Task 1: Deterministic quote inputs
Files: `quant_session/live.py`, `tests/test_shadow_live.py`.
- [x] Add regressions for fractional non-UTC quote times and altered Decimal precision/rounding; observe failures with `PYTHONPATH=tests python3 -m unittest test_shadow_live`.
- [x] Parse original timestamp with its offset intact; require UTC. Decorate NAV construction with existing `fixed_decimal`.
- [x] Run focused tests; retain explicit IEX feed and freshness policies.

## Task 2: Truthful app state and useful strategy evidence
Files: `quant_app/service.py`, `quant_app/jobs.py`, new `quant_app/evidence.py`, `quant_app/assets/app.js`, `quant_app/assets/index.html`, `tests/test_app_service.py`, `tests/test_app_jobs.py`, new `tests/test_app_evidence.py`.
- [x] Regress changed-book fill eligibility, malformed heartbeat, and malformed-key offline checks before fixes.
- [x] Share immutable snapshot/hash/book matching between fill readiness and recording. Heartbeat projection must pass existing schema validation. Do not read keys for offline checks.
- [x] Introduce a content-keyed study display cache. Hash all study paths and research source plus SQLite sidecars before/after readiness; unstable content fails closed. Return copies. Test content mutation with preserved size/mtime, missing/repaired files and WAL changes.
- [x] Project verified selected settings and qualified holdout economic metrics; label missing optional metrics honestly. Render as text in the existing setup page. Pause polling while the page is hidden and refresh on return.
- [x] Run `PYTHONPATH=tests python3 -m unittest test_app_service test_app_jobs test_app_evidence`; measure repeated snapshot cost on invented fixtures before/after.

## Task 3: Recoverable daily operations
Files: `scripts/run_daily.sh`, `scripts/daily_shadow.sh`, new `quant_session/recovery.py`, `tests/test_shadow_runners.py`, new `tests/test_shadow_recovery.py`.
- [x] Regress a transient run failure and committed decision with missing publication.
- [x] Retry up to three attempts, ten minutes apart, only while the same session is open. Preserve failure health, readiness gates, fail-fast `--once` and existing lock ownership.
- [x] In `daily_shadow.sh`, recover exact canonical ledger report only after validating original inputs, current config/source identity and daily data gate. Publish before input regeneration or intake credentials/provider access. The outer continuous runner retains its gated calendar scheduling role. Any mismatch requires review.
- [x] Run focused unittest suites and `bash -n scripts/run_daily.sh scripts/daily_shadow.sh`.

## Task 4: Interrupted study publication
Files: `scripts/run_study.sh`, new `quant_session/study_recovery.py`, new `tests/test_study_recovery.py`.
- [x] Regress missing completed validation/selection/holdout files and reserved/failed events.
- [x] Open registry read-only, validate stored canonical payload digests and identities against current data/config/protocol/research source. Export only missing matching artifacts, never overwrite or recompute. Missing registered freeze or non-completed event requires explicit review before intake.
- [x] Run focused recovery tests and existing study runner tests.

## Task 5: Verification and publication
Files: `README.md`, `SETUP.md`, `docs/plans/quant-trading-delivery-plan.md`, dated validation notes.
- [x] Independent specification and quality review; correct substantive findings.
- [x] Run `make check build demo`, browser fixtures, shell/JS syntax and content comparison proving frozen research/config/protocol unchanged.
- [x] Document actual behavior, WSL update/start commands, measured fixture performance and remaining evidence limits. No unattended maintenance promise.
- [ ] Commit only reviewed source/docs; push existing branch and update PR 3 with exact validation. Check CI on the pushed SHA.
