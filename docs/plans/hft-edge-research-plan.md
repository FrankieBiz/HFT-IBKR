# Executable order-flow edge: research and delivery plan

Updated 2026-10-05. **Authoritative research priority.** Supersedes the daily-first
priority in the October 4 pivot decision, while preserving its implemented software
and operational controls. Evidence: [research decision](../research/2026-10-05-hft-research-decision.md)
and its three linked primary-source reviews. This document specifies experiments;
intraday feature/replay modules and empirical results remain absent. The G0
conditional economics calculator is implemented; it is not a strategy backtest.
G3 daily evidence arithmetic is also implemented as a standalone diagnostic;
empirical G3 evaluation and promotion controls remain unperformed.

## Decision

Investigate one SPY long-or-cash order-flow candidate on seconds-to-minute horizons,
with abstention, affordable whole-share size and conservative aggressive execution.
Do not promise exchange-speed HFT through Gateway. Daily SPY remains a separate
unproven benchmark. Do not replace the broker, buy data, deploy infrastructure,
connect to accounts or submit orders as a consequence of this plan.

The research question is: **does information available on the intended feed predict
enough executable price movement to cover the complete cost of entering and exiting,
after realistic delay and accounting for selection uncertainty?**

The first outcome can be PASS TO FURTHER VALIDATION, REJECT or INCONCLUSIVE. There is
no PROFITABLE/READY state awarded by a backtest. No minimum trades per hour is set.

## What exists and what does not

| Component | Actual state | Treatment |
| --- | --- | --- |
| Daily research, costs, dividends and chronological evaluation | Implemented; synthetic examples | Retain; daily bars cannot supply intraday features |
| Risk/recovery reducer and journal | Implemented for narrow synthetic account semantics | Retain as reference; real fees/streams require additional design |
| Offline dashboard, data bundle, shadow-session ledger | Implemented | Reuse provenance/reproducibility patterns, not daily data schemas blindly |
| Gateway readiness diagnostic | Implemented; target API handshake not independently verified | Does not collect prices, reconcile accounts or place orders |
| G0 cost/funding sensitivity | Implemented in `quant_economics`; synthetic example | Conditional break-even and constant-price funding bound; no G0 completion |
| G3 daily evidence diagnostics | Implemented in `quant_evidence`; synthetic example | Cost/uncertainty/stress arithmetic; no holdout enforcement or G3 completion |
| Real intraday event data and license | Absent | First empirical dependency |
| Order-flow features, causal intraday labels and replay | Not implemented | Build only after data/economics contract |
| Measured edge, real fill/latency calibration | Absent | No performance claim |
| Paper/live adapters | Not implemented | Separate future work and action-specific authorization |

## G0 - economic and data feasibility before a model build

Software support: `python3 -m quant_economics assess --config FILE --output NEW_FILE`.
The [design](../superpowers/specs/2026-10-05-intraday-economics-design.md) records
equations, limitations and dated sources. Use it to falsify an unaffordable route
before fitting a model. Do not treat its grid as predicted trade frequency or
optimize size/frequency against realized returns. Freeze a single primary quantity
and cost policy using independent inputs; retain unfavorable sensitivities.

- [ ] Create `docs/research/hft-review/experiment-manifest.json` only once real inputs
  can be specified; unresolved required fields must block freezing, not default to zero.
- [ ] Record instrument identifier, currency, venue/aggregation, price/size units,
  dataset/version/date range, license/use rights and a reproducible input digest.
- [ ] Record affordable primary quantity, available settled cash, account type and settlement calendar, actual pricing
  plan, relevant per-order minimum/cap, external fees, fixed monthly costs and
  proposed loss/exposure limits. Capital and account restrictions are presently unknown. The default research ledger
  spends settled cash only and never recycles unsettled sale proceeds; fees are
  reserved separately. Different purchasing-power rules require verified account
  eligibility and a separately frozen configuration, not an implicit margin loan.
- [ ] Select either a consolidated quote-flow proxy with comparable historical/live
  semantics, or a explicitly venue-specific experiment. Never combine a venue queue
  model with undocumented SMART execution. If the required feed cannot be obtained
  within an authorized budget, reject that implementation route.
- [ ] Produce a break-even table before fitting a model. Include a no-trade benchmark
  with zero incremental strategy costs; research development spending is reported
  separately from recurring deployment costs.

