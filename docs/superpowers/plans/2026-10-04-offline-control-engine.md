# Offline Control Engine Implementation Plan

> **For agentic workers:** Use the executing-plans skill to implement this plan
> task-by-task. Steps use checkboxes to track actual implementation, not intentions.

**Goal:** Produce a deterministic, network-free reference engine that demonstrates
the M1 risk and recovery contract against synthetic scenarios.

**Architecture:** A single event reducer owns state, risk reservations and decision
history. A local journal records input events before applying them; replay rebuilds
state. The CLI emits simulated decisions and cancellation requests only.

**Tech stack:** Python standard library (`dataclasses`, `enum`, `decimal`, `json`,
`unittest`, `argparse`, `hashlib`); no installed third-party or broker dependencies.
Record the interpreter version used in the validation evidence.

**Specification:** [Delivery plan, M1 contract](../../plans/quant-trading-delivery-plan.md).
**Research:** [Broker assumption review](../../research/2026-10-04-broker-assumptions.md).
The fixture events model documented behavior; they do not certify an API adapter.

## File map

| Path to create | Responsibility |
| --- | --- |
| `quant_control/__init__.py` | Package marker |
| `quant_control/domain.py` | Immutable typed inputs, config and validation |
| `quant_control/risk.py` | Pure admission calculation and reason codes |
| `quant_control/engine.py` | Serialized transitions, reservations and outcomes |
| `quant_control/reconciliation.py` | Snapshot generation/completeness checks |
| `quant_control/journal.py` | Versioned local event persistence and replay validation |
| `quant_control/runtime.py` | Durable serialized reducer owner and restart |
| `quant_control/__main__.py` | Offline CLI and JSON output |
| `tests/test_control_domain.py` | Configuration and data boundaries |
| `tests/test_control_risk.py` | Hand-calculated exposure/cash/loss cases |
| `tests/test_control_engine.py` | Idempotency, fills, cancellation and halt transitions |
| `tests/test_control_engine.py` | Recovery and snapshot cases |
| `tests/test_control_journal.py` | Replay, restart and corruption cases |
| `tests/test_control_cli.py` | End-to-end offline scenarios and exit codes |
| `examples/control/A01.json–A14.json` | Synthetic versioned event streams and expected outputs |
| `.gitignore` | Python caches and generated replay artifacts |

Extend `README.md` with commands when implemented. Do not add a broker package,
credential loader, gateway configuration or paper/live transport to this milestone.

## Shared implementation decisions

Use frozen dataclasses for input records and schema-validated stable string values
for side, mode, event kind, state and decision reason. The latter is the implemented
JSON boundary convention rather than separate Enum types. Convert JSON decimal strings with `Decimal` at the boundary;
reject JSON floating-point prices rather than silently introducing binary rounding.
Use integer milliseconds for fixture timestamps, nondecreasing event time and a
strictly increasing event sequence. Snapshot as-of sequence and generation are
separate from event receipt time.

Public entry points:

```python
validate_config(raw: dict) -> ControlConfig
parse_event(raw: dict) -> Event
evaluate(intent: Intent, state: RiskView, config: Config, now_ms: int) -> Decision
apply_event(state: EngineState, event: Event, config: Config) -> Transition
accept_snapshot(state: EngineState, event: Event, config: ControlConfig) -> EngineState
replay(events: Iterable[Event], config: Config) -> ReplayResult
```

`Transition` contains new state plus a tuple of simulated outputs. Its caller must
replace the state before handling another event. No threading or asynchronous queues
are necessary for M1. Denial reason codes are stable machine-readable values, such as
`NOT_READY`, `STALE_ACCOUNT`, `STALE_QUOTE`, `EXPIRED`, `CASH_LIMIT`,
`POSITION_LIMIT`, `LOSS_LIMIT`, `DUPLICATE_CONFLICT`, `UNKNOWN_OUTCOME`.

Assign an internal decision sequence to every processed intent. A duplicate identical
intent returns its original decision without advancing reservations or producing a
second submission output. Log its duplicate receipt as a separate audit event.

## Task 1: domain and configuration boundaries

- [x] Create the package marker and `tests/test_control_domain.py` before implementation.
  Cover A03 and A04: absent required limits, invalid modes, unknown fields, bool
  quantities, NaN/infinite monetary inputs, fractional quantities, negative time,
  future timestamps, crossed quotes, unknown account/instrument, bad enums.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_domain.py' -v` and confirm
  failure because the domain module is absent.
- [x] Implement the domain records named in the M1 contract, with explicit fields
  and no permissive defaults for numerical risk limits. Include a schema version
  and synthetic account/instrument identifiers. Validate config and each event
  before mutation. Invalid inputs produce a typed error; the CLI fails closed.
  Require fixture initial cash/equity/session-start equity and zero initial inventory;
  include this bootstrap baseline in the configuration digest. Opening orders and
  executions are empty in M1.
