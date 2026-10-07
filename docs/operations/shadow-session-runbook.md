# Daily shadow decision rehearsal

The current direction is the [bounded daily trend overlay](../../README.md),
with the original signal and stronger evidence/risk/health controls. SPY trend is
unproven. HFT, AI and framework migration remain deferred. This page describes
explicit offline rehearsals; operational scripts additionally enforce study
readiness before accessing keys/services or printing cached proposals.

## What this command does

`quant_session` joins validated local price data, an explicit session schedule and
invented portfolio/quote snapshots to causal trend signals, independent cost-aware
sizing and a durable SQLite decision ledger. It produces a non-binding proposal or
an explanation of HOLD/BLOCKED. No SDK, socket, account request or order method is
used. It does not change the separate SIM control/recovery engine.

All snapshots are restricted to SIM/SPY/USD. Quotes are either synthetic or a
declared `alpaca_iex_realtime` quote. `quant_session live-inputs` renders that quote
and the schedule from the free Alpaca calendar and SPY's real-time IEX quote, for a
portfolio the user declares. IEX is one venue, not the national best quote. The
command refuses to run outside today's session, so a closed market never freezes a
BLOCKED decision. `scripts/daily_shadow.sh` chains fetch, prepare, live inputs and
plan; see the [Windows + WSL runbook](windows-wsl-runbook.md#6-each-trading-day-record-the-shadow-decision).
None of this establishes strategy validation. It is not a broker adapter, live
monitor or paper-order submission.

## Automatic end-to-end demonstration

```sh
make check build demo
```

The fresh `.research-output/demo-*` folder includes four **independent** scenarios:

| File | Expected result |
| --- | --- |
| shadow-buy.json | LONG while flat; proposes a cost-aware whole-share BUY |
| shadow-hold.json | LONG with existing shares; HOLD, no daily rebalance |
| shadow-sell.json | CASH signal with shares; proposes a full SELL if limits pass |
| shadow-blocked.json | Stale synthetic quote; BLOCKED, no proposal |

These are not a continuous account history or evidence of brokerage fills.
`shadow-buy-repeat.json` must be byte-identical to the first decision. The demo
changes the snapshot and attempts to reuse the same session ledger; it must reject
that conflict and produce no `shadow-conflict.json`. `summary.json` records these
checks alongside existing research, control, evaluation and dashboard checks.

The tracked `examples/shadow/schedule.json` is an invented weekday schedule,
including actual exchange holidays. Do not use it as a real trading calendar.
Example portfolio limits are software fixtures, not recommended capital allocation.

## Individual session

Reuse a bundle produced by the demo, choosing a new ledger/output path:

```sh
python3 -m quant_session plan \
  --bundle .research-output/YOUR_DEMO_DIRECTORY/synthetic.qdata \
  --config examples/research_config.json \
  --schedule examples/shadow/schedule.json \
  --snapshot examples/shadow/buy.json \
  --ledger .research-output/shadow-ledger.sqlite \
  --output .research-output/shadow-plan.json
```

The portable form is `python3 dist/quant-system.pyz session plan` with the same
arguments. Output must not already exist. Exit 0 means the shadow report was
recorded/published, including a valid BLOCKED result; it never means trading is
enabled. Exit 2 means invalid inputs, conflicting decision, ledger integrity failure
or output/storage error; unexpected runtime failure is exit 1.

## Interpretation and recovery

Only prices through the immediately preceding completed declared session enter the
signal. The runner checks schedule coverage, UTC/NY session dates, trading window,
freshness, reconciliation declarations, pending/uncertain orders and halts. Insufficient
complete history is WARMUP. Later bundle observations cannot affect the signal or
sizing, although their full-source hash can change the report's provenance/ID.

Buys reference ask; sells reference bid. The existing research half-spread term is
zeroed because the quote already expresses spread. Slippage, impact and fees remain
illustrative estimates. Settled cash funds buys. Conservative effective NAV is the
minimum of declared NAV and the synthetic cash-plus-bid-marked inventory value;
declared and ledger-observed peak NAV determine the drawdown entry gate. These marks omit unpaid dividends
and other assets and cannot be treated as a real broker balance sheet.

The ledger serializes planning, observed peak/latched entry-risk memory and one
decision per SIM/SPY/execution-session, including blocked
results. An identical retry in a fresh output file recovers the same canonical report
without a second row. If output publication fails after the transaction committed,
retry identical inputs with a valid fresh destination. Changed inputs conflict;
they never replace the stored decision. New sessions must be chronological. An
edited lower peak or recovery cannot clear an observed breach. Valid NAV marks
still update risk memory during a manual trading halt; stale/invalid marks do not.
Legacy ledgers lacking memory block new sessions pending reviewed migration.
Independent rehearsal cases need independent
ledgers. Do not delete/reset a ledger to bypass a conflict in an operational workflow.

This is a local audit/idempotency guard, not order reservation, fill accounting,
tamper-resistant storage or an adaptive intraday journal. A declared halt blocks all
proposals. A drawdown breach blocks entries but still proposes signal-driven exits,
matching the backtest's latched buy-only halt. Neither liquidates inventory or guarantees a
maximum loss. Full exits
can be blocked by capacity/notional limits; partial exit policy is not implemented.

## What remains before actual paper trading

1. A separately reviewed read-only IBKR snapshot collector and real-stream
   normalization: account ownership, cash/settlement, positions, orders, executions,
   commissions and incomplete/asynchronous recovery.
2. Reviewed historical data and corporate actions, calibrated fees/slippage,
   chronological economic evaluation and a prospective shadow log.
3. A broker order adapter with durable identity maps, reservations, partial fills,
   cancellation/unknown-outcome recovery, watchdogs and explicit reset policy.
4. Separately authorized paper-account reads/orders on the user's Windows/WSL
   computer and operational drills. Live operation remains a separate decision.