**Exit:** all required fields resolved with sources, or a documented blocked/rejected
route. A code scaffold, a successful TCP connection or free delayed quotes is not
exit evidence. Costs/subscriptions and account access remain unperformed until the
specific action is authorized. Preparation and public-document review can continue.

### Evidence ledger required for G0 exit

| Unresolved decision | Evidence needed | Current state |
| --- | --- | --- |
| Capital and account constraints | Declared settled capital, cash reserve, max position/loss, account/entity and verified settlement rules | Unknown; no account access requested |
| Data budget and access path | Authorized monthly/one-time budget; historical and prospective rights; exact feed/schema/sample | No licensed intraday dataset |
| All-in cost schedule | Actual pricing/route, fee minima/caps/rounding, external fees, recurring bills and startup cost | Synthetic calculator only |
| Time semantics | Event/receipt clock definitions, timestamp granularity, sequence/gap/correction behavior; documented historical/live mapping | Not measured |
| Execution envelope | Independently justified feed/order/report delay and tails; impact, depth participation, expiry/recovery bounds | Not calibrated |
| Complete calendar and evaluation window | Full session and settlement calendars, predetermined 122-session window, held-out isolation | Not frozen |

Public fee documentation is context; it does not identify the user's actual account
or complete bill. Separate unknown inputs from a documented zero charge. A feed
sample may first be schema-checked offline if the user already has licensed files.
Access, purchases or observation through a broker remain separately authorized.

### Meaning of success

The first pilot tests net incremental dollars versus not operating the strategy.
It does not establish market outperformance. Before making that broader claim,
freeze a separate benchmark evaluation: same dates and initial capital, SPY total
return with implementable whole-share/cash treatment and its own trading costs,
plus an eligible cash alternative using sourced yield/eligibility assumptions.
Report idle cash, exposure, volatility, drawdown, turnover and paired daily return
differences; a lower-risk or lower-exposure result alone is not evidence of alpha.
Do not add this objective retroactively after seeing test results. The initial G3
pilot remains a bounded gate to further evidence, with its stated primary method.

Research priorities stay ordered: economics/data contract, causal features and
labels, hand-audited replay, sealed evaluation, prospective cohort, operational
readiness. Freeze numerical failure limits before evaluation. If a route fails,
record the rejection before considering a new horizon, instrument or access path;
register that change as a new experiment with fresh final data. Avoid endlessly
adding models or hardware in response to a failed held-out result.

## G1 - freeze the first experiment

The following are proposed defaults, to be frozen before examining returns. Changing
one after evaluation creates a new registered trial and requires fresh final data.

| Choice | Predeclared first study |
| --- | --- |
| Instrument/direction | SPY, long or cash, whole shares; no leverage/short sales |
| Candidate count | Six: two feature sets multiplied by three holding horizons |
| Decision schedule | UTC integer-second grid; replay acts only when flat, all orders terminal and settled cash eligible |
| Horizons | 1, 10 and 60 seconds after locally received terminal entry report |
| Features A | Displayed-size imbalance, spread, trailing one-second simple mid-price return |
| Features B | A plus trailing one-second normalized best-quote order-flow imbalance/proxy |
| Model | Ridge regression; objective mean squared error plus `1 * sum(beta²)`; unpenalized intercept; training-only standardization; no hyperparameter search |
| Target | Delayed exit bid minus delayed entry ask, dollars/share before explicit fees |
| Primary quantity | One affordable fixed Q from G0; do not optimize Q on validation/test |
| Threshold | Forecast exceeds per-share round-trip explicit costs plus frozen impact/slippage and uncertainty buffer |
| Position policy | One position; no pyramiding; entry IOC if supported; resume only after terminal orders, reconciled fills and sufficient settled cash |
| Session | Regular session; begin five minutes after open, stop entries five minutes before scheduled close; no overnight inventory |
| Training policy | Fit on development only; choose on validation; no final refit for this first study |

Generate training observations at every valid scheduled second independently of
policy inventory or predicted actions, with equal observation weight. Replay alone
applies flat/cash/order eligibility. At an equal receipt timestamp, process events
strictly before the decision; events stamped exactly at the boundary become visible
on the next decision. Compute simple return as `mid(t)/mid(t-1s)-1` using causal
as-of states subject to the same freshness/gap rules.

