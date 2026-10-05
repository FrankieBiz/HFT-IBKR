# Realistic odds: will this system work, make money, or generate alpha?

Written 2026-10-05, **before** the pre-registered `spy-daily-v1` study has run. The
odds below are judgment, anchored on 150 years of historical base rates, a daily-data
check and published research. They are not a promise, and not financial advice.
To keep the sealed test clean, no analysis here used the study's holdout period
(2023-07-11 onward).

## The short answer

- **Will the software work?** Very likely. 206 automated tests pass, along with
  Linux CI and end-to-end runs. The main open risks are practical: whether Alpaca's
  free plan serves the historical data, the PC sleeping, and network or clock problems.
- **Would following it make money?** Over several years, probably yes. But the reason
  is that it holds SPY about 75–80% of the time and stocks have tended to rise, not
  skill. Over any single year it loses money roughly a quarter of the time.
- **Would it beat simply buying and holding SPY?** **Probably not.** Historically it
  beat buy-and-hold in only about 1 in 4 three-year periods, and about 1 in 6 since
  2010. The **daily** version this system uses flips position far more often than
  the textbook monthly version. Over 2017–2023 it returned about **5% a year against
  11%** for simply holding.
- **Does it generate alpha?** Not in any way you could rely on or prove. Its real,
  historical strength is **smaller crashes**: it steps aside during long bear
  markets. That is risk reduction, paid for with lower returns most of the time.
  Proving genuine alpha within a few years is statistically almost impossible.

## The odds

These are rough estimates for following the rule as configured: daily 200-day
average, all-in or all-out, cash earning 0%, IBKR Lite costs, before taxes.

| Question | Horizon | Estimated odds | Main basis |
| --- | --- | --- | --- |
| The daily software runs and records a decision, once set up | any trading day | ~90% | Tests and CI; risks are PC sleep, network and clock |
| Alpaca's free plan serves the history the study needs | once | ~85% | Docs allow free history older than 15 minutes, but this is not confirmed for daily bars |
| Following it makes money (positive return) | 1 year | ~70% | Historical 1-year windows: 71–83% |
| | 3 years | ~85% | Historical 3-year windows: 92–100%; today's high valuations argue for caution |
| It beats buy-and-hold on total return | 1 year | ~15–20% | 11–26% historically, lower on daily data |
| | 3 years | ~15–25% | 16–42% historically (16% since 2010), lower on daily data |
| | 10 years | ~20–35% | 0–61% depending on era; it needs a deep bear market to win |
| It has a smaller worst drop than buy-and-hold | 3 years | ~55–70% | 53–74% historically; daily 2017–23: 20.5% vs 33.9% |
| Better risk-adjusted return (Sharpe, 0% cash) | 3 years | ~35–50% | 40–55% historically, before daily whipsaw costs |
| Positive beta-adjusted alpha (small, noisy) | 3 years | ~45–60% | 58–73% on monthly data, reduced for daily whipsaws |
| Statistically provable alpha | 3–5 years | <5% | A handful of trades and one price path cannot separate skill from luck |
| Study verdict **DOMINATES** (better return *and* smaller drawdown) | holdout | ~10–20% | Rarely happens in bull-market periods |
| Study verdict **RISK_REDUCING** (smaller drawdown, lower return) | holdout | ~45–60% | This rule's typical profile |
| Study verdict **DOMINATED** (no drawdown benefit) | holdout | ~25–35% | Whipsaws or a fast V-shaped dip can erase the benefit |

**Bottom line in dollars:** with $50,000, if your goal is the most money, simply
holding SPY has historically beaten this rule most of the time. The rule is for
investors who will accept less return in exchange for avoiding much of a 2008-style
collapse.

## Evidence

### 1. 150 years of monthly data (upper bound for the rule)

The test applies a 10-month moving average, the standard monthly version of the
200-day rule, to a dividend-inclusive S&P 500 index.

- **Data:** Shiller's monthly data, 1881–2026.
- **Assumptions:** cash earns 0%; costs are 5 bp per side per switch.
- **Windows:** every 1-, 3-, 5- and 10-year window, starting each month.
- **Script:** [`research/odds/base_rates.py`](../../research/odds/base_rates.py).

