# Robust daily trend system

Decision: 2026-10-06. The user authorized project-wide adjustments using the
comparison with the supplied report and delegated implementation choices.

## Direction

Keep deterministic daily SPY long/cash trend research. It is a hypothesis for a
bounded investment overlay, not established alpha, intraday trading or a promise
of safety. Prefer a smaller sleeve to adding crypto, FX, grid, DCA, AI or new
execution infrastructure before evidence exists. No account access, downloads,
notifications, deployment or orders are authorized by this development task.

Alternatives considered: extending to multiple markets now adds data, custody and
portfolio accounting before the baseline has evidence; adopting a framework now
adds operational complexity without validating the signal. Strengthen the existing
standard-library baseline first.

## Research and risk policy

Preserve `spy-daily-v1` byte for byte. Add `spy-trend-v2` with the same simple
100/150/200 SMA hypotheses, a 25% entry target, 30% entry exposure cap and 10%
latched drawdown entry halt. These are conservative research defaults, not personal
allocation advice or stop-loss guarantees. Positions can appreciate past entry
limits; drawdown controls do not force liquidation or cap realized losses. Cash
yield, taxes, settlement delays and observed execution calibration remain open.

Past dates are publicly known: changing settings does not create fresh out-of-sample
history. Share the existing v1 experiment registry so previously released sessions
cannot be reused by renaming the study. If v1 has consumed these dates, v2 release
is deliberately blocked: it needs a separately frozen protocol on fresh future
dates. Do not delete the registry or rename data to reopen history. Use unique run
IDs; never overwrite v1 artifacts. Forward observations are prospective evidence.

Add expanding-window walk-forward diagnostics using only development/validation
sessions, chronological embargo and frozen candidate selection before each next
test interval. Add deterministic paired moving-block resampling of net daily
equity returns at 2x costs, reporting return/drawdown distributions and benchmark
differences. These are scenario diagnostics, not probabilities of future success,
significance tests or new holdouts. Holdout observations do not enter selection,
metrics or resampling; provenance hashes cover the complete supplied input.
Keep candidate sensitivity and 1x/2x/5x costs visible.

## Enforced readiness

Every operational runner script must validate completed historical holdout evidence,
matching frozen config/protocol/code/dataset identities and historical provenance,
plus the mechanical `proceed_to_shadow` verdict, before network access or proposals.
Verify the immutable study bundle, not the changing current daily bundle. Compare
the frozen original base config; permit only its selected lookback in a derived
planning config. Authenticate validation, freeze, holdout and event identities
against read-only registry contents. Reject nonfinite or impossible metrics.
Missing, corrupt, mismatched, negative or rejected evidence fails closed. Selection
may change only the lookback listed in the frozen artifact. The offline planning
CLI remains usable for explicit synthetic rehearsals; it cannot send orders.
Low-level `live-inputs` and `market-clock` remain explicit read-only operator tools,
not approved strategy workflows. A cached daily plan must still pass readiness and
match integrity-verified ledger bytes before the scripts print it.

The study command may fetch data when invoked by an authorized operator, but the
daily runner no longer initiates a study implicitly. `--check` checks readiness
before external setup checks. No custom CONFIG override bypasses readiness.

## Durable risk memory

Plan and record a session in one SQLite transaction. Compute the observed NAV peak
and a latched entry halt from verified prior ledger reports as well as the current
declared portfolio peak. A lower declared peak or recovery does not clear a breach.
Serialize concurrent decisions; identical retries return stored bytes, altered
inputs fail, and new out-of-order sessions fail. Corrupt history fails closed.
Existing memory is validated before any read/retry; exact retry is resolved before
recomputing a proposal. Legacy history without recorded
risk memory blocks new sessions until a separately reviewed migration; it is not
silently reconstructed from incomplete old report fields. Only valid economic marks
update observed peaks and drawdown latches; valid losses during manual trading halts
must still latch.
Include memory in the report and decision identity. Signal exits remain eligible;
manual global halts and invalid inputs still block proposals. No automatic reset.

## Operations and presentation

Write a local runner heartbeat on a short interval while waiting. An independent
offline health checker reports stale, future, missing or failed heartbeat status
and missing expected daily decisions. This checker must be invoked by a separate
scheduler to detect a dead process; the process cannot alert about its own death.
No external monitoring service is installed or contacted by this task.

Update README, SETUP, delivery plan and operator/component documentation around
the actual current workflow. Mark original HFT/AI/framework plans historical or
deferred. Avoid profitability claims and distinguish software tests, research
evidence, shadow monitoring and broker execution.

## Validation and sources

Use regression tests for readiness bypasses, stale/mismatched evidence, causality,
deterministic diagnostics, paired resampling, restart/recovery risk latching,
ledger integrity/concurrency and health deadlines. Run `make check build demo`.
All integration tests use local synthetic fixtures or mocked transports.

Primary sources accessed 2026-10-06:
- [AQR trend-following research](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing): motivates testing slow trend hypotheses; diversified futures results are not evidence for this SPY rule.
- [Bailey et al., Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253): selection across trials can overfit; more historical diagnostics do not establish an edge.
- [IBKR Web API documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/): individual trading API eligibility requires a funded Pro account; no integration is implemented here.
- [IBKR paper limitations](https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm): simulation differs from actual execution; broker paper fills cannot prove live execution quality.
