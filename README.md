# Daily trend research and shadow system

A deterministic daily **SPY trend overlay** with bounded entry allocation,
chronological research, independent risk checks and a durable shadow decision
ledger. The repository keeps its historical name, HFT-IBKR, but the current system
makes one decision per trading session and may hold a position for months.

**It never places, changes or cancels broker orders.** Historical replay, synthetic
order-control simulation, shadow decisions and future broker execution are separate.
The strategy has no demonstrated edge or live performance record in this checkout.

Start with [SETUP.md](SETUP.md). The current direction and remaining work are in the
[delivery plan](docs/plans/quant-trading-delivery-plan.md).

## The strategy

At yesterday's completed close, compare a causal dividend-aware SPY price index
with its simple moving average. Above the average means LONG; at or below means
CASH. The next session's open is the historical execution assumption. The shadow
runner prices buys at the current ask and sells at the bid after the open.

The study tests only 100-, 150- and 200-session lookbacks. Validation at 2x modeled
costs selects one; the choice is frozen before the final holdout. The strategy does
not top up or rebalance daily. LONG while already invested means HOLD; CASH with
shares means a full SELL proposal, subject to admission limits.

The [revised research protocol](studies/spy-trend-v2/PROTOCOL.md) treats this as a
smaller investment overlay:

| Research default | Value | What it means |
| --- | --- | --- |
| Entry target | 25% of declared strategy NAV | Leaves most of the modeled account in cash |
| Entry exposure cap | 30% | Bounds a new purchase; appreciated holdings can exceed it |
| Drawdown entry halt | 10% from the observed/declared peak | Latches against new buys; does not liquidate holdings |
| Funding | Settled cash, whole shares | No margin, leverage or shorts |
| Order/share caps | $100,000 / 1,000 shares | Additional maximums; cash and allocation can reduce size further |
| Participation cap | 0.1% of previous-session volume | Uses prior information; full exits can be rejected |

These values are research assumptions, not a recommended personal allocation.
**The drawdown threshold is not a maximum-loss guarantee.** This is an investment
sleeve, not a stop-loss strategy with a fixed percentage of equity at risk per trade.
Gaps, slow signal exits and rejected full exits can produce larger losses.

## Evidence before the daily runner

The original `spy-daily-v1` study is retained unchanged. Its 95% allocation and
20% entry-halt settings cannot qualify the revised strategy.

The new study uses 2016–2026 history, chronological development/validation/final
holdout periods, five-session embargoes and costs at 1x/2x/5x. It compares the trend
rule with buy-and-hold using the **same allocation and risk policy** and zero-yield
cash. A smaller allocation alone is not evidence of strategy advantage.

At 2x costs, the rule must have a nonnegative return and lower drawdown than its
matched buy-and-hold benchmark. Higher or equal return is DOMINATES; lower return
with lower drawdown is RISK_REDUCING and supports only the overlay interpretation.
Other outcomes reject progression. This mechanical gate is historical screening,
not proof of significance, profitability or suitability.

Both daily operator scripts check the immutable study bundle, frozen selection,
actual base config/protocol, research source identity and authenticated registry
results **before reading keys, calling services or printing cached decisions**.
Missing, rejected, synthetic, corrupt or mismatched evidence stops the workflow.
Only the frozen selected lookback may differ in the derived planning config.
The changing daily data bundle is validated separately.

The shared original experiment registry prevents renamed studies from reusing
released historical sessions. **If v1 already consumed the proposed v2 holdout,
v2 is blocked and requires a separately frozen study on fresh future dates.** Do
not delete a registry or change dataset labels to bypass this. Changing code can
also invalidate frozen evidence; requalification cannot reopen a consumed holdout.
Publicly known historical data is not fresh prospective evidence in either study.

## Robustness diagnostics

The `research robustness` command adds expanding-window walk-forward testing and
paired moving-block resampling of net daily returns. It uses development and
validation history only; final holdout prices never enter the calculations.

Each fold selects on earlier data, skips the embargo, then tests the frozen choice
at 1x/2x/5x costs. Resampling at 2x costs uses identical return-block indices for
trend and matched buy-and-hold, with a fixed seed and declared block/sample counts.
Reports show return/drawdown distributions, benchmark differences and limitations.
Resampled drawdown uses closing marks; replay drawdown also includes open and
post-fill marks. Resampling does not rerun the strategy or its risk controls.
They are conditional scenario diagnostics, not probabilities of future success.
Diagnostics cannot change the final study selection or rescue a rejected holdout.

