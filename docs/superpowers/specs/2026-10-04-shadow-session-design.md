# Integrated daily shadow session

## Scope

Build `quant_session`, a deterministic **offline_shadow** decision runner. It joins
the existing daily signal and independent cost-aware admission to explicit local
schedule, quote and portfolio snapshots and a SQLite decision ledger. No SDK,
socket, orders, cancellation, credentials or wall-clock scheduler. The output is a
non-binding proposal, never order authority. SIM/SPY/USD only; historical source
declarations remain unreviewed and all strategy validation remains unproven.

Do not connect the synthetic `quant_control` reducer to IBKR. Reuse pure research
strategy/risk functions while retaining that reducer as the fault-scenario oracle.

## Inputs and time contract

CLI: `python3 -m quant_session plan --bundle PATH --config PATH --schedule PATH
--snapshot PATH --ledger PATH --output NEW_JSON`. Read JSON once with duplicate-key
rejection and a 1 MiB limit. Use existing bundle loader and strict research config.

Schedule schema: `schema_version:1`, `source` nonempty bounded text,
`sessions:[{session,open_at,close_at}]`. Require unique ascending ISO dates and UTC
aware timestamps, open < close, no overlap, and both timestamps' America/New_York
local date equals session. A declared schedule can model early closes and DST;
source accuracy/holidays are not independently verified. Synthetic calendars must
not be described as exchange-certified schedules.

Snapshot schema: `schema_version:1`, `mode:offline_shadow`, `account:SIM`,
`symbol:SPY`, `currency:USD`, `execution_session`, `now`,
`quote:{bid,ask,as_of,data_type}`, `portfolio:{cash,settled_cash,nav,shares,
peak_nav,as_of,reconciled,pending_orders,uncertain_orders,halted}`,
`policy:{max_quote_age_seconds,max_account_age_seconds}`.
Decimals are bounded nonnegative strings; bid/ask/nav positive, bid<=ask,
settled_cash<=cash; shares and counts bounded nonnegative integers; booleans strict.
Require positive peak_nav >= declared nav. Use effective_nav = min(declared nav,
cash + shares*bid) for target/exposure admission and drawdown marking, and disclose
both marks. Block zero effective NAV and drawdown >= config.max_drawdown. This
conservative synthetic mark excludes unpaid dividends/other assets; no real broker
balance-sheet equivalence is implied. Drawdown/halts block proposals without forced
liquidation; a live risk-reducing exit policy remains a separate design.
Require quote `data_type:synthetic` for this offline version; unsupported/live modes
are input errors. The runner does not infer permissions or real account validity.
Policy ages are explicit bounded positive integer seconds, not production defaults.

Execution session must exist in schedule. Select the immediately preceding schedule
session as the signal session; require its close <= now and exact supplied price
coverage through that session. Later dataset bars are excluded from calculations.
Concretely, causal dataset dates must equal declared schedule dates from the first
supplied causal bar through the signal session, including that last bar.
Earlier schedule history need not be supplied; short complete history is WARMUP.
The full bundle may contain later observations for retrospective rehearsal, but no
next-open bar or future close is used in the proposal. Missing schedule/data or
incomplete signal close blocks; insufficient causal history produces WARMUP.

Require execution open <= now < execution close, quote as_of >= execution open,
quote and portfolio timestamps <= now, and ages <= policy maxima. Missing coherence,
stale data, pending/uncertain orders, or halted state block proposals fail closed.
These are explicit synthetic declarations, not real broker reconciliation evidence.

## Decisions and cost conventions

LONG+zero shares proposes BUY; CASH+shares proposes SELL; otherwise HOLD. WARMUP,
invalid session/freshness or unsafe portfolio produces BLOCKED with reasons.
Use current bid for sell reference and ask for buy reference. Zero the research
half-spread component when applying the existing estimator to these bid/ask prices
so spread is not charged twice. Retain modeled slippage/impact/fees at 1x only;
their values are illustrative. Size buys from effective NAV/target fraction and ask,
cap using settled_cash, shares, notional/exposure/capacity and estimated fees. Use
only previous completed-session volume. Independently admit the final buy/sell.
If reduced to zero or exit cannot pass limits, BLOCKED with the concrete reason.
Halt is not a liquidation guarantee. No partial-exit policy is introduced here.

Reports include mode, synthetic snapshot/quote scope, data_kind, unproven strategy,
signal/execution sessions, signal, HOLD/BLOCKED/PROPOSED status, proposal side and
quantity or null, reference and estimated prices/costs, blockers, consumed causal
bar count, source hashes and explicit limitations. Add a stable SHA256 decision ID
over canonical decision inputs/report (excluding its own ID). Changes to future
data may change full-source hash/ID but must never change signal/sizing decisions.

## Durable ledger

SQLite stores canonical report bytes under a unique SIM/SPY/execution-session key
with decision ID. Use FULL synchronous transactions. Same inputs retry retrieves
byte-identical report without a second row. Changed inputs for an existing session
fail closed as a conflict; never replace or silently issue another plan. Failed
output publication does not undo ledger recording; a retry can republish its report
to a fresh path. The ledger freezes one offline rehearsal decision per session,
including blocked outcomes; it is not order reservation, account reconciliation,
tamper-resistant storage or a real-time adaptive execution journal. Corrupt row
hash/content mismatches fail closed. Never store account identifiers beyond SIM.

## Acceptance

Tests precede implementation: buy/hold/sell/warmup; causal future-data independence;
early close/DST and exact trading-window boundaries; stale/future/crossed/delayed
quotes; unreconciled/pending/uncertain/halted portfolio; independent fee/cash/
exposure/notional/capacity gates; no spread double counting; deterministic results
under ambient Decimal changes; ledger retry/conflict/corruption and failed-output
recovery; CLI/archive use outside checkout. A synthetic demo produces all action
classes and byte-identical repeated reports without sockets or optional SDK imports.
