# SPY trend overlay research protocol (spy-trend-v2)

Defined 2026-10-06 after reviewing the existing software and publicly known research.
This is a revised historical research protocol, not a claim of untouched history
or a completed pre-registration before all researchers knew the data.

## Hypothesis and risk policy

Keep the causal dividend-aware SPY SMA rule, whole shares, long/cash and next-open
execution. Candidates are 100, 150 and 200 sessions. Change only research allocation
and entry-halt settings from v1: target 25% of NAV, maximum entry exposure 30%, and
10% latched peak-to-NAV drawdown halt on new buys. These are illustrative defaults
for a bounded sleeve. There is no stop-based per-trade loss budget, automatic
liquidation, guaranteed loss ceiling or daily/intraday loss monitor. Holdings may
appreciate past the entry cap. The smaller cash allocation is not a claim of alpha.

The original `../spy-daily-v1/{config,protocol}.json` and registration remain intact.
V1 results cannot qualify v2. Never edit either study's JSON after evaluation; a
change requires a new recorded protocol and fresh final evidence where consumed.

## Fixed historical workflow

Data: raw SPY OHLC/dividends/calendar, 2016-01-01 through 2026-10-02. The same strict
intake, timestamp checks and dividend caveats documented in the v1 registration
apply, including derived/supplemented historical dividends. Independently review
provider licensing and completeness before treating the source as economic evidence.

2016 warms features; development is 2017-01-03–2020-12-31; validation is
2021-01-11–2023-06-30; final holdout is 2023-07-11–2026-10-02, with five-session
embargoes. Each interval starts flat at $50,000. Highest validation return at 2x
costs selects a lookback; ties choose the smaller one. These inherited dates are
historical, not new prospective observations.

Storage: `.research-output/spy-trend-v2/`. The study script shares the original
`.research-output/spy-daily-v1/experiments.sqlite` registry and uses unique v2 run IDs.
If those holdout sessions were released by v1, the v2 holdout is deliberately
refused. **Keep the registry.** A separately frozen protocol on fresh future dates
is required; no rename, reset, alternate registry or relabeling makes old data fresh.
Old registries predating session claims require review, not replacement to evade
consumption. Unused dates in a local registry still do not erase public-history bias.

## Costs, comparisons and progression

Inherited research cost assumptions: $0 commission, sell fee 0.3 bp, adverse fills
2 bp per side (half-spread 0.5, slippage 1, impact 0.5). These are scenarios, not a
verified 2026 account quote or observed fill calibration. Report 1x, 2x and 5x costs.
Taxes, cash yield, settlement delays and queue/auction behavior are excluded.

The trend rule and buy-and-hold use the same sleeve allocation/risk/cost settings
and dates. Cash earns zero. Comparison with an almost fully invested SPY account
would confound signal behavior with cash allocation and is not this matched test.

At 2x costs: DOMINATES means lower drawdown and at least benchmark return;
RISK_REDUCING means lower drawdown but lower return; other outcomes reject. Negative
trend return blocks progression. Equal drawdown is conservatively rejected.
The verdict tool defines these boundaries exactly. A permitted result supports only
prospective manual shadow observation, never automatic paper/live orders.

Readiness also requires exact study/source identities and authenticated historical
validation, frozen selection and holdout records. It allows only the frozen selected
lookback in a derived planning config. Code or policy changes invalidate evidence;
revalidation cannot reopen consumed final sessions. Failed or missing evidence
halts daily operator scripts before they access keys or services.

## Robustness diagnostics and prospective evidence

The study workflow also records expanding-window walk-forward and paired moving-
block return resampling on development/validation only. The report freezes its
folds, embargo, seed, sample count and block size. These diagnostics cannot tune the
final choice, rescue a rejected final result or establish probabilities of future
profit. A single asset/path and a small number of decisions limit inference.

Only later observations are prospective. Maintain the shadow book explicitly,
retain decisions/heartbeats/errors and document modeled actions and actual quote
friction separately. Broker execution, realistic fill calibration, independent
monitor scheduling, taxes/cash-yield sensitivity, external cash-flow accounting
and portfolio diversification are separate future work.

## Operator commands

After separately configuring authorized data access:

```sh
./scripts/run_study.sh
```

This explicit command may download study inputs; the daily runner never starts it
implicitly. An approved study is necessary for:

```sh
./scripts/run_daily.sh --check
./scripts/run_daily.sh
```

No study, download, external notification or account request was run as part of the
October 6 development changes. Local tests and demonstrations use synthetic data.
