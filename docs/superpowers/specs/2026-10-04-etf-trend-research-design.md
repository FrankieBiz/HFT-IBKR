# Daily ETF trend research design

Decision date: 2026-10-04. User delegated market/strategy selection and authorized
starting development. This design defines a runnable offline research slice (R1).
The full M1 broker-style order/reconciliation engine remains a separate milestone.

## Market decision and evidence

Choose a cash-funded, whole-share, long-only S&P 500 ETF system, initially SPY.
This is a decision about development reliability and research tractability, not a
claim that SPY or this strategy offers the highest prospective return.

| Alternative | Development tradeoff | Decision |
| --- | --- | --- |
| Daily broad-market ETF trend | Single asset, bounded cash-funded position, daily bars, few execution events | Start here |
| Intraday ETF mean reversion | Needs reliable intraday quotes, spread and execution timing calibration; higher turnover costs | Defer until daily pipeline is validated |
| Micro index futures trend | Expiration/roll, leverage, multiplier and margin accounting | Defer |

Primary sources accessed on 2026-10-04:
- [State Street SPY product page](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy): S&P 500 benchmark, USD listing and quarterly distributions. ETF market prices already reflect fund expenses; do not deduct the expense ratio again from raw market-price returns.
- [CME micro futures FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html): MES multiplier and quarterly expiration mechanics establish additional accounting requirements.
- [IBKR stock/ETF commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php): plan-dependent rates, order minimums and third-party fees mean commissions must be configurable. Example costs below are research assumptions, not an account quote or exact broker fee implementation.

Eligibility to buy US ETFs depends on account entity/jurisdiction and permissions;
verify before any account integration. No account, data purchase or deployment is
part of R1. Capital remains a simulator input; the example balance is not an
allocation recommendation.

## Strategy hypothesis

Use a 200-session simple moving average of a causal dividend-aware price index.
At each completed session, LONG when the index is strictly above its SMA; CASH at
or below it. Warmup requires 200 completed sessions. Signals generated at close
are executable only at the next supplied session's open. Trade only on entry/exit;
no daily rebalancing or parameter optimization. Hold durations may span weeks or
months. Overnight risk, whipsaws and missed recoveries remain possible.

A buy-and-hold benchmark starts at the same evaluation session with the same
capital, exposure cap, whole-share sizing, dividends and execution costs. A cash
benchmark returns zero before taxes and cash interest; cash yield is explicitly
excluded. Reports make no alpha/significance claim.

Buy-and-hold tries entry at the first evaluation open and retries until admissible.
Trend targets are recomputed from the latest completed session: a rejected entry
does not survive a signal reversal. Open marks, post-fill open marks and close
marks all update peak NAV and reported maximum drawdown.

## Scope and components

Python standard library, Decimal arithmetic with fixed local precision 28 and
ROUND_HALF_EVEN, immutable records and deterministic JSON output. Existing Orca
worktree is already a feature checkout. No new worktree or dependency installation
is needed.

- `quant_research/data.py`: strict CSV + provenance manifest loading.
- `quant_research/config.py`, `serde.py`: explicit configuration, strict parsing and fixed arithmetic context.
- `quant_research/strategy.py`: causal price index and pure trend signals.
- `quant_research/costs.py`: adverse fill-price and fee model.
- `quant_research/risk.py`: independent cash/exposure admission and drawdown latch.
- `quant_research/backtest.py`: close-to-next-open replay, dividend accounting and metrics.
- `quant_research/__main__.py`: local CLI and reproducibility metadata.
- `examples/`: explicitly synthetic fixture and explicit simulation parameters.

## Data contract

