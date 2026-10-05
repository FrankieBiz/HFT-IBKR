# Pre-registration: SPY daily trend on real data (spy-daily-v1)

Registered 2026-10-05 and committed **before any real SPY data was retrieved** for this
study. [`protocol.json`](protocol.json) and [`config.json`](config.json) are part of
this registration. Changing either after retrieval makes a new study, which requires
new holdout data. The registry enforces that per session.

## Question

On real SPY history, does the repository's causal dividend-aware SMA trend rule
(long above the SMA, cash at or below it) improve on buy-and-hold for a
cash account trading at most once per session at the next open? Improvement means
lower drawdown, and ideally better return. The rule is the hypothesis from the
[ETF trend design](../../docs/superpowers/specs/2026-10-04-etf-trend-research-design.md);
the 100/150/200 candidates were fixed on synthetic data on 2026-10-04.

Why this study, and not intraday: see the
[blueprint review](../../docs/research/2026-10-05-architecture-blueprint-review.md#account-facts-close-the-intraday-route-2026-10-05).

## Data (zero cost)

- **Source:** Alpaca free Basic plan through `python3 -m quant_data fetch-alpaca`:
  - SIP daily bars with `adjustment=raw`, labeled at 00:00 New York time;
  - cash dividends from `/v1/corporate-actions`;
  - sessions from the Alpaca trading calendar.
- **Range:** request 2016-01-01 to 2026-10-02, the last completed session before
  registration.
- **Fail-closed checks before use:**
  - bar sessions equal calendar sessions exactly;
  - every quarter-end third Friday in range has a dividend ex-date in that month;
  - only USD domestic dividends, with no duplicate ex-dates;
  - on ten evenly spaced sessions, the daily open, high and low lie within 0.1% of the
    regular-session minute bars, with at most two exceptions.
- **Storage:** inputs and bundle stay under the gitignored `.research-output/`.
  Alpaca's terms allow personal non-commercial use and forbid redistribution.

## Protocol

| Field | Value |
| --- | --- |
| Warmup | 2016 sessions (at least 200 before development) |
| Development | 2017-01-03 to 2020-12-31 |
| Embargo | 5 sessions between intervals |
| Validation | 2021-01-11 to 2023-06-30 |
| Holdout (released once) | 2023-07-11 to 2026-10-02 |
| Candidates | SMA lookback 100, 150, 200 |
| Selection | Highest validation total return at 2x costs; ties choose the smaller lookback |

Each interval resets to $50,000 cash and starts flat. The 0.95/0.98 exposure targets,
20% latched buy halt and 0.1% participation cap apply to the trend rule and to
buy-and-hold alike.

**Costs (IBKR Lite):**

- $0 commission.
- Sell fee 0.3 bp. This covers the SEC Section 31 fee ($20.60 per million from
  2026-04-04, with the historical maximum about $27.80) plus FINRA TAF.
- Adverse fill 2 bp per side: half-spread 0.5, slippage 1, impact 0.5.

Results are reported at 1x, 2x and 5x. SPY's typical spread is far below this; the
margin covers opening-print and wholesaler execution uncertainty.

## Pre-registered decision rule

Applied once to the holdout at **2x costs**:

| Outcome | Condition | Consequence |
| --- | --- | --- |
| Dominates | Trend total return ≥ buy-and-hold **and** maximum drawdown ≤ buy-and-hold | Proceed to a prospective manual shadow on Lite (one decision per session) |
| Risk-reducing | Trend return < buy-and-hold **but** maximum drawdown lower | Shadow only as an explicit risk-control overlay, disclosing the return given up |
| Dominated | Trend maximum drawdown ≥ buy-and-hold | Reject the rule for this period; do not tune lookbacks on the holdout |

A negative holdout total return for the trend rule at 2x costs blocks every
"proceed" outcome. The 1x and 5x columns are sensitivities only and cannot rescue a
result. Validation results and all three candidates are reported regardless of
outcome.

## Known limitations, stated in advance

- The whole period is public history known to the researchers, and the 200-day rule
  is widely published. This is a historical replay, not a prospective test; only the
  shadow period is genuinely out of sample.
- One asset and one price path. A trend rule trades a handful of times a year, so a
  three-year holdout contains few independent decisions. No statistical significance
  is claimed or computed.
- Cash interest on idle balances, taxes and settlement timing are excluded. Opening
  fills are modeled from the daily open plus costs, not observed fills.

## Commands

```sh
D=.research-output/spy-daily-v1 && mkdir -p "$D"
# 1. You, with free Alpaca paper keys in APCA_API_KEY_ID / APCA_API_SECRET_KEY:
python3 -m quant_data fetch-alpaca --start 2016-01-01 --end 2026-10-02 --output-dir "$D/alpaca"
# 2. Build and inspect the bundle (offline from here on):
python3 -m quant_data prepare --prices "$D/alpaca/prices.csv" --distributions "$D/alpaca/distributions.csv" \
  --calendar "$D/alpaca/calendar.csv" --metadata "$D/alpaca/metadata.json" --output "$D/spy.qdata"
python3 -m quant_data inspect --bundle "$D/spy.qdata" --output "$D/inspect.json"
# 3. Validation and frozen selection, then the single holdout release:
S=studies/spy-daily-v1
python3 -m quant_research evaluate --bundle "$D/spy.qdata" --config $S/config.json --protocol $S/protocol.json \
  --registry "$D/experiments.sqlite" --selection "$D/selection.json" --output "$D/validation.json" --run-id validation-1
python3 -m quant_research holdout --bundle "$D/spy.qdata" --config $S/config.json --protocol $S/protocol.json \
  --registry "$D/experiments.sqlite" --selection "$D/selection.json" --output "$D/holdout.json" --run-id holdout-1
```