- [x] Add age-equals-limit, age-one-millisecond-over, expiry-equals-now and
  finite Decimal boundary cases. Run the same command and require all cases pass.

## Task 2: pure risk decisions

- [x] Write `tests/test_control_risk.py` for A04 and A05. Set cash to `1000`, equity and
  session-start equity to `1000`, zero inventory, unit limit `20`, order-notional
  limit `1000` and position-notional limit `2000`. A buy of six units at `100`
  passes in isolation. After reserving `600`, a second six-unit buy fails cash.
  A buy of four units at `100` passes exactly at remaining cash.
- [x] Add inventory ten, pending sells seven: sell three passes, sell four fails.
  Pending buys cannot make a short sell permissible. Test notional with ask above
  limit, and a prior pending buy limit above ask. Test daily loss equal to its cap.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_risk.py' -v`; confirm the
  expected missing implementation failure.
- [x] Implement `evaluate` following the formulas in the specification, returning
  a Decision without mutating input state. Require READY, valid fresh data and
  supported dimensions before evaluating exposure. Run the risk tests to green.

## Task 3: admission and order lifecycle

- [x] Write `tests/test_control_engine.py` for A05–A08 and A11: repeated intents, conflicting
  IDs, two sequential admissions, partial fills, duplicate executions, overfills,
  wrong-side/unknown fills, cancel timeout, late fills and repeated kill events.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_engine.py' -v` and confirm
  the missing reducer failure.
- [x] Implement a reducer with intent/decision ledger, order ledger, execution ledger
  and reservations. Persist an immutable normalized payload for deduplication.
  Accepted orders begin `PENDING_ACK`, reserving capacity without halting other
  valid admissions. Only an explicit acknowledgement-timeout or disconnect event
  changes them to `UNKNOWN_OUTCOME` and halts admission. Test two intents before the
  first acknowledgement. Never replay an uncertain submission as a new order.
- [x] Implement acknowledgement, partial fill, terminal fill, cancel request,
  cancel confirmation, rejection and unknown-outcome transitions. A cancel
  confirmation carries a cumulative filled quantity; inconsistent or incomplete
  execution evidence keeps the order unresolved until reconciliation. Retain
  execution history after terminal states so late duplicates remain idempotent.
- [x] Implement kill as a latched halt with deduplicated simulated cancellation
  outputs. Continue recording fills while halted. Run engine tests to green.

## Task 4: recovery and readiness

- [x] Write `tests/test_control_engine.py` for A01, A02, A08–A10 and A13.
  A02 starts with fixture cash/equity/session-start equity `1000`, inventory `0`;
  a matching first snapshot plus reset establishes READY and the same baseline.
  A nonzero first-snapshot position is unexplained and must halt.
  Test a completed empty snapshot separately from absent position/order callbacks;
  include stale generation responses, account mismatch, missing execution data,
  unexplained inventory and open orders received after a disconnect. Add a missed
  partial fill recovered from full execution records, absent terminal evidence,
  a fill during collection and an older account snapshot after an applied fill.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_engine.py' -v`;
  confirm expected failure before implementing reconciliation.
- [x] Implement generation-scoped accumulation. Completion requires all four
  components, matching as-of sequence, fresh values, consistent positions/cash and
  resolved local order outcomes. Apply the spec's evidence rules for open, filled,
  cancelled and rejected orders; execution IDs alone are insufficient. Compare
  snapshot cash/inventory with baseline plus unique executions through the common
  as-of broker sequence. Replace the baseline only on agreement; mark those fills
  accounted for without charging them twice. A fill/account update during collection
  invalidates the generation and requires a new snapshot covering that event.
  Reject snapshots older than the latest applied broker sequence. Discrepancies
  produce reasons and remain halted. A known pending order in a consistent snapshot
  restores its remaining reservation.
- [x] Implement explicit operator-reset fixture events, preventing reset from
  bypassing incomplete reconciliation, stale data or breached limits. Reset is
  valid only for the current generation; it does not carry into a later recovery.
- [x] Implement broker-notification fixture mapping using the research note:
  disconnect invalidates readiness; 1101 requests resubscription; 1102 preserves
  subscription intent; 2100 invalidates account updates. All require the applicable
  fresh data and recovery checks before another accepted intent.
- [x] Run reconciliation and engine suites; ensure the first accepted intent can
  only occur after complete initial reconciliation and explicit reset.

## Task 5: local journal and restart

