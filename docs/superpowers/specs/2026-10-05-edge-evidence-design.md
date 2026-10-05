# Daily edge evidence diagnostics

Date: 2026-10-05. Implements the statistical arithmetic proposed under G3 in
[the research plan](../../plans/hft-edge-research-plan.md). G0/G1 and empirical G2
remain unresolved. The user's continuing implementation and GitHub instructions
authorize this offline support tool; no market access or trading is included.

## Choice and boundary

Build a daily evidence diagnostic with explicit accounting and failure states.
Feed ingestion requires a licensed sample and fixed timestamp/schema contract;
fitting strategies requires that ingestion. Statistical diagnostics depend only
on supplied daily outcomes and can be independently tested now. This tool is not
the future sealed intraday evaluator or evidence that the six models were run.

`python3 -m quant_evidence assess --input FILE --output NEW_FILE` reads strict JSON
for one candidate and exactly 30 predeclared scheduled sessions. Required metadata:
schema_version=1, evidence_kind synthetic/declared, experiment_id, candidate_id,
source_notes, cost_notes, and scheduled_sessions. `scenarios` contains exactly
primary, double_friction, tail_delay and conservative_liquidity, each with all 30
rows in schedule order. Dates must be unique, strictly increasing ISO dates;
market-calendar completeness remains a caller declaration.
Every row has session, gross_pnl, variable_cost,
recurring_cost, outcome_bounded, constraints_satisfied and quality_notes. Costs
are nonnegative decimal strings; P&L is signed. Precision is at most 12 decimal
places and magnitude at most 1e18. Boolean flags must be actual booleans.

Bounded rows require every monetary value. Unbounded rows may use null for unknown
amounts and require an explanatory note. A missing row or omitted scenario is an
input error; an explicit unbounded row produces an inconclusive diagnostic.
Never drop an outage or quietly replace it with zero. Zero-trade days have zero
gross and variable costs but still their allocated recurring cost. The caller
supplies and substantiates that allocation; this tool cannot verify completeness.
`double_friction` means doubled slippage/impact with unchanged commission pricing;
aggregate supplied costs cannot verify how the scenario was constructed.

Net daily dollars equal gross less variable and recurring costs. No-operation
comparison is zero incremental dollars. All money arithmetic uses exact integer
units of 1e-12 dollars, including resampling sums and funding-independent metrics.
All decision comparisons use exact integers/rationals before report rounding.
Reported divisions use a fixed Decimal context. No floating-point statistics.

## Frozen diagnostic method

For primary daily net P&L, sample uniformly from overlapping noncircular blocks;
concatenate blocks to 30 observations and truncate the last block if needed.
Use 10,000 resamples, seed 20261005 with a fresh `random.Random(seed)` for each
block length. Primary length is 5 sessions; sensitivities are 1 and 10. Sort the
resampled means and linearly interpolate the fifth percentile at `(B-1)*0.05`.
Include Python implementation/version, RNG identity, seed and all method constants
in output. Repeat assessment is a diagnostic capability, not a holdout release.

Report mean/total net dollars, total gross and each cost component, worst day,
losing/zero-net days, close-to-close maximum dollar drawdown from initial zero
cumulative P&L, best day and sum excluding that best day. No annualized Sharpe,
p-value, risk-adjusted alpha or guaranteed loss estimate is produced. Bootstrap
bounds are only produced for a complete bounded primary series. All stress means
and quality/constraint failures remain visible.

Numeric assessment precedence:

1. Any explicitly failed constraint => reject (even if other outcomes unknown).
2. Any unbounded scenario outcome => inconclusive; do not extrapolate its partial series.
3. Primary mean <= 0, or any stress mean < 0 => reject.
4. Any of the three primary lower bounds <= 0 => inconclusive.
5. Otherwise => meets_pilot_numeric_criteria.

The overall report ALWAYS remains `diagnostic_only`, `promotion_allowed=false`,
`g3_complete=false`. Even positive numbers from declared input cannot establish
holdout isolation, calibrated execution, G0/G1 completion, provenance or durability.
Thirty days can yield unstable block inference; no claim of coverage calibration.

## Verification and packaging

Use hand-calculated accounting, exact percentile interpolation, deterministic
block-start/truncation fixtures, positive/negative/zero outcomes, stress failure,
outage retention, constraint precedence, tiny P&L beside large gross/costs,
malformed schema/calendar, context independence and source/archive parity tests.
Reuse existing source hashes, strict JSON parsing and atomic no-overwrite outputs.
Add one invented full-month-plus sample (30 weekdays, declared synthetic calendar)
to the standard demo. No external calls, dependencies, or model code.

## Sources reviewed 2026-10-05

[Ledoit and Wolf (2008)](https://www.ledoit.net/Robust_Sharpe_2008.pdf)
discuss dependent-return performance inference using a studentized time-series
bootstrap for Sharpe differences. This implementation is the project's simpler
percentile daily-dollar diagnostic, not their test or a replication.
[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
motivates explicit attention to strategy selection. This tool implements neither
PBO nor multiple-trial correction; trial registration and a sealed evaluation are
separate prerequisites, and repeat runs cannot award promotion.
