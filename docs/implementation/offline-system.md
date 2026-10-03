# Offline quantitative system implementation plan

Date: 2026-10-03. User authorizes implementation and GitHub synchronization; IBKR is last.

## Scope and design

Implement an executable local research and simulation platform in Python 3.11+ (standard library), with a separately compiled C++20 deterministic execution foundation. No credentials, vendor data downloads, broker connections, deployment, paid services or model downloads. Keep the existing Orca feature branch and push incremental reviewed commits to origin.

Python provides validated CSV import with provenance and SQLite history, an event-driven next-bar simulator, realistic configurable cost assumptions, long-only cash portfolio accounting, a strategy protocol and illustrative moving-average strategy, reproducible artifacts, offline reports, and research validation utilities. C++ provides a bounded SPSC queue, fail-closed state machine/risk gate, token bucket and AC scheduling, with an offline replay executable. Python simulation is a reference research path; the C++ executable is a separately tested execution foundation, not a broker adapter or latency guarantee.

All inputs reject invalid/nonfinite values. Times are timezone-aware UTC; bar timestamps denote bar start. Signals formed from a completed bar may execute only on a later bar. Simulated market fills use next-bar open plus half spread, slippage and participation-dependent impact, capped by volume; no fills at zero volume. Unfilled orders expire at the next attempt to prevent stale intent. Limits include cash, per-order, per-symbol, gross/net, sector concentration, daily loss, peak drawdown, stale marks and kill state. No shorts or leverage in this first simulator; this makes margin utilization zero. Reconciliation requires exact position/open-order matching before READY. Halts cancel pending simulated orders and retain inventory for inspection; never assume liquidation is safe.

The data importer rejects duplicate/out-of-order bars, bad OHLCV and missing provenance, preserves immutable dataset versions and checksums, and records gaps and survivorship/adjustment limitations. Simulation output contains configuration, input hash, fills, decisions, equity, cost totals and summary. A static HTML report opens locally; no external assets or server.

Research modules implement interval-aware triple-barrier labels, purged/embargoed combinatorial folds, walk-forward splits, PSR/DSR and CSCV PBO. CPCV splits alone are not a PBO calculation; no automatic promotion to live mode. A persisted experiment registry records trials and human review states. AI receives only exported research packets and cannot enter deterministic execution. Uncalibrated costs and synthetic data are labeled explicitly.

## Tasks and validation

- [ ] 1. Foundation: `pyproject.toml`, `.gitignore`, `Makefile`, source package, example config and synthetic data; no runtime third-party dependencies.
- [ ] 2. Data: `quantlab/data.py`, schema/types, SQLite import and read, source metadata; tests cover atomic rejection and provenance.
- [ ] 3. Simulation: `quantlab/risk.py`, `simulation.py`, `strategy.py`, cost model, event audit and reports; tests cover next-bar timing, cash conservation, exposure, partial fills, stale data, daily drawdown, rejection and kill/recovery.
- [ ] 4. Research: `quantlab/research/` labels, validation, metrics, experiment registry; tests cover leakage, combinations, tied ranks, invalid inputs and trial counts.
- [ ] 5. Native foundation: `native/` C++20 SPSC queue, risk/state control, token bucket, AC schedule, offline replay executable and tests; use clang++/g++ without dependency downloads.
- [ ] 6. Operations: CLI demo/import/backtest/validate/report/research packet, offline container definition, CI definition, local commands, runbooks and plan coverage map.
- [ ] 7. Verification: run Python unittest, native strict build/tests and end-to-end demo. Review spec compliance and code risks. Commit and push completed increments. Verify remote head equals local head.

## Corrections and deferred work

The proposal's guaranteed latency, uptime, profit, autonomous authentication and statistical certainty claims are not accepted. Local measurements do not establish broker or venue latency. AC is a model with assumptions, not a guarantee of passive fills. CPCV/DSR/PBO are diagnostics, not automatic approvals. Brokers, authentication, fee schedules, data subscriptions, broker state reconciliation adapter, exchange calendars/corporate actions, calibrated impact, real datasets, model installation, remote deployment, operational latency/HA measurements and live approval require later authorized integration or unavailable external inputs. Local interfaces and runbooks prepare those steps.

## Primary references checked 2026-10-03

- Almgren & Chriss, Optimal Execution of Portfolio Transactions: https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf (original paper hosted mirror; use linear-impact model assumptions).
- Bailey & López de Prado, Deflated Sharpe Ratio: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf (authors' paper).
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html (explicit transactional import; no network dependency).

Implementation-specific methods and limitations will be documented alongside code. Broker, pricing and regulatory claims are deliberately not relied on in this offline implementation.