Treat feature definitions as versioned mathematics. For valid best bid/ask sizes
`B,A`, displayed imbalance is `(B-A)/(B+A)`; a zero denominator invalidates the
observation. Define mid-price as `(bid+ask)/2` only for valid, noncrossed quotes.
For successive observations `n-1,n`, the standard best-quote OFI increment is:

```text
e[n] = 1(bid[n] >= bid[n-1]) * B[n]
     - 1(bid[n] <= bid[n-1]) * B[n-1]
     - 1(ask[n] <= ask[n-1]) * A[n]
     + 1(ask[n] >= ask[n-1]) * A[n-1]
```

Sum increments received in `[t-1s,t)`, divide by the event-observation mean of
`(B+A)/2` over that same window, and require a valid predecessor and nonzero depth.
Record this normalization choice; it is not claimed to reproduce every paper's
specification. If sourced from consolidated quotes, name it **quote-flow proxy**,
not exchange queue flow. No updates in a valid continuing quote stream give zero
flow; disconnects or unknown coverage give missing data. Training-only means and
standard deviations normalize features; constant features map to zero. No clipping,
feature lookback search or alternative learner enters this initial six-model family.

### Execution and label contract

At decision time `t`, use only locally available information. Entry arrives at
`t + Lentry`. For the scientific reference label, assume an immediate entry fill
and a terminal report received at `t + Lentry + Lresponse`; exit is submitted `h`
later and arrives after `Lexit`. The label is therefore
`bid(t + Lentry + Lresponse + h + Lexit) - ask(t + Lentry)`.
This is a project-specific executable-quote diagnostic, not a replication of
next-tick classification or a guaranteed fill.

The executable policy starts its timer only when the client receives the terminal
entry report and has accounted for its executions. Use marketable IOC entry only
if the instrument/route supports the modeled semantics, verified at G0. Partial
fills create a smaller position; the unfilled remainder must be confirmed terminal
before the exit clock starts. Missing/ambiguous terminal evidence halts the policy
and retains exposure; elapsed time is never proof of cancellation. Exit filled
inventory after `h`, with its own delay and price protection. A failed/partial exit
retains exposure and invokes the frozen bounded retry/expiry and recovery policy;
its numerical limits must be frozen at G0. Never call an unresolved position flat.
Actual simulated fills and report receipt times, not the reference label, determine
policy P&L and holding duration. Measure both event-time and client-observed duration.

For historical exchange-time feeds, reconstruct market state at arrival; for
broker-receipt streams, call it an executable-quote proxy, not a known exchange fill.
Feed delay determines which earlier observations the policy can see. Freeze feed,
entry, response and exit delay, quote freshness, backlog tolerance, limit protection,
order expiration/recovery limits, impact/slippage and a numerical uncertainty buffer
from independent observations or clearly stated scenarios before strategy evaluation.
No unresolved numerical policy parameter may silently receive an implementation default.

For unmeasured delays, use four **paired** entry/exit scenarios: each leg 10, 100,
500 or 1,000 ms. Independently evaluate feed delays 0, 100 and 500 ms (12 cells);
zero is an optimistic diagnostic, not the default deployment assumption. Add these
delays to receipt availability consistently. Response delay requires its own frozen
primary and tail assumptions; cannot be inferred as half a round trip. Fit the six
models under one declared primary scenario only; freeze models, transforms and
thresholds across all stress cells. Retraining creates additional registered trials.
Without justified primary delays/costs, results remain conditional simulation
and cannot establish executable acceptance.

Replay limit protection at delayed arrival and available liquidity: it may fail or
partially fill. Cap participation using the frozen displayed-depth bound. Include
settled cash, reserved cash/fees, unsettled sale receivables and date-specific
settlement processing. Every entry passes purchasing-power eligibility. Settlement
never happens just because a sale completed. At session end, mark residual inventory
conservatively and fail the operational gate; do not erase its liquidation cost.

Do not skip losing examples because an exit quote is missing. Block decisions when
known input quality is bad; separately account for outages arising after entry,
retain exposure and mark uncertainty. A dataset that cannot bound those outcomes
cannot establish executable performance. Do not forward-fill across a feed gap,
halt, session boundary or expired freshness threshold. Report missing labels and
exclusions by time/volatility; never silently remove them from daily risk results.

### Fixed split and selection

