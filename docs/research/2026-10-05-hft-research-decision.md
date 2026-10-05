# HFT research decision: prove executable edge before expanding the system

Research reviewed 2026-10-04 to 2026-10-05. Decision date: 2026-10-05.
Status: research and planning, **not a profitable strategy or trading authorization**.

## Executive summary

The project needs a change in research direction, not a wholesale code rewrite. Its
implemented strategy is a daily SPY trend experiment, tested on invented data. That
does not meet the user's HFT objective. The existing accounting, experiment records
and failure-control work remain useful, but another dashboard or broker connection
would not establish a trading advantage. The immediate deliverable should be an
economic feasibility experiment with the power to reject the strategy.

Select one research candidate: short-horizon, long-or-cash SPY order-flow prediction,
with an explicit no-trade decision and conservative aggressive-execution accounting.
Start with small linear models and a tightly bounded trial count. This is a choice
of what to investigate, not a finding that SPY or this model is most profitable.
Retain the daily strategy as a separate benchmark. Do not put Laya, reinforcement
learning, continuous two-sided quoting, or a systems-language rewrite on the next
milestone's critical path.

True latency-race HFT is not an approved deployment direction on the current
unmeasured IBKR/desktop setup. Published research gives useful mechanisms for
prediction and inventory control, but their datasets, queue access and execution
assumptions do not transfer automatically. A direction classifier can be accurate
while its trades lose money. A passive quote can earn the spread primarily when
the next price movement goes against it. Brokerage minimums can overwhelm a small
per-share edge.

The revised plan therefore requires licensed event data, an explicit description
of what the executable feed can observe, realistic costs, latency sensitivity,
chronological selection, a sealed test period and prospective observation. If the
candidate fails, record the failure and stop that branch. Do not rescue it by
continually changing horizons, symbols or fill assumptions. No return target,
hourly trade count or production-readiness claim is supported yet.

## Scope and method

This review asks what can be tested and eventually executed with the proposed
Windows/WSL2, RTX 3070 Ti, 32 GB RAM and IB Gateway setup. The development machine is
a different Mac; no benchmark here measures the user's GPU or network. Capital,
account pricing, market-data permissions, subscription budget and execution latency
are unknown. Numerical thresholds below are proposed experiment rules, not measured
facts or universal trading standards.

Three parallel reviews examine [market making](hft-review/market-making-evidence.md),
[prediction](hft-review/orderbook-prediction-evidence.md) and
[broker/data feasibility](hft-review/broker-data-feasibility.md). Primary papers,
author repositories, exchange specifications and official broker documentation
take precedence over GitHub popularity and social-media performance claims. The
notes distinguish theoretical results, empirical prediction, simulated trading and
actual trading evidence. This is a targeted literature review, not an exhaustive
survey or independent reproduction of every paper.

## 1. The objective is executable profit, not prediction accuracy

For a completed long trade of Q shares, the accounting identity is:

`net P&L = Q * (actual sell fill - actual buy fill) - all transaction charges`.

Monthly economic profit also subtracts data, infrastructure and other incremental
operating costs. Mark open inventory to a conservative executable liquidation
price, not the entry price. Spread and impact already reflected in actual fills
must not be subtracted twice. Before actual fills exist, replay must explicitly
model the difference between observable quotes and attainable prices.