| Period | Rule CAGR | Buy-and-hold CAGR | Rule max drawdown | Buy-and-hold max drawdown | Time invested |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1881–2026 | 9.8% | 9.4% | 47.8% | 81.8% | 71% |
| 1950–2026 | 11.5% | 11.7% | 19.0% | 49.0% | 76% |
| 1990–2026 | 10.8% | 10.9% | 19.0% | 49.0% | 79% |
| 2010–2026 | 11.9% | **14.2%** | 19.0% | 19.3% | 85% |

The next table shows how often the rule did better, across all rolling windows. Each
cell is beats buy-and-hold on return / smaller drawdown / positive beta-adjusted alpha.

| Windows starting | 1 year | 3 years | 5 years | 10 years |
| --- | --- | --- | --- | --- |
| 1881+ | 26% / 44% / 31% | 42% / 74% / 71% | 46% / 87% / 85% | 50% / 92% / 97% |
| 1950+ | 22% / 39% / 32% | 32% / 69% / 73% | 35% / 85% / 88% | 45% / 95% / 97% |
| 1990+ | 18% / 33% / 27% | 28% / 53% / 58% | 38% / 67% / 77% | 61% / 88% / 92% |
| 2010+ | 11% / 33% / 34% | 16% / 55% / 64% | 13% / 58% / 68% | **0%** / 62% / 70% |

Over the full history, positive returns occurred in 71% of 1-year windows and 92% of
3-year windows (buy-and-hold: 73% and 85%).

**Why this is an upper bound:** Shiller's monthly "price" is the *average* of each
month's daily closes. Averaging smooths returns and hides fast crashes, which
flatters trend rules. For example, the 2020 crash barely appears in monthly averages.

### 2. Daily data, the rule this system actually uses (2017-07 to 2023-06)

- **Data:** FRED daily S&P 500 closes. These are price-only, so dividends are excluded
  on both sides.
- **Rule:** the 200-day average, decided at the close and held from the next close.
  The live system acts at the next open.
- **Window:** ends before the study's holdout begins.
- **Script:** [`research/odds/daily_check.py`](../../research/odds/daily_check.py).

| | CAGR | Max drawdown | Volatility |
| --- | ---: | ---: | ---: |
| Buy-and-hold | 10.7% | 33.9% | 20.5% |
| **Daily 200-day rule** | **5.1%** | **20.5%** | 12.3% |
| Monthly 10-month rule, same years (for comparison) | 8.5% | 19.1% | — |

The daily rule switched **47 times in six years** (7.8 per year), mostly in clusters:

- 2018-10 to 2018-12: 9 switches;
- 2020-02 to 2020-06: 10 switches;
- 2022-01 to 2022-04: 11 switches;
- 2023-01 to 2023-03: 7 switches.