CSV fields, in this order: `session,open,high,low,close,volume,dividend,dividend_pay_date`.
Sessions are ISO calendar dates, strictly increasing. Raw unadjusted OHLC prices
are finite positive decimal strings; OHLC ranges must be consistent. Volume is a
positive whole number. Dividend is nonnegative; positive dividends require a pay
date strictly after ex-date (the row's session). Zero dividends require blank pay
date. Splits are unsupported and the manifest must declare none in this interval.
Reject dividend on the first row because no prior close/entitlement context exists.

Manifest requires schema version, symbol, currency USD, provenance kind
`synthetic` or `historical`, source, retrieved_at UTC timestamp, raw price policy,
corporate-action coverage declaration, no-split declaration, CSV SHA-256,
calendar source and exact expected session dates. Reject unknown/missing fields,
bad hashes, gaps relative to the supplied calendar, duplicate dates and malformed
numbers. Calendar/provenance correctness is supplied evidence, not independently
verified by the loader. Do not present synthetic weekday dates as an exchange calendar.
Historical outputs are exploratory until source/licensing/corrections and calendar
are reviewed. No downloaded dataset is included in this change.

For prices p and dividend d, the causal index is I[0]=p[0] and
I[t]=I[t-1]*(p[t]+d[t])/p[t-1]. This uses only information through t;
it never rewrites historical observations using future corporate actions.
Compute the gross-return ratio before multiplying the index so unchanged prices
preserve it exactly. Accumulate represented index values as exact fractions and
compare `index * lookback` with their sum, avoiding rounded SMA equality errors.

## Replay and accounting

Evaluation start must exist in the dataset and have at least lookback prior
sessions. Pre-evaluation rows warm the signal only; they produce no holdings or
returns. On each evaluated session:
1. Pay previously accrued dividend receivables whose pay date is at or before
   this session, into cash before the simulated open (explicit timing assumption).
2. Accrue today's dividend for shares held at the previous close, before trading.
   Ex-date sales retain entitlement; ex-date purchases get none. Receivables add
   to equity but are unavailable for purchases until paid.
3. Consume yesterday's signal. On entry, desired shares are floor(previous-close
   NAV * target_fraction / previous raw close). Execution sizing may reduce this
   number to fit current-open cash, costs, exposure limits and capacity, never
   increase it. A zero executable size produces an explicit rejected trade.
4. A prior-volume capacity cap is floor(previous session volume * participation
   limit); it uses no current day's completed volume. If a full exit exceeds this
   cap, reject the entire simulated exit and report it; do not silently assume a
   partial fill. Retry desired entry/exit on following eligible sessions.
5. Fill at open adjusted adversely for half-spread + slippage + impact basis
   points. Commission is max(minimum, per-share * shares), plus configured
   exchange/regulatory bps on notional (sell fee separate). All parameters are
   nonnegative required inputs. This is a scenario model, not a calibrated model.
6. Mark NAV = cash + shares * raw close + unpaid receivables. Update peak NAV,
   maximum drawdown and a latched buy-halt when drawdown reaches its configured
   threshold. Sells remain allowed subject to inventory, positive proceeds and
   capacity; no forced liquidation is implied by halt. At next open the same
   drawdown gate checks the known open mark before permitting buys.
7. Generate the next signal using this completed close.

Risk admission is independent of the strategy: simulation mode only, supported
asset/currency, positive whole quantity, finite amounts, adequate cash after fees,
maximum shares, maximum order notional, and maximum position fraction <= 1.
Desired target fraction <= maximum position fraction. No leverage or shorts.
Exposure fraction is tested against pre-trade open NAV; post-fee NAV is disclosed
but does not redefine the admission denominator. Receivables are included in NAV
but cannot satisfy cash requirements. Existing holdings can drift over the entry
cap; no automatic rebalance is inferred.

End-of-test positions remain marked, with outstanding receivables and pending
last-close signal reported separately. No fictitious last-close fill. Run both
strategies at cost multipliers 1, 2 and 5 (all adverse bps and fees multiplied),
using identical evaluation dates. Report total return, maximum drawdown, exposure
sessions, fills, rejections, paid costs and final holdings/cash/receivables.

## Reproducibility and validation

Require explicit config, include config/data/manifest hashes, strategy identifier,
code version and all assumptions in JSON. Reject an output path that already exists;
create it atomically after successful validation and simulation. Same inputs and
code must produce byte-identical output. Error exit 2 for invalid inputs; exit 1
for unexpected runtime errors; exit 0 for a completed valid research replay,
including reported trade rejections.

Hash the captured bytes used for parsing, without rereading input files. Code
identity includes a content hash of runtime package sources, including uncommitted
changes, alongside the package version. Arithmetic uses an explicit independent
Decimal context (precision, rounding, traps and exponent bounds).

Tests must cover strict input validation, no same-bar fills, prefix invariance of
signals, warmup/equality, affordability under gaps/fees, whole-share limits,
capacity using prior volume, dividend receivables/ex-date entitlement, drawdown
latching and sell permission, final open positions, benchmark alignment,
hand-calculated P&L/costs/drawdown, CLI errors and deterministic offline replay.

This slice does not complete M1 order lifecycle, journal, recovery or broker
reconciliation. Any future transport must pass the existing M1 acceptance criteria.
Before strategy selection, use reviewed historical data, chronological development,
validation and untouched holdout periods; record all trials, test neighboring
lookbacks for sensitivity without selecting on holdout, and model taxes/cash yield,
settlement, gaps, market capacity and observed execution costs. Those conclusions
cannot come from synthetic tests.