- [x] Write `tests/test_control_journal.py` for A12 and A14: repeated replay, duplicate
  sequence, invalid schema, modified payload, truncated final record, changed config,
  journal write failure and restart with unresolved orders.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_journal.py' -v`; confirm
  missing implementation failure.
- [x] Implement an append-only JSONL journal containing schema version, sequence,
  canonical event, configuration digest and chained SHA-256 digest. Decimal values
  serialize as strings; canonical JSON sorts keys. The chain detects corruption,
  not malicious tampering. Flush and fsync before applying an event or emitting an
  output; a write error halts admission. No parallel writers are supported.
- [x] Replay validates all records before permitting continuation; corruption or
  truncation fails closed without silently dropping records. Rebuild from validated
  inputs, preserving reservations, ID history and session-start equity.
- [x] Separate historical replay from restart: replay reproduces original results;
  continuation appends a restart event that enters RECONCILING and emits no new
  submissions until current-generation reconciliation and reset complete.
- [x] Run journal tests and the full suite. Use temporary directories for every
  test so no fixture or user file is overwritten.

## Task 6: runnable scenarios and completion evidence

- [x] Add synthetic fixture cases mapping each A01–A14 to expected decisions,
  final cash/inventory/reservations/state and reason codes. Every scenario declares
  config, data provenance `synthetic` and relative clock origin; expected outcomes
  are mapped by scenario ID in `tests/test_control_cli.py`. No market returns
  or profitability statistics are produced.
- [x] Write `tests/test_control_cli.py` before the CLI: run subprocesses with broker-related
  environment variables absent; require identical normalized output across runs,
  no accepted intents for invalid fixtures and distinct exit codes.
- [x] Run `python3 -m unittest discover -s tests -p 'test_control_cli.py' -v`; confirm failure
  because the CLI does not exist.
- [x] Implement `python3 -m quant_control replay --fixture PATH --output PATH`.
  Refuse existing output files unless a future explicit overwrite option is added.
  Exit 0 for a valid replay, including expected risk rejections; exit 2 for invalid
  input/config/journal and 1 for unexpected runtime failure. Output includes schema,
  configuration and input digests, final state and ordered decisions.
- [x] Add tests that patch socket creation to raise for all in-process replay calls;
  inspect imports to confirm no transport/SDK dependency exists. A subprocess smoke
  test complements this check; it does not alone prove absence of network access.
- [x] Run `python3 -m unittest discover -s tests -v` and
  `python3 -m compileall -q quant_control tests`. Require zero failures.
- [x] Run two CLI replays into separate temporary outputs; compare byte-for-byte.
  Record interpreter version, commands, test count and scenario mapping in the
  delivery plan's progress record. Mark M1 complete only after all A01–A14 pass.
- [x] Review the diff, run `git diff --check`, and update README usage and scope.

## Deferred requirements that must not disappear

M2 adds fees, adverse fill assumptions, mark-to-market accounting and data provenance.
M4 adds a real transport, broker order-ID mapping, durable outbound uncertainty
handling, non-atomic snapshot reconciliation, account/client visibility, request
pacing, callback ordering and execution corrections. Real broker integration must
not treat this simulator's common snapshot sequence as an API feature.

Before M4, specify maximum journal growth, retention, operator recovery after storage
failure, backup/restore and single-writer enforcement. Live availability, liquidation,
margin, shorts, multi-currency portfolios and multi-account risk are outside M1.

## Validation evidence — 2026-10-04

- Authoritative command: `make check build demo`, exit 0, Python 3.14.0.
- Complete suite: 123 tests passed. Compilation and `git diff --check` passed.
- All A01–A14 IDs covered by CLI fixtures and domain/risk/lifecycle/journal tests.
  A03 deliberately returns exit 2 with no report or accepted output.
- Build artifact `dist/quant-system.pyz` uses only source packages and standard
  library; repeated builds are byte-identical and run outside the checkout.
- Demo artifacts: `.research-output/demo-76roqo4q`; verification log:
  `.research-output/final-verification.log`. Artifacts are ignored local outputs.
- Same fixture replay: byte-identical outputs. Durable restart preserves cash,
  IDs, pending exposure and session loss baseline; emits reconciliation only.
- Independent spec review approved core lifecycle/reconciliation and journal.
  Fixed demonstrated findings: stale refresh bypass, quote exposure breach,
  conflicting cancellation totals, reused execution sequence, rejection erasing
  reported missing fills, direct-constructor risk bypass and continuation tail
  validation before persistence. Regression tests cover each correction.
- Implementation uses stable schema-validated strings rather than Enum wrappers,
  and reconciliation tests share the lifecycle harness in `test_control_engine.py`.
- M1 is completed offline reference software. Its synthetic common snapshot
  sequence, no-fee accounting and synthetic account are not a real broker adapter.