Each time the price hovered near its average, the rule sold low and bought back
higher. This matches published counts: since 1997 the S&P 500 crossed its 200-day
average about 150 times, against only 11 real 10%+ corrections
([Alpha Architect](https://alphaarchitect.com/the-moving-average-research-king-valeriy-zakamulin/)).
**The textbook monthly results overstate what this daily system is likely to do.**

### 3. Published research

- **Faber** ([2007/2013](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf)),
  monthly 10-month rule, S&P 500 1901–2012:
  - CAGR 10.18% against 9.32%, Sharpe 0.55 against 0.32, max drawdown −50% against −83%.
  - After publication (2006–2012) it still won, but almost entirely by sidestepping 2008.
  - It lost to buy-and-hold in the 1990s bull market.
  - A cited tax study cuts a 10.62% pre-tax return to about 6.3% at this kind of turnover.
- **Zakamulin**:
  - The [robust-MA paper](https://smallake.kr/wp-content/uploads/2016/04/SSRN-id2612307.pdf)
    finds a Sharpe of about 0.49–0.53 for MA rules against 0.38 for buy-and-hold over
    1860–2014. The edge comes from a few sub-periods.
  - The [2014 study](https://link.springer.com/article/10.1057%2Fjam.2014.25) reports
    the real-life edge to be only marginal, and statistically indistinguishable from
    buy-and-hold once look-ahead bias is removed. That is from its abstract and
    secondary reports; the full text was not accessed.
- **Siegel** used a **1% band** around the 200-day average, precisely to reduce
  whipsaws (as reported by Faber). This system has no band.
- **Diversified trend following**
  ([Moskowitz–Ooi–Pedersen](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf),
  [Hurst–Ooi–Pedersen](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing))
  reaches a Sharpe near 1.0 by spreading across dozens of markets. Single markets sit
  around 0.3–0.5. This system trades one market, so it borrows the idea without the
  diversification behind most of that evidence.

## Where it is strong

**The system**

- **Honest evidence:** the rules were pre-registered in Git before any data was
  fetched, the holdout can be released once, signals are causal and tested, and data
  checks stop on problems instead of guessing. A disappointing result will be
  reported as disappointing.
- **Safe by construction:** it has no order authority and cannot touch your account,
  so a bug cannot lose money directly.
- **$0 to run:** free data, $0 commissions on Lite, unattended operation and phone
  notifications.
- **Tested:** 206 automated tests and Linux CI, plus a security review of the code
  that handles your API keys.

**The strategy**

- Simple, transparent and widely studied; the code has one tunable number.
- Low trading needs. A trade is one manual order on Lite, and a cash account is never
  a constraint.
- A real historical record of stepping aside in long bear markets: 1929–32, 1973–74,
  2000–02 and 2008–09.

## Where it is weak

- **No unique edge.** It is one of the best-known public rules, applied to one asset.
  Nothing here is proprietary information or skill.
- **Whipsaws.** The daily rule has no band or confirmation. In choppy markets it
  repeatedly sells low and buys back higher: 47 switches in 2017–2023.
- **Bull markets cost it return.** It lags whenever stocks grind higher, as they mostly
  have since 2009.
- **V-shaped crashes hurt.** It decides at the close and acts at the next open, so it
  can exit near a bottom and re-enter higher (2020).
- **Cash earns 0% in the model.** IBKR does pay some interest on cash. Ignoring it
  slightly understates the rule, by up to about 1% a year at today's rates while in cash.
- **Taxes.** Frequent switches realize short-term gains in a taxable account. That
  drag can exceed any edge. If used for real, an IRA is far better suited.
- **Manual execution.** Lite has no API, so every signal needs you to place the order.
  Missed or late trades, and the temptation to override, are real risks.
- **Weak proof.** The study replays known history over a few dozen decisions. It can
  say "consistent with" or "not consistent with", never "proven".
- **Operational dependencies:** Alpaca's free plan, the PC staying awake, the WSL
  clock, and a single-venue IEX quote for pricing.
- **The name.** This is not high-frequency trading. That route was closed for a Lite
  cash account; see the [blueprint review](2026-10-05-architecture-blueprint-review.md).

## What would actually improve the odds

Each change below is a **new, separately pre-registered study**. None can be tuned on
the current holdout without invalidating it.

1. **Cut whipsaws:** check the signal only at month-end, or require a band (for
   example 1–3% beyond the average, as Siegel did) or several days of confirmation.
   Effect: the largest, as the daily-versus-monthly comparison shows.
2. **Earn interest while out:** hold a T-bill ETF instead of 0% cash.
3. **Diversify:** apply the same rule across stocks, bonds, real estate, commodities
   and international markets, Faber-style. That is where trend-following evidence is
   strongest.
4. **Use a tax-advantaged account** if you trade it for real.
5. **Shadow before money:** run the daily shadow for 6–12 months and compare its
   decisions with what you could actually have executed.

## Caveats

- The odds are judgment calls from history, which is a single path and may not repeat.
- Today's market (valuations, rates, concentration) differs from most of the sample.
- The monthly data flatters the rule.
- The daily check is price-only and fills at the next close, not the next open.
- The pre-registered study will give a cleaner, account-specific answer for 2023–2026.
- Data sources: Shiller-derived monthly S&P 500 via
  [datahub.io core/s-and-p-500](https://datahub.io/core/s-and-p-500) (ODC-PDDL), and
  [FRED SP500](https://fred.stlouisfed.org/series/SP500) daily closes. Both are
  downloaded by the scripts and not committed here.
