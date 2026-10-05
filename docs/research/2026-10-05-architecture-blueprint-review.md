# Review of the "microstructure alpha" architecture blueprint

Reviewed 2026-10-05. Status: **research decision; no trading authorization or
profitability claim.** Scope: a user-supplied blueprint for an i7-13700KF / 32 GB /
RTX 3070 Ti desktop trading through IB Gateway. It proposes NautilusTrader with
ib_async, a local DeepSeek-R1-Distill-Qwen-7B "verifier", multi-level order-flow
imbalance (MLOFI) alpha with PCA, Hawkes filtering, a VPIN toxicity gate and post-only
passive execution. Method:

- Primary-source checks.
- This repository's existing evidence notes.
- A simulation of the G3 acceptance rule's statistical power.
- Two exploratory order-book replications.

No account access, purchase, installation or broker contact occurred.

## Verdict

**Do not build the blueprint as written.** Its three load-bearing pieces fail on evidence:

1. **Alpha.** The MLOFI/PCA results it cites measure how well order flow *explains the
   price change in the same window*. The one cited line of work that tests one-minute-ahead
   *prediction* reports negative out-of-sample R². The authors also state that integrated
   OFI does not significantly beat best-level OFI forward. Our two replications agree:
   same-window fit is high, forward predictive R² is about zero, and the blueprint's
   1.5-sigma rule loses roughly one spread per trade.
2. **Execution.** The proposed post-only + IOC orders cannot rest. Nasdaq's rule text
   forbids that combination. IBKR SMART has no post-only flag for US stocks, and the
   pinned Nautilus IB adapter raises on `post_only`. IBKR says Tiered pricing typically
   does not pass exchange rebate enhancements through.
3. **Integration.** NautilusTrader's IB adapter uses `nautilus-ibapi`, not ib_async.
   Running ib_async with nest_asyncio beside it opens a second, independent IB session;
   it does not bridge to the Rust core.

What survives is either already in the [authoritative plan](../plans/hft-edge-research-plan.md)
or a small, cheap design note: best-level OFI as a lagged feature, headless Gateway,
injected clocks, and broker-side GTD expiry and request pacing for a future adapter. The
plan's ordering stands, and the evidence here shifts expectations toward **REJECT**
for aggressive SPY order-flow trading at retail latency.

## Claim-by-claim