Use a fixed calendar window of 120 scheduled sessions **plus two one-session boundary gaps**:
60 development, gap, 30 validation, gap, 30 sealed test, all chronological. Preselect
calendar dates without viewing strategy returns. Unusable training labels follow frozen quality rules and an audit trail. Evaluation
days, including outages and incomplete sessions, remain in the economic denominator;
do not replace bad days with later clean days. Unbounded outcomes make the result
inconclusive or an operational failure, rather than a favorable exclusion. Purge any label interval crossing its partition;
maximum horizon plus delay bounds governs purging, not an arbitrary row count.

Development may include expanding-window checks without changing the six-model
family. Select at most one candidate by highest validation mean daily P&L after
variable and recurring fixed costs; ties choose A before B, then the longer horizon.
If none has positive validation mean, reject the family without opening the test.
Freeze the selected model, threshold, quantity and all execution assumptions before
opening the test once. Report all six validation results and only the chosen
candidate's final-test result. Keep daily trend/buy-and-hold context separate from
intraday alpha attribution; differing exposure does not establish superior skill. Retain matched A/B validation
forecast-error and net-P&L comparisons at each horizon. If A wins, report no support
for incremental OFI; do not open additional final-test candidates to seek that support.
Allocate each actual monthly recurring bill equally over that calendar month's
scheduled regular sessions, including outage/zero-trade days. Report startup spending
and partial-month treatment separately and freeze them before validation.

## G2 - minimal research implementation

These are proposed files, not claims of completed implementation. Keep intraday data
types separate from daily OHLC and leave existing CLI behavior unchanged.

| Proposed unit | Responsibility | Required falsification tests |
| --- | --- | --- |
| `quant_microstructure/data.py` | Typed events, feed identity, clocks, ordering, gaps, sessions, hashes | Out-of-order/corrected/duplicate events; mixed feeds; integer units; unknown timestamps; session reset |
| `quant_microstructure/features.py` | Causal A/B features and train-only transforms | Future perturbations leave earlier features unchanged; price-change cases; zero depth; gap invalidation |
| `quant_microstructure/labels.py` | Delay/horizon targets and split purging | Exact boundaries; stale exit; gaps after entry; no accidental same-tick hindsight |
| `quant_microstructure/replay.py` | Settled/reserved/unsettled cash, orders, partial fills, report delays and all costs | Hand-calculated losing trade; minimum fees; same-day cash exhaustion; settlement holiday; partial/unfilled orders; no double spread; held inventory at outage |
| `quant_microstructure/evaluate.py` | Frozen manifests, six trials, selection, daily uncertainty, ledger | Refuse altered holdout inputs; no random time splits; all failed trials counted; deterministic seed/results |
| `tests/test_microstructure_*.py` | Independent numerical and failure fixtures | Expected values derived by hand, not by calling the implementation under test |

- [ ] First specify the exact input schema against the selected licensed feed.
- [ ] Write failing causal/accounting fixtures, then implement the smallest path.
- [ ] Demonstrate identical output from a tiny hand-audited event tape and rerun.
- [ ] Run the existing regression suite and new focused tests; record environment,
  dependency versions, dataset hashes, manifest and commit with the result.
- [ ] Commit each reviewable data/features/replay/evaluation increment. No dashboard,
  broker adapter or GPU model is a dependency for this gate.

Only after the schema is fixed should a detailed task-by-task coding plan pin paths,
function interfaces and dependencies. Do not add placeholder modules now and report
them as progress toward an edge. A third-party replay candidate requires a pinned
version, license review and a hand-audited equivalence check before adoption.

## G3 - economic acceptance and rejection

Standalone arithmetic support is available through `python3 -m quant_evidence
assess --input FILE --output NEW_FILE`; see the
[diagnostic contract](../superpowers/specs/2026-10-05-edge-evidence-design.md).
It accepts one declared 30-session candidate cohort with primary, double-friction,
tail-delay and liquidity stress outcomes. Costs are explicit; unknown economic
outcomes and missing sessions cannot silently disappear. The current diagnostic
does not enforce trial/holdout isolation, construct execution stresses, verify G0/G1,
or grant promotion. A numerical pass alone does not satisfy the gate below.