## Daily decisions and persistent controls

Once qualifying evidence exists, the runner waits for the exchange calendar's
session and records one decision a minute after the open, normally 09:31 New York.
Holidays, early closes and daylight-saving changes follow the declared calendar.
The validated bundle contains bars through the previous session; today's prices
cannot change the signal.

Data/calendar/dividend checks, stale or future quotes, stale portfolio snapshots,
manual halts, declared unreconciled/pending/uncertain state, cash, exposure and
liquidity limits can block a proposal. The portfolio remains a **manual shadow
book**, not broker-verified holdings or fill accounting. An IEX quote is one venue's
quote, not the national best quote.

SQLite serializes planning and recording together. Valid marks preserve observed
peak NAV and a latched drawdown entry halt across restarts and lower declared peaks.
A recovery does not clear the latch. Invalid marks do not raise the observed peak
or permanently latch a new drawdown. Identical retries recover the stored bytes;
changed inputs or new out-of-order sessions fail. Corrupt history blocks progress.
Legacy ledgers without risk memory require reviewed migration; retain them.

A manual global halt blocks all proposals. A drawdown halt blocks new buys while
allowing signal exits. Neither means the account is flat. No automatic halt reset,
partial exit policy or continuous intraday risk monitor is implemented.

## Operations

On a genuinely fresh checkout, the explicit study command can initialize the
shared registry offline. If legacy artifacts exist without their registry, or
older releases lack session claims, it stops for reviewed recovery/migration.

| Component | Purpose |
| --- | --- |
| `quant_data` | Strict daily prices/dividends/calendar intake and hashed bundles |
| `quant_research` | Signals, cost-aware replay, chronological selection, holdout registry and robustness diagnostics |
| `quant_session` | Declared shadow inputs, independent admission, atomic decision/risk ledger and offline readiness |
| `scripts/run_study.sh` | Explicit operator study workflow; never runs implicitly from the daily runner |
| `scripts/run_daily.sh` | Evidence gate, daily schedule, local heartbeat and optional phone notifications |
| `scripts/check_shadow_health.py` | Independent offline health/deadline check |
| `quant_control` | Separate SIM-only order reservation/reconciliation/journal reference |
| `quant_view` | Offline snapshot dashboard |

The runner emits a local heartbeat while waiting. The health checker detects stale,
future, missing, stopped or failed heartbeats and missing decisions after a deadline.
**Run it from an independent scheduler to detect a dead runner.** No remote monitor
or scheduler is installed. Optional ntfy notifications require operator setup and
cannot detect death of their own sending process.

Low-level `session live-inputs` and `session market-clock` remain explicitly invoked
read-only data tools; they do not qualify a strategy or submit orders. The offline
`session plan` CLI supports synthetic rehearsals independently of study readiness.

## Costs and limits of the evidence

The revised study assumes 2 bp adverse execution per side (spread, slippage and
impact combined), configurable fees and 1x/2x/5x stress. These are conservative
scenarios, not observed broker fills. The inherited commission/sell-fee assumptions
are recorded in the protocol; actual account/venue costs must be calibrated before
any broker integration. Cash yield, taxes, settlement timing, queues and auction
execution are excluded. With most capital in cash, omitted cash yield matters.

Passing tests establishes software behavior. One SPY price path, few independent
trades and familiar public history cannot establish statistical significance.
Forward shadow observations and economic/calibration review remain outstanding.

## Verify locally

Python 3.11+; standard library only. No credentials or network are needed:

```sh
make check build demo
```

This builds the portable application and creates explicitly synthetic reports and
a dashboard under ignored `.research-output/`. Real market data is not bundled.
See the [component reference](docs/reference/components.md) for individual commands.

Crypto/FX, grid, DCA, AI signals, framework migration and broker execution are
**deferred**. Add a component only after a frozen comparison demonstrates its
incremental benefit after costs and its risk/operational burden is addressed.
The [October 6 design](docs/superpowers/specs/2026-10-06-robust-trend-design.md) records
these decisions and primary sources. Earlier HFT proposals are historical context.