| Blueprint claim | Finding | Decision |
| --- | --- | --- |
| Sub-ms HFT is impossible here; target 100 ms–minutes | Consistent with [broker feasibility](hft-review/broker-data-feasibility.md) | Already adopted |
| IBKR sends only 250 ms (VWAP) snapshots, so features must use snapshots | 250 ms applies to `reqMktData` L1 only. `reqTickByTickData` BidAsk and `reqMktDepth` exist. No source describes the snapshots as VWAP. | Any recorder uses tick-by-tick BidAsk with `ignoreSize=False` |
| 50 msg/s hard limit, error 100 | This is request pacing (market-data lines / 2 per second), not an inbound-data ceiling | A future adapter rate-limits outbound requests and prioritizes cancels |
| 50–250 ms order round trip | No current IBKR source; the only IBKR figure found was a ~2013 options-routing brochure | Unmeasured; keep the plan's delay scenarios |
| OFI formulas (Cont–Kukanov–Stoikov) | Formulas correct; the published result is contemporaneous price impact | Already plan feature set B, used lagged |
| "10-level MLOFI cuts RMSE 65–75%" | Real figure, misapplied: ridge, 5-fold CV, *contemporaneous* 10 s price changes, six Nasdaq stocks in 2016, large-tick only (small-tick 15–30%); no forecasting regression and no PCA ([Xu, Gould & Howison, §6.1](https://arxiv.org/abs/1907.06230)) | Not prediction evidence; MLOFI is at most a later challenger if depth data exist |
| MLOFI-PCA scalar | PC1 explains 89.06% of variance; contemporaneous OOS R² 64.64% → 83.83%; **one-minute-ahead OOS R² is negative** (best-level −0.37%, integrated −0.36%, Table 8). The authors say integrated OFI "cannot significantly outperform" best-level forward, and their P&L illustration "ignores trading costs" ([Cont, Cucuringu & Zhang](https://arxiv.org/abs/2112.13213)). | Reject as the alpha basis |
| Trade when rolling z > 1.5 | The rule has no cost or spread term; replications below lose about one spread per trade | Reject; the plan's cost threshold already supersedes it |
| Hawkes filtering improves the signal | Review literature is descriptive ([Bacry, Mastromatteo & Muzy](https://arxiv.org/abs/1502.04592)); no trading-relevant out-of-sample gain found | Reject for now |
| VPIN halts quoting under toxicity | Andersen & Bondarenko (J. Financial Markets, 2014) find its signal largely mechanical. Bulk-volume classification error is material, and VPIN adds no incremental volatility prediction after volume/volatility controls. A broker-aggregated feed is coarser still. | Reject |
| Avellaneda–Stoikov passive entry with re-pegging | Theory, not a deployment recipe; slow resting orders fill disproportionately when adverse ([market-making review](hft-review/market-making-evidence.md)) | Remains deferred |
| Post-only + IOC to earn maker rebates | Contradictory: a post-only order must rest, and Nasdaq forbids an IOC time in force on post-only orders ([SR-NASDAQ-2021-094](https://www.sec.gov/rules/sro/nasdaq/2021/34-93569.pdf)). IBKR SMART has no post-only flag; Nautilus v1.231.0's IB adapter raises `ValueError` on `post_only`. IBKR "typically will not directly pass" rebate enhancements ([commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)). | Reject; never model rebates as income |
| GTD cancels stale quotes broker-side | Supported for SMART US stocks with second granularity (`goodTillDate`, [Order API](https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html)) | **Adopt for future adapter design**: orders carry broker-side expiry so a crashed client cannot leave one resting. Cancellation evidence is still reconciled, never assumed. |
| IB Gateway on 4002 (paper), not TWS | Correct (4001 live) | Already in the [Gateway setup](../operations/paper-gateway-setup.md) |
| ib_async + nest_asyncio bridges Python to the Nautilus Rust core | Wrong. Nautilus's `TradingNode` runs its own asyncio loop with the `nautilus-ibapi` client. ib_async 2.1.0 (BSD-2) docs recommend `util.startLoop()` for notebooks, not nest_asyncio. | Use one client per process: ib_async alone for a simple read-only recorder, or Nautilus alone |
| Nautilus gives byte-for-byte backtest/live parity, 128-bit precision, Redis state | v1.231.0 (2026-08-02), LGPL-3.0, Python 3.12–3.14. 128-bit precision is not on Windows; Redis cache is supported; L2/L3 queue fill is a probabilistic model. Identical code does not mean identical fills or latency. | Keep as the planned F1 offline study; not needed for the aggressive-only G2 replay |
| Rust memory safety removes trading bugs | Memory safety is not logic, accounting or reconciliation correctness | No change |
| 32 GB RAM forces DuckDB/Parquet | One symbol at 250 ms L1 is about 93,600 updates/day. The NVDA sample day is 1.7 M top-of-book rows (274 MB CSV). Single-symbol research is not RAM-bound. | Use Parquet/DuckDB later if vendor data or volumes call for it; not urgent |
| Local DeepSeek-R1-Distill-Qwen-7B as private logic verifier for frontier coding agents | The cited 92.8% is MATH-500, not GSM8K; LiveCodeBench is 37.6% ([DeepSeek-R1](https://arxiv.org/abs/2501.12948)). vLLM GGUF is "highly experimental". The 3070 Ti has 608 GB/s, not 448 ([NVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3070-3070ti/)). A 7.65/8 GB plan leaves no display headroom. Newer small models exist. | Reject from the trading and verification path; at most an optional private assistant |

## Exploratory replications

Both replications use the same causal pipeline. Features at decision time `t` use
only rows received strictly before `t`, on a one-second grid from 10:00 to 15:30 New
York time. Each run uses a 60/40 chronological split within the day, with a 120 s gap,
and fits OLS on the training part only. Targets are:

- **Same-window move:** `mid(t) − mid(t−w)`.
- **Forward move:** `mid(t+h) − mid(t)`.
- **Executable long round trip:** `bid(t+L+h) − ask(t+L)`, with entry delay `L` of
  0.1 or 0.5 s.

Costs are $0.008/share for the round trip on top of the spread: an assumed
$0.0035/share IBKR Tiered commission plus $0.0005/share of other fees per side. Trades
do not overlap. A perturbation test confirmed that rows at or after `t` cannot change
any feature at `t`.

**A. Databento free sample, NYSE Arca `mbp-1`, NVDA, 2025-09-16** ([dataset page](https://databento.com/datasets/ARCX.PILLAR)).

- 1,705,029 rows (SHA-256 `a826e40b…db8388`), timed by `ts_recv`.
- Mean spread 1.09¢; one tick 91% of the time; mid about $175.

| Measure (test period, 7,802 seconds) | Result |
| --- | --- |
| Same-window R², best-level OFI, event data (w = 1 s / 10 s) | 62.4% / 67.5% |
| Same, OFI from 250 ms snapshots | 35.6% / 26.9% |
| Forward R², OFI, h = 1/10/60 s | −0.09% to +0.11% |
| Forward R², L1 queue imbalance, h = 1/10/60 s | 2.56% / 0.32% / 0.09% |
| Mean next move after top-decile OFI | −0.22¢ to +0.26¢, against a 1.08¢ spread |
| Blueprint rule (z > 1.5), 12 configurations | All negative: −1.8¢ to −2.3¢/share net, hit rate 2–36% |
| Model rule, trade only when predicted executable return exceeds costs | Never trades: maximum predicted return is below zero |

**B. LOBSTER sample files, Nasdaq, 2012-06-21** (MSFT, INTC, AAPL, plus a 45-minute SPY
extract), obtained from a third-party mirror because LOBSTER's sample download now
requires registration.

- Same-window fit reproduces.
- Forward R² for OFI and its multi-level, PCA and decay variants stayed within about
  ±1–2%.
- The blueprint rule lost in every main-stock configuration.
- Frictionless mid-to-mid backtests showed small positive "edges" that crossing the
  spread erased.

Detailed figures are withheld from this public repository pending review of LOBSTER's
sample-data terms.

**Limits.** These are single days, one venue's book (not the consolidated NBBO or SMART
execution), and an idealized fill at the displayed quote. Capture timestamps are faster
than a retail feed would be. These are exploratory checks, not a study. They agree with
the literature and support the plan's prior expectation; they do not substitute for
G1–G3. **Exclude 2025-09-16 and 2012-06-21 from any future study window**, since both
dates have now been viewed.

## The G3 sealed test detects only very large edges

Simulated with Gaussian daily P&L, mean and standard deviation set by a true
annualized Sharpe, 600–1,000 replications, and 2,000 bootstrap resamples. The pass rule
is the plan's: positive mean, and a 5th-percentile moving-block bootstrap mean above
zero at block lengths 5, 1 and 10. Student-t(3) days gave slightly higher pass rates.

| True annualized Sharpe | P(pass), 30 sessions | 60 sessions | 90 sessions |
| --- | ---: | ---: | ---: |
| 0 (no edge) | 4.9% | 4.9% | 4.5% |
| 1 | 8% | 11% | 12% |
| 2 | 17% | 22% | 26% |
| 3 | 28% | 42% | 54% |
| 5 | 49% | 75% | 88% |
| 8 | 83% | — | — |

The false-pass rate is controlled. Power is low: a genuine Sharpe-2 strategy is
usually reported INCONCLUSIVE. That suits a pilot meant to catch HFT-scale edges, but
the plan should say so. If free consolidated history from 2016 is available, a longer
sealed window costs only download time. Whether to lengthen it is a
pre-freeze decision for G1. The selection count, horizons and fixed seed are unchanged
by this note.

## Data route for G0

**User decision, 2026-10-05: no purchased data and no paid market-data subscriptions.**
The data budget is $0. The routes below are free as documented on 2026-10-05; items
marked unconfirmed must be checked before relying on them.

| Zero-cost route | What it provides | Requirements and caveats |
| --- | --- | --- |
| Alpaca Market Data, free Basic plan, historical `/v2/stocks/SPY/quotes` with `feed=sip` ([data API](https://docs.alpaca.markets/us/docs/about-market-data-api), [free access](https://alpaca.markets/learn/access-free-market-data)) | Consolidated SIP quotes from 2016: bid/ask price, size and exchange, condition codes; up to 10,000 rows per page | Free email signup with API keys; no funding or card. Request end must be at least 15 minutes old. One timestamp per quote, with no separate exchange and SIP times. The raw data may not be redistributed, so it never enters this public repository. Free rate limit (reportedly about 200/minute) and SPY update counts are unconfirmed. |
| IBKR free real-time Cboe One + IEX quotes ([market-data pricing](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php)) | Live non-consolidated top-of-book through the API. These are the exchanges where IBKR execution actually happens, with receipt timestamps. | Live recording only; 122 sessions take about 6 months. Whether `reqTickByTickData` BidAsk works under this free entitlement is unconfirmed; delayed data does not support tick data. Requires user-authorized read-only account access. |
| IBKR historical bars and ticks under the free Level 1 entitlement ([historical data rule](https://interactivebrokers.github.io/tws-api/historical_data.html)) | Daily and intraday SPY bars; historical BID_ASK ticks with sizes | Likely free, because the API requires only the same Level 1 permission as live data; not separately confirmed for SPY. 1,000 ticks per request plus pacing make months of tick history impractical; daily bars are practical. |
| IEX HIST TOPS files ([download](https://iextrading.com/trading/market-data/#hist-download)) | IEX's own best quote with sizes and nanosecond timestamps; no login | One venue, roughly 4–8% of US volume, so not the NBBO. About 12 trailing months. Attribution required. Useful only as a cross-check. |

Excluded under this decision:

- Databento: its $125 credit requires a card on file, and larger windows are billed.
- Massive Stocks Advanced: $199/month.
- IBKR Network B ($1.50/month) and ArcaBook ($11/month).
- LOBSTER: registration-gated academic licensing.

**Recommended sequence:**

1. Resolve the remaining user-owned G0 inputs: capital, account type and pricing plan.
2. If the user opens a free Alpaca account, download one predeclared window of SPY SIP
   quotes for the frozen study. Store the files outside Git, with hashes and a
   manifest, and label them `quote-flow proxy, consolidated SIP, single timestamp`.
3. Separately, and only with authorization, run a read-only IBKR recorder on the free
   Cboe One + IEX entitlement. It tests whether tick-by-tick BidAsk is available and
   measures receipt delay for G4; it does not select models.

## Account facts close the intraday route (2026-10-05)

The user reported IBKR Lite, a cash account, $25k–$100k for this strategy, and no
data purchases.

- **No API on Lite.** IBKR's [plan comparison](https://www.interactivebrokers.com/en/general/compare-lite-pro.php)
  (header "IBKR Lite | IBKR Pro") marks "IBKR APIs" as not included for Lite. It uses
  the same marker as other Lite-excluded rows, such as institutional accounts.
  Automated Gateway/API trading therefore requires IBKR Pro. Pro brings back per-order
  commissions (Tiered minimum $0.35), which exceed the predicted moves measured above.
- **Cash-account turnover ceiling.** Settled cash must fund each intraday round trip.
  A same-day sale of a position bought with unsettled proceeds is a good-faith or
  freeriding violation. Daily traded notional is therefore at most about settled
  capital, so daily profit is at most capital × net edge per round trip. At a net
  0.5 bp per trip, several spreads more than any edge observed here, $50,000 earns
  about $2.50 per day.
- **Lite fees.** Zero commission; sells pay the SEC Section 31 fee of $20.60 per
  million from 2026-04-04 ([Federal Register](https://www.federalregister.gov/documents/2026/03/04/2026-04233)).
  FINRA's TAF is waived from 2026-10-01 to 2026-12-31 ([notice](https://www.federalregister.gov/documents/2026/09/23/2026-19392)).

**Decision:** the intraday order-flow branch is closed for this account. The project
returns to daily and slower research, which fits a cash account and one manual
order per day on Lite. It uses free Alpaca daily bars, dividends and the exchange
calendar under the pre-registered [`spy-daily-v1`](../../studies/spy-daily-v1/PREREGISTRATION.md) study.

## What this means for the project

The repository's strongest asset is its **research and failure discipline**:

- Causal signals with future-perturbation tests.
- Deterministic Decimal accounting, including dividends.
- An append-only experiment registry.
- Fail-closed control and reconciliation, with a hash-chained journal.

Its main weakness is that this discipline currently surrounds a 39-line daily
moving-average rule evaluated on invented data. About 8% of the non-test code is
strategy, costs, risk and backtest. Documentation runs to roughly 1.75 words for every
word of Python.

A 2026-10-05 code review found and this change fixed:

- **Holdout reuse.** Renaming a protocol or changing code could re-release a sealed
  holdout. The registry now claims revealed sessions per data kind and symbol.
- **Reconciliation stall.** A steady account stream restarted reconciliation forever
  with no halt reason. Invalidations now keep the attempt's deadline.
- **Shadow planner divergence.** The planner blocked signal-driven exits during a
  drawdown breach, which the backtest does not do.
- **Durability and speed.** Journal appends were quadratic. macOS durability now uses
  `F_FULLFSYNC` and SQLite `fullfsync`.

Remaining known gaps:

- The control reducer models no commissions.
- It assumes a single global broker sequence and atomic snapshots, which IBKR does not
  provide. It is an acceptance reference, not an adapter base.
- The two risk engines are unconnected.
- Helpers are duplicated across packages.
- Loaders read whole files into memory, with no streaming event reader.
- Daily stress scenarios multiply commissions, which G3 intraday work must not copy.

**Realistic expectation.** Edges available to a retail participant on SPY at 100 ms or
more of latency appear far smaller than one spread plus commissions. The most likely
G3 outcome is REJECT, or INCONCLUSIVE at best. That result is still worth producing
cheaply, because it stops spending on a branch that cannot pay. If it fails, the
better use of this infrastructure is slower strategies, where costs are a small
fraction of the expected move: the existing daily benchmark on real data, or
minutes-to-days horizons. A faster, rewritten or AI-driven stack does not change that.