The primary result is a daily series of net incremental dollars at fixed capital,
including zero-trade sessions and allocated recurring overhead. Proposed initial
uncertainty method: moving-block bootstrap of daily P&L, 10,000 resamples, fixed
seed 20261005, primary block length five sessions with lengths one and ten reported
as sensitivity. Draw uniformly with replacement from overlapping noncircular blocks,
concatenate until the original number of sessions is reached, truncate excess, and
use the fifth percentile of resampled means (linear interpolation between sorted
order statistics) as the one-sided lower bound. Freeze the RNG implementation/version
in the manifest. This percentile bootstrap is a proposed pilot procedure, not a claim
to implement the studentized Sharpe test in Ledoit-Wolf. A 30-session test provides few effective blocks: intervals can be
unstable. It is a pilot, not proof of regime durability or a universal power target.

- [ ] Require positive held-out mean and a one-sided 95% lower bound above zero for
  the predeclared primary method. Display sensitivity intervals even if unfavorable;
  a lower bound at or below zero in either required sensitivity makes the pilot
  inconclusive. No interval can pass when an economic outcome is unbounded.
- [ ] Require all capital/exposure/loss constraints from G0 to hold. Historical
  drawdown is an observation, never a guarantee or hard future loss bound.
- [ ] Report costs, implementation shortfall, opportunities, abstention, settlement-blocked
  entries, fill/partial
  rates, attempts and round trips/hour, exposure, turnover, worst day, drawdown,
  concentration by day/time, and latency break-even. Include no-trade comparison.
- [ ] Apply the frozen stress envelope: separate 2x slippage/impact, observed or
  conservative tail-delay scenario and conservative liquidity participation.
  Keep commissions tied to actual pricing rather than arbitrarily multiplying them.
  Require nonnegative stress mean; otherwise reject robustness for the chosen access path.
- [ ] Report all prior trials; use selection diagnostics for exploratory results.
  The fresh single-candidate sealed test is the primary confirmatory assessment,
  conditional on complete isolation from selection. Multiple finalist/test reuse
  requires a new multiplicity procedure or new data, never a quiet second attempt.

**Reject** if realistic costs erase the edge, data cannot support executable labels,
the required size is unaffordable, or the edge exists only at unattainable delays.
**Inconclusive** if uncertainty is too wide, timestamps cannot support the claimed
horizon, or quality/latency calibration is insufficient. Investigate a logged
measurement problem without tuning returns; a changed model needs a new experiment.

## G4 - prospective observation and operational evidence

A narrowly scoped read-only observer can be designed before G3 to resolve feed
semantics, receive times and quality. Separately authorized measurements may inform
G0 without selecting models or submitting orders. Quote observation cannot measure
true order-entry latency. Unmeasured execution delays remain explicit conditional
assumptions until separately authorized evidence can resolve them. A full candidate
shadow workflow is justified only after G3; actual broker/account actions require
specific authorization.

Freeze a 30-session prospective cohort before it starts, with one assessment at its
end using G3's economic gates and the additional operational/drift checks below. Do
not repeatedly test until a result passes. If inconclusive, preregister a separate
fixed-length cohort and analysis before collecting it; do not pool or extend under
an ordinary fixed-sample interval after inspecting results. Valid sequential
inference would require a separately specified procedure. Compare feed distributions,
signal decay, quoted execution proxies, stale-data rates and timing tails against
replay. Do not interpret observed quotes as real fills. Feature drift, missing
entitlements or delay beyond the validated envelope block promotion.

Separately finish real broker reconciliation, commission accounting, settlement,
restart, uncertain submission, cancel/fill races, independent loss limits and operator
kill/exit procedures. The current synthetic global sequence is not an IBKR snapshot
guarantee. Authorized paper order drills validate integration and recovery; paper
profit does not establish queue fills or market impact. Live readiness is a distinct
decision with actual limits, account/regulatory review and explicit authorization.

## Definition of progress

Track unresolved assumptions, frozen experiments, rejected hypotheses and calibrated
cost/delay envelopes. Current status is **G0 unresolved, G1 design drafted but not frozen, G2-G4 not run**.
This planning revision and literature review are complete artifacts; empirical work
remains open. The next build is the smallest causal event-data/replay experiment
supported by G0, not a new AI trader or another claim that the system is finished.
The economics calculator now supplies reproducible conditional tables and funding
bounds. It does not resolve the evidence ledger or authorize G2 construction from
an invented feed schema.
