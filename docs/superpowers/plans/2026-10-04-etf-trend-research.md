# Daily ETF Trend Research Implementation Plan

> For agentic workers: use executing-plans and test-driven-development. The user
> delegated market/design decisions and authorized development. Implement this
> research slice inline in the existing feature worktree.

Goal: a runnable offline SPY daily-trend simulator with costs, risk checks,
dividend accounting, a comparable benchmark and reproducible reports.

Specification: [R1 design](../specs/2026-10-04-etf-trend-research-design.md).
Architecture: validated local input -> causal signal -> independent risk gate ->
simulated next-open fill -> portfolio accounting -> deterministic research report.
Tech stack: Python 3.14 standard library; Decimal; unittest.

- [x] Task 1 — `quant_research/config.py`, `data.py`, `serde.py`:
  write `tests/test_inputs.py`, confirm absent-module failure, implement immutable
  records, strict config/provenance/calendar/hash/CSV validation, run tests green.
- [x] Task 2 — `strategy.py`, `costs.py`, `risk.py`:
  write `tests/test_strategy_risk.py`; establish red; implement causal SMA, explicit
  execution cost components, whole-share cash/exposure sizing, and drawdown latch;
  verify boundary, gap, capacity and prefix-invariance tests.
- [x] Task 3 — `backtest.py`:
  write `tests/test_backtest.py`; establish red; implement warmup, next-open fills,
  receivables, fees, benchmark alignment and 1/2/5 cost scenarios. Verify manual
  accounting, no lookahead, halt and end-position tests.
- [x] Task 4 — `__main__.py`, `tests/test_cli.py`, `examples/`:
  establish red; implement exclusive atomic report publication, version/config/input
  hashes, deterministic JSON and meaningful exit codes. Add a labeled synthetic
  fixture and explicit sample config. Verify identical output and socket-blocked
  in-process tests; inspect runtime imports for network/SDK dependencies.
- [x] Task 5 — review and evidence:
  run `python3 -m unittest discover -s tests -v` and
  `python3 -m compileall -q quant_research tests`. Perform independent code review,
  fix material findings and rerun relevant checks; `git diff --check` must pass.
- [x] Task 6 — document outcome:
  update README commands, assumptions, actual completed R1 scope and remaining M1
  work. Record authoritative validation output; do not infer strategy advantage
  from synthetic metrics.


## Validation evidence — 2026-10-04

- Interpreter: Python 3.14.0. No third-party packages installed.
- `python3 -m unittest discover -s tests -v`: 55 tests, all passed.
- `python3 -m compileall -q quant_research tests`: exit 0.
- Full synthetic CLI replay: 460 input sessions, 200 warmup sessions, 260 evaluated
  sessions; trend and buy-and-hold under cost multipliers 1, 2 and 5.
- Two CLI reports compared with `cmp`: byte-identical, exit 0.
- `git diff --check`: exit 0.
- Independent spec review and current-code review approved. Fixed review findings:
  dividend-adjusted SMA equality/flat index drift, ambient Decimal settings,
  consumed-input byte hashes and oversized integer classification. Regression
  cases were demonstrated failing before correction and now pass.
- Socket creation blocked during in-process replay/CLI tests; runtime imports are
  standard-library and local modules only. There is no broker SDK or transport.

Generated report: `.research-output/synthetic-report.json` (ignored local artifact).

Completed R1 scope: input validation, causal trend, independent risk sizing,
next-open simulation, dividend accounting, explicit cost stress, fair-date benchmark,
CLI and reproducibility evidence. This is software verification on invented data;
no historical strategy validation or economic advantage is established.

At the R1 checkpoint, historical validation and M1/M3 were outstanding. Subsequent
M1/M3 software implementation is recorded in their plans. Reviewed historical
data/calendar/corporate actions, calibrated execution and broker integration remain
outstanding. Preserve this feature worktree for continued development.
