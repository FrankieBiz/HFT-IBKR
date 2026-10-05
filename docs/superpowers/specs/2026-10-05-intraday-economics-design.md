# Intraday economic feasibility calculator

Date: 2026-10-05. Scope: the G0 break-even table in the authoritative
[research plan](../../plans/hft-edge-research-plan.md). The user authorized continued
planning and implementation. Account access, data purchases and orders are excluded.

## Decision

Build a usable offline economics tool before selecting a feed or fitting a model.
More strategy code would depend on an unresolved data contract. A document-only
table would be difficult to reproduce across quantities, costs and capital budgets.
The calculator accepts explicit assumptions and produces conditional sensitivity
results; it cannot freeze G0, select a strategy or establish an edge.

## Contract

`python3 -m quant_economics assess --config FILE --output NEW_FILE` and portable
`economics assess` accept strict JSON. Every field is required, including zeros.
Reject unknown keys, duplicate keys, nonfinite/negative amounts, booleans masquerading
as integers, duplicate grid entries and excessive grid sizes. Monetary inputs are
decimal strings; use exact rational arithmetic for all calculations and funding
decisions. Serialize amounts under an isolated 80-digit Decimal context; only
nonterminating report fractions are rounded. Reuse atomic publication.
Quantity, reference mid and movement increment must be positive. Every scenario
must have a positive zero-movement exit price. Zero trips have null break-even
and net dollars equal to negative daily overhead.

Inputs: declared source notes and synthetic/declared evidence type; USD/SPY;
reference mid; settled cash; protected cash buffer; maximum entry notional;
quantities; completed round trips per session; one month's explicitly declared
scheduled session dates; monthly recurring and separate startup costs; analysis
movement increment; side-specific commission rate/minimum/notional cap and external
per-order/per-share/notional charges; named spread/slippage/impact scenarios.
Source notes are declarations, never verified credentials or verified market data.

Each fee is `min(max(Q * rate, minimum), Q * fill_price * cap_fraction)` plus
external order, share and notional charges. External charges are outside the
commission cap. Require cap plus external notional fraction below one. Charges
are continuous estimates, without invoice rounding, rebates or volume-tier changes.
One fully filled order per side is an explicit limitation; partial/replaced orders
can increase costs. Account-specific fee schedules need reconciliation later.

Entry price is mid plus half entry spread plus entry slippage and impact. Exit
price is mid plus movement minus half exit spread minus exit slippage and impact.
Spread is therefore counted exactly once per crossed side. Exit fees must change
with exit price, including the cap crossover. Solve the two linear fee regimes for
the exit price covering entry outlay, exit fees and daily overhead divided by trips.
Round the required nonnegative mid movement upward to the declared analysis
increment; this is not an assertion about the exchange tick size. Show fees and
net dollars at that movement, at zero movement, and variable-only break-even.

Allocate the full declared monthly bill over every supplied scheduled session.
Reject multi-month schedules; do not prorate partial months silently. Calendar
completeness remains a declaration. Zero-trade strategy days still lose their fixed
cost; the separate do-not-operate benchmark is zero incremental cost. Startup
spending is reported separately. No predicted return or trade count is inferred.

Available cash is settled cash less protected buffer and one day's fixed overhead.
Reserve any excess of zero-movement exit fees over sale proceeds per trip. The
floor of available cash divided by entry outlay plus this reserve is a
**constant-price funding bound**, not a settlement replay. Sale proceeds never replenish it. Above-bound
trip counts and quantities above the entry exposure limit are infeasible; still
show their diagnostic arithmetic with explicit reasons. Zero trades needs no entry
capital. Actual price paths, unsettled cash, outages and partial fills need G2 replay.

## Evidence and next gate

Reports carry exact input hash, code hashes, assumptions and all grid rows in input
order. Status always `conditional_analysis`; `g0_complete` is always false. Local
declared inputs cannot prove licensing, fee completeness, latency or data fitness.
No experiment manifest or placeholder intraday feed adapter is created.

Tests derive numerical answers by hand: per-order minimum, cap below minimum,
external fees outside cap, price-dependent sell fee, spread accounting, zero-trade
overhead, unaffordable quantity, cash-boundary equality, no proceeds reuse,
nonfinite input, context independence and portable archive parity. Full regression
and existing demo must remain green.
Include exact cap crossover, zero cap, non-divisible increments and exit-fee
deficits. At positive computed break-even, require negative net one increment
lower. Spec review findings were incorporated before implementation.

## Sources checked 2026-10-05

[IBKR US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
lists per-share rates, per-order minima, notional caps and separate third-party
charges. Its published US Pro first-tier rates include $0.0035/share with $0.35
minimum (tiered) and $0.005/share with $1 minimum (fixed), each with a 1% cap.
These facts motivate configurable side-specific costs; the fixture is invented
and does not reproduce a complete IBKR bill or identify the user's pricing plan.

[IBKR cash account definition](https://www.interactivebrokers.com/campus/glossary-terms/cash-account/)
requires cash covering transaction cost and commissions.
[SEC T+1 FAQ](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq)
describes the shortened standard settlement cycle. The calculator deliberately
does no multi-day settlement calculation; no same-day sale proceeds are recycled.
