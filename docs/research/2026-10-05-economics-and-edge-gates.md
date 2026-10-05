# Economics implementation and next edge gates

Date: 2026-10-05. Continuation of the authoritative HFT research plan.

## Delivered

`quant_economics` makes G0 cost arithmetic reproducible before model fitting.
Inputs declare quantities, completed trips/day, entry and exit friction, side-specific
fee schedules, cash/exposure bounds and a full month's recurring cost allocation.
Outputs include variable-only and overhead-inclusive break-even movement, loss at
zero movement, and explicit funding violations. Hashes bind reports to exact input
bytes and implementation. Source and portable archive produce identical reports.

The analytic fee model recomputes capped sell commission and notional charges at
the required exit price. It counts each crossed half-spread once and keeps startup
spending separate. Zero-trade operating days still incur overhead; not operating
has zero incremental costs. A funding bound reserves purchases and any modeled
exit-fee deficit without recycling sale proceeds. It cannot replace a price-path,
partial-fill or multi-day settlement simulation.

The fixture is invented. A favorable row is an arithmetic requirement under inputs,
not a forecast that the market will supply that movement. No account, subscription,
market data collection, GPU inference or order submission was performed.

## Research choices

First resolve real capital, risk limits, data budget, fee schedule and a licensed
feed sample. Then freeze data semantics and the experiment before implementing
features/replay. The calculator deliberately cannot mark G0 complete. Choosing a
smaller spread, more daily trades or a larger quantity merely to improve a table
is an assumption change requiring evidence, not an improvement in expected returns.

Keep six predeclared candidate models and one final test. A failed candidate is a
recorded result. New instruments, feature families, timing assumptions and repeated
test exposure count as new experiments; they must not be hidden by a successful
final report. Planned turnover must satisfy cash eligibility on actual price paths.

The current pilot's net-dollar objective is narrower than beating SPY. A market
outperformance study needs a separately frozen benchmark contract covering same
capital/dates, total return, idle cash, executable costs and risk/exposure differences.
No pilot return or software check can substitute for that comparison.

## Primary-source context

Checked 2026-10-05. The
[IBKR fee schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
motivates separate commission minima/caps and external charges. The
[SEC settlement FAQ](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq)
motivates keeping sale settlement distinct from executions. Account-specific
applicability and calibrated costs remain unresolved; implementation equations and
limitations are in the [design](../superpowers/specs/2026-10-05-intraday-economics-design.md).

[Novy-Marx and Velikov, A Taxonomy of Anomalies and their Trading Costs](https://www.nber.org/papers/w20721)
studies how transaction costs and mitigation change anomaly returns. It supports
testing costs as part of research; its historical anomaly results are not evidence
for this SPY intraday candidate. The restriction on repeated selection follows the
research plan's existing trial and holdout controls.

## Verification

`make check build demo` completed on Python 3.14.0 / macOS, 2026-10-05:

- 199 tests passed, including 21 focused economics/CLI tests and the integrated demo.
- Compile checks and `git diff --check` passed; portable archive built successfully.
- Full synthetic demo passed all 14 control scenarios, holdout recovery/reuse checks,
  shadow decisions and the new 32-row conditional economics report.
- Independent adversarial review exposed two accepted-input precision failures in
  the initial Decimal implementation. Regression tests reproduced both; exact
  rational arithmetic fixed them. The reviewer then reported 500 deterministic
  accounting probes passed and no remaining material findings in this scope.

Local report: `.research-output/demo-httjm8i1/economics.json`. The associated
`summary.json` records workflow outcomes; reports contain input and source hashes.
Build SHA-256: `f6fbf1eb9ed158205b0227c6620ab94ccd770e242aa96a32369b289d3656c75e`.
Generated artifacts remain excluded from version control. These are software and
synthetic-accounting checks. Empirical strategy validation remains absent.