Dixon's trade-information framework connects prediction errors to expected P&L
through fill probabilities and position-dependent trading rules. Its relevance is
the separation between a statistical prediction and a monetizable action; it does
not supply a transferable profitable model for this repository. [Dixon, 2017/2018](https://arxiv.org/abs/1710.03870)

Our proposed aggressive-entry label is the later executable bid minus the delayed
entry ask, measured per share before explicit commissions. It incorporates both
spread crossings through prices. The entry decision then compares the forecast
with size-specific fees, additional slippage/impact allowances and a fixed
uncertainty buffer. A model of mid-price movement is still useful diagnostically,
but cannot supply the reported net trading return. A marketable limit order also
can fail or partially fill: replay must preserve that possibility rather than
silently treating a quote as a completed trade.

Passive market making requires a different joint problem: whether an order fills,
when it fills, the adverse price movement conditional on that fill, inventory risk,
and the cost of exiting the position. Unconditional price prediction and an
independent, optimistic fill probability miss their dependence. The
[market-making review](hft-review/market-making-evidence.md) explains why queue and
latency assumptions are essential and why textbook optimal quotes are research
baselines rather than a deployment recipe.

No desired number of trades enters the optimization objective. Frequency is an
output of the threshold, holding period, costs and risk state. More opportunities
can increase gross P&L while reducing net P&L. A correct result may be zero trades.
The reporting contract must show opportunities, abstentions, order attempts,
partial fills, completed round trips and active trading hours separately.

## 2. Data and execution determine which model is meaningful

An exchange order book, a consolidated best quote, a broker depth view and a
periodically sampled quote are different observations. The initial manifest must
identify venue coverage, aggregation, timestamp origin and update semantics.
Never describe consolidated displayed size as a trader's FIFO queue position.
Never reproduce exchange-feed research with a different broker stream and assume
the same feature distribution or signal lifetime. See the official-source
[feasibility review](hft-review/broker-data-feasibility.md).

For SPY, consolidated executable-quote coverage and the identity of the venue
producing book features must both be explicit. A single-venue feed can support a
single-venue scientific experiment; it cannot establish IBKR SMART execution
economics by itself. The first experiment is blocked if comparable features and
execution references cannot be obtained. This is more informative than pretending
daily OHLC data contain the queue information required for HFT.

The recorder design needs exchange time where supplied, local monotonic receipt
time, UTC correlation and clock uncertainty, feed sequence/ordering information,
gaps, corrections, connection state and trading status. Only events received by a
decision time may form its features. Late messages must remain late in replay.
When historical data omit receipt times, explicitly label synthetic delay
scenarios; they are not measured feed latency. Subtracting unsynchronized clocks
does not measure one-way latency, and half an acknowledgement round trip is not a
measured exchange arrival time.

Measure feature computation, inference and risk processing separately from feed,
gateway, routing, acknowledgement and cancellation delays. Report distributions
and tail behavior under bursts, not just a mean. GPU acceleration might shorten
one component while leaving the dominant external component unchanged. The 3070 Ti
is optional research hardware until a specific model and batch size are benchmarked.
The initial linear models do not justify a GPU dependency.

Queue-aware replay is worth studying, but software adoption is conditional.
HftBacktest provides latency and queue modeling; its replay cannot change the
historical market, so liquidity consumption and impact remain limitations. Current
repository documentation includes L2/L3 support; older versioned pages describing
only market-by-price are not a statement about every current release.
[HftBacktest source](https://github.com/nkaz001/hftbacktest),
[order-fill documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html)

ABIDES offers interacting agents and configurable network latency; JAX-LOB offers
GPU-parallel simulation. They answer useful simulation questions but introduce
calibration requirements. Neither simulator's existence validates the simulated
counterparties, our fill assumptions or future profit. Defer both until an empirical
question requires them. [Byrd et al., 2019](https://arxiv.org/abs/1904.12066),
[Frey et al., 2023](https://arxiv.org/abs/2308.13289)

## 3. Small-account economics can reject the idea before model complexity

The following is **illustrative arithmetic, not an account quote**. Assume a $600
stock, a $0.01 total quoted spread, $0.005/share commission with a $1 minimum per
order, one buy and one sell, and no additional charges or slippage. These are
deliberately incomplete assumptions; actual pricing must be loaded from a dated
account-specific schedule. The official [US stock commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
distinguishes pricing plans and applicable external charges.

| Shares | Purchase notional | Two commissions | Spread cost | Break-even favorable mid-price move/share |
| --- | ---: | ---: | ---: | ---: |
| 1 | $600 | $2.00 | $0.01 | $2.010 |
| 10 | $6,000 | $2.00 | $0.10 | $0.210 |
| 16 | $9,600 | $2.00 | $0.16 | $0.135 |
| 50 | $30,000 | $2.00 | $0.50 | $0.050 |
| 100 | $60,000 | $2.00 | $1.00 | $0.030 |
| 500 | $300,000 | $5.00 | $5.00 | $0.020 |

Formula: `spread + 2 * max(1, 0.005 * Q) / Q`. In the 16-share example, $0.135
is 2.25 basis points of the assumed price, before slippage, external charges and
operating costs. Increasing size to reduce minimum-commission drag increases
capital and exposure requirements. Cash turnover also depends on settlement:
selling a position does not automatically restore settled purchasing power. The
replay must track unsettled proceeds before estimating intraday frequency.
[SEC cash-account guidance](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9). It is
not a free optimization, and sizes that
exceed available settled cash are invalid. This table does not recommend leverage.

Fixed costs matter independently. At a hypothetical $100/month incremental cost,
100 completed round trips require another $1 per round trip; 1,000 require $0.10.
Do not increase trading to amortize that bill unless each additional trade has
positive expected contribution. A hypothetical $0.50 contribution per round trip
would require 200 round trips merely to cover $100, before compensation for risk.
These examples demonstrate arithmetic only; none is a forecast.

The experiment must produce a size-by-cost-by-delay feasibility surface. Freeze
one affordable primary size and one actual pricing configuration before comparing
candidates. Other sizes are sensitivity diagnostics, not extra chances to pick a
winner after inspecting results. Where there is no affordable positive-cost region,
stop. Switching to futures or crypto solely because a backtest omits their fees,
contract exposure or venue risk is not a solution.

## 4. The validation process must withstand model selection

A large event count does not imply many independent trading opportunities. Nearby
labels overlap; trades share market regimes; repeatedly testing a holdout makes it
part of selection. White's Reality Check explicitly addresses the best model in a
searched family relative to a benchmark. The plan therefore records every attempted
variant, not just the final six displayed in a report.
[White, 2000](https://www.ssc.wisc.edu/~bhansen/718/White2000.pdf)

Bailey and colleagues' probability-of-backtest-overfitting framework motivates
examining selection instability. Their combinatorial procedure is a diagnostic,
not permission to replace a chronological deployment test with shuffled financial
history. The Deflated Sharpe Ratio addresses selection and non-normality under its
assumptions; its effective independent trial count is not automatically the raw
number of grid combinations, and its output is not a probability of future profit.
[Bailey et al., 2015 manuscript](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf),
[Bailey and Lopez de Prado, 2014](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)

The proposed first study uses a fixed 120-session calendar window plus boundary gaps:
60 for development, 30 for chronological selection and 30 sealed for a single
final assessment. This is a planning minimum, not a claim of statistical power.
Fit scalers and all preprocessing on training data. Purge labels that cross a
boundary, use complete session gaps, and retain failed/data-invalid sessions in an
exclusion ledger. Calendar periods are fixed before reading strategy outcomes. Outage days remain
in the economic denominator; incomplete outcomes cannot be replaced with clean days.

For uncertainty, resample contiguous blocks of daily net results, preserving
within-day dependence, with block-length sensitivity and an explicitly documented
estimator. Ledoit and Wolf show why Sharpe comparisons need inference that accounts
for time dependence and heavy tails. Do not apply an IID trade-level Sharpe test
to thousands of overlapping labels. [Ledoit and Wolf, 2008](https://www.ledoit.net/Robust_Sharpe_2008.pdf)

An experiment may be valid and inconclusive. A positive mean with a confidence
interval spanning zero is not a pass; insufficient precision is a reason for new
prospective data, not a license to relax the criterion. Likewise, testing many
block lengths and reporting only the favorable one is another selection step.
Declare the primary method first and display every required sensitivity result.

## Synthesis: selected and rejected branches

| Branch | Decision now | Condition to reconsider |
| --- | --- | --- |
| Simple order-flow directional model | First research experiment | Data, executable cost and delay feasibility must pass |
| Daily SPY trend | Preserve as separate control | Real historical evaluation needed; not evidence of HFT capability |
| Passive market making | Defer | Venue-specific queue data, fill/markout calibration, inventory and cancellation evidence |
| DeepLOB/other neural predictor | Challenger only after baseline | Same data/splits/costs; incremental net benefit exceeds complexity and latency |
| Laya/news or local language model | Defer from trading path | Separate timestamped information hypothesis and incremental evidence |
| RL/agent-based simulation | Defer | A specified control problem and externally calibrated simulator |
| Colocation/direct-access HFT | Separate, currently unapproved branch | Measured edge decay, direct feed/routing plan, all-in budget and explicit authorization |

These are project decisions, not claims that the deferred techniques never work.
The [prediction review](hft-review/orderbook-prediction-evidence.md) records what
the selected literature actually tests, including the differences between event
horizons and wall-clock horizons, historical train/test splits and transaction-cost
assumptions. Newer or more complex models receive no automatic preference.

## Recommendations and remaining uncertainty

Execute the [revised research plan](../plans/hft-edge-research-plan.md) in order:
resolve economic inputs and data semantics, freeze the experiment, build only the
necessary replay/label path, evaluate once, then decide whether broker-observed
shadow measurement is worth doing. No additional feature count substitutes for a
completed empirical gate. Preserve the tested risk code as a reference, but extend
its accounting and asynchronous reconciliation before treating it as an IBKR adapter.

We still lack a licensed real event dataset, observed execution costs, target-machine
timings and any demonstrated edge. The user's Gateway TCP connection establishes
network reachability only. Paper simulation can exercise operational behavior but
cannot certify actual queue priority or price impact. The correct current outcome
is a better specified, falsifiable research program. It may conclude that this
strategy should not trade.

## Bibliography and research appendix

Primary sources used directly above: Dixon (2017/2018), White (2000), Bailey et al.
(2015 manuscript), Bailey and Lopez de Prado (2014), Ledoit and Wolf (2008), Byrd
et al. (2019), Frey et al. (2023), HftBacktest maintainer documentation and the
IBKR stock pricing schedule. Each has a direct link at its associated claim.
The three evidence notes provide the remaining paper titles, primary links,
empirical scope, limitations and implementation consequences; together they are
the full bibliography for this research package.

Search families included order-flow imbalance, queue imbalance, microprice,
DeepLOB and later reproducibility studies; inventory-aware market making, queue
position, adverse selection and latency; broker data semantics, fees and paper
fills; and dependent-data validation and selection bias. Accessible abstracts were
used only for abstract-level claims; full-text limitations are identified in the
evidence notes. We did not run the papers' training code or independently reproduce
their numerical results. No paid data, cloud resources, credentials or account
access were used. All proposed acceptance thresholds are our design decisions.
