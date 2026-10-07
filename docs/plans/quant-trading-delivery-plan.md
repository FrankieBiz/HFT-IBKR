# Quant trading delivery plan

Updated 2026-10-07. **Current direction: a bounded daily SPY trend overlay, with
research evidence and durable entry-risk controls before operational shadowing.**
The [October 6 design](../superpowers/specs/2026-10-06-robust-trend-design.md) and
[implementation plan](../superpowers/plans/2026-10-06-robust-trend.md) supersede
earlier sequencing. The HFT/order-flow branch is closed; AI, framework migration,
crypto/FX, grid and DCA remain deferred until incremental economic evidence exists.
The original proposal and earlier research decisions remain historical context.

The [October 7 reliability scope](../superpowers/specs/2026-10-07-reliability.md)
preserves frozen research/config/protocol identities and existing history. It
repairs quote/NAV inputs, app eligibility/health reporting, bounded daily retries
and interrupted publication recovery, and exposes verified strategy evidence.
Study display verification is content cached; operational gates remain fresh.
Maintenance is on demand whenever requested, with tested commits, GitHub pushes
and documentation updates; no unattended maintenance schedule is installed.

The revised [spy-trend-v2 protocol](../../studies/spy-trend-v2/PROTOCOL.md) uses a
25% entry target, 30% entry exposure cap and 10% drawdown halt on new buys. These
are research sleeve assumptions, not loss guarantees or personalized allocation.
V1 remains unchanged. V2 shares v1's registry: consumed final sessions cannot be
reused. Historical source/config/protocol/freeze/registry/code verification and the
verdict are mandatory before daily operator scripts access keys or services.

## Objective and boundaries

Build reproducible offline research and execution-control simulations first. Advance
to broker integration only after their controls have evidence behind them. Successful
software tests do not establish strategy profitability or operational readiness.

The implemented R1 research slice uses Python standard library, Decimal arithmetic,
an independent admission gate and synthetic daily ETF fixtures. The implemented
M1 order-control engine uses immutable domain records,
integer time units, Decimal monetary quantities, a single deterministic event reducer,
and synthetic fixtures. This is a reference model; it makes no live latency promise.
It has no broker SDK, credentials, socket transport, deployment or trading endpoint.
Research, simulation, paper and live modes must remain distinct. The first milestone
accepts only `simulation`; all other modes fail configuration validation.

## Delivery sequence

| Milestone | Deliverable | Exit evidence | Status |
| --- | --- | --- | --- |
| M0: correct the baseline | Dated broker review, risk contract and scoped implementation tasks | Primary links; review of contradictions and failure cases | Completed planning review |
| R1: daily ETF research slice | SPY trend signals, next-open replay, independent cash/exposure gates, dividends, cost scenarios and buy-and-hold comparison | Tests, independent review, deterministic synthetic CLI replay | Implemented; validation evidence in R1 plan |
| M1: offline control engine | Risk decisions, order reservations, reconciliation and deterministic scenario replay | All acceptance scenarios below pass with no network access | Implemented offline; acceptance fixtures/tests pass |
| M2: reviewed historical data and calibrated replay | Strict local export intake, reviewed datasets, calendar/corporate actions, empirical fee/spread/slippage/impact assumptions | Provider/license review, hand-calculated P&L, historical sensitivity report | Intake/bundle mechanics implemented; actual historical inputs and calibration outstanding |
| M3: research evaluation | Chronological causal evaluation, explicit embargo, frozen final holdout and trial registry | Leakage tests; reproducible split indices and experiment manifest; documented selection procedure | Evaluation software implemented; empirical validation outstanding |
| H0: target-machine preflight | Environment diagnostic followed by isolated single-checkpoint Laya inference on RTX 3070 Ti | Actual CUDA/device/dtype, peak model memory with headroom, bounded-input timings and fallback/crash evidence | Environment diagnostic implemented; target GPU and model benchmark outstanding |
| A1: optional local text features | Timestamped fixed-taxonomy classification, calibrated abstention and controlled price-only comparison | Frozen labels/rubric/model revision; classification baselines; financial ablation and prospective evidence if training cutoff unknown | Planned; Laya is not integrated and has no order authority |
| F1: framework compatibility study | Pinned NautilusTrader offline replay and IBKR adapter design; ib_async fallback if necessary | P&L equivalence, version-matched API/docs, A01–A14 mapped to adapter behavior, license/dependency review | Planned; no framework adopted for operational use |
| V1: offline results view | Self-contained chart/cost/provenance/control snapshot dashboard | Automated report rendering, keyboard/mobile browser checks, loopback route restrictions | Implemented and opened locally; read-only offline snapshot |
| S1: integrated shadow session | Causal completed-session signal, explicit synthetic quote/portfolio, independent admission and durable decision ledger | Buy/hold/sell/blocked rehearsal, exact retry, conflict/corruption/causality tests, portable CLI | Implemented offline; 178 total tests and full synthetic demo pass; no order authority |
| R2: bounded trend robustness | Separate v2 sleeve protocol, causal walk-forward selection and paired block-resampling diagnostics | Holdout metrics excluded; deterministic paired samples and cost stress | Software implemented; historical economic evidence outstanding |
| S2: enforced evidence and durable risk | Authenticated historical readiness before operator scripts; serialized ledger peak/entry-halt memory | Gate bypass, restart, manual-halt loss marking, corruption and exact-retry regressions | Software implemented; no broker order authority |
| O1: local health | Short-interval heartbeat and independent offline deadline checker | Missed decisions/failed process checks | Software implemented; independent scheduler and alert delivery not installed |
| M4: paper adapter | Account-scoped adapter, pacing scheduler, durable journal, operator runbook | Authorized paper tests including reconnect, uncertain submission and cancel/fill races | Not started; requires separate authorization for account actions |
| M5: live readiness review | Instrument-specific risk policy, regulatory applicability review, operational drills and budget | Reviewed evidence and explicit live authorization | Not started; no live path authorized |

M2 needs reviewed historical inputs and calibrated assumptions. The M3 implementation
plan is [chronological evaluation](../superpowers/plans/2026-10-04-chronological-evaluation.md). The initial research
choice is SPY, daily 200-session trend-following, with long-or-cash positioning;
[R1 design](../superpowers/specs/2026-10-04-etf-trend-research-design.md) records
the decision and limitations. The revised research sleeve policy is explicit;
production limits remain unselected. Reviewed historical evaluation and an adapter design
remain necessary before account-level paper tests.

An optional standalone [paper Gateway connection diagnostic](../operations/paper-gateway-setup.md)
now waits for the official SDK readiness callback and disconnects without requesting
account data or submitting/cancelling orders. Its fake-client, timeout and SDK
protobuf compatibility checks are complete; the real Windows/WSL connection remains
unverified. This is setup tooling, not implementation of the M4 paper adapter.

## Current priority and retained architecture constraints

The next empirical work is reviewed daily data/corporate actions, observed cost
calibration, v2 walk-forward and paired-block diagnostics, and a qualifying frozen
historical study followed by prospective shadow observation. If previous studies
consumed v2's proposed historical holdout, freeze fresh future dates; do not reset
the registry. Cash yield/taxes matter for a sleeve holding most capital in cash.
No completed economic study is asserted by this development work.

Ledger-backed planning serializes peak/drawdown entry-halt memory with each frozen
decision. Restarts, lower declared peaks and NAV recovery cannot clear a breach.
Economic marks remain eligible during manual trading halts; invalid account/quote
marks do not update memory. Signal exits remain subject to admission. Legacy
ledgers require reviewed migration and must be retained. A local heartbeat and
independent offline checker report operational failures; independent scheduling
and alert delivery remain operator responsibilities.

Retain the following optional AI/framework architecture constraints if those branches
are later reopened. They are not the selected next milestones.

Laya runs in a separate process/environment without credentials. Begin with one
English checkpoint, batch one and a 512-token cap; measure actual residency rather
than equating checkpoint file size with VRAM. Record invalid output, truncation,
timeouts and CPU fallback as missing features. A feature-dependent strategy blocks
new entries on missing features; deterministic exits/recovery remain available.
No risk check, accounting calculation or order callback waits for model inference.

The earlier F1 study selected NautilusTrader as the first candidate, not an immediate replacement of
the tested reference software. Investigate stable `v1.231.0` with matching source
and docs; current `latest` IBKR docs describe a different adapter generation.
Use a separate Python 3.12 environment for the initial study and pin dependencies
only after compatibility evidence. Map framework events into the existing risk
contract, including fees, uncertain orders, snapshot consistency and restarts.
If those mappings fail, evaluate a thin ib_async adapter rather than weakening
controls. No broker connection is needed or authorized for F1's offline study.

Framework adoption is now optional rather than a prerequisite for the next offline
read-only callback study. Start from the pinned official SDK and review real-stream
snapshot semantics; no framework replaces that work. Empirical M3 evidence and
operational controls precede account-level paper-order M4 tests. Model experiments must not
delay a valid price-only paper candidate if they fail to add useful evidence.
No VPS, paid CLI workflow, cloud inference or complex deployment is selected.
The current simulation journal requires POSIX locking; native Windows support
is unverified, so use native Linux or WSL2 for the proposed local setup.

S1's [shadow-session runbook](../operations/shadow-session-runbook.md) documents
non-binding proposals, conservative synthetic NAV, settled-cash sizing, bid/ask
cost convention and the freeze-once ledger. It does not reconcile IBKR streams or
implement a real-time scheduler. Real sources, source normalization and a distinct
read-only snapshot contract remain dependencies for that daily/broker branch. The
[read-only capture design](../superpowers/specs/2026-10-04-ibkr-readonly-snapshot-design.md)
specifies separate broker observations, completion markers and readiness blockers;
the collector is not implemented and no account reads have been performed.

## M1 risk and recovery contract

### Inputs and scope

Use one synthetic USD account, one synthetic instrument, multiplier one, whole units,
long-only limit orders. These deliberately narrow constraints make the first tests
auditable. Unsupported currency, account, instrument, side, mode or order type is
rejected. Numerical fixture limits are test inputs, never production defaults.

An intent contains an immutable ID, instrument, side, quantity, limit price, creation
time and expiry time. Quotes contain bid, ask, receipt time and data type. Account
state contains cash, equity, session-start equity and receipt time. A complete
reconciliation snapshot includes positions, open orders with remaining quantities,
full execution records (execution ID, order ID, side, quantity, price and sequence),
terminal order evidence, account values, generation ID and completion indicators.

All money is finite Decimal; quantities are positive integers excluding booleans.
Reject NaN/infinity, zero/negative prices, crossed quotes, future or stale timestamps,
expired intents and missing fields. Configured quote/account age limits are inclusive:
age equal to the limit is valid; larger age is stale. Intent expiry is exclusive:
`now >= expires_at` rejects. Use a caller-supplied monotonic simulation clock.

Every fixture declares initial cash, initial equity, session-start equity and initial
inventory (zero only in M1), with no opening orders or executions. These values are
the bootstrap accounting baseline, included in the configuration digest and journal.
The first snapshot must match them; it cannot silently adopt positions. For the A02
startup fixture, cash/equity/session-start equity are `1000`, inventory is `0`, and
the first completed matching snapshot establishes that same reconciled baseline.
Restart recovers the journal baseline rather than seeding it from a new snapshot.

### Control states

`BOOTSTRAP -> RECONCILING -> READY` is the only startup path. `HALTED` is latched
after a disconnect, unknown order outcome, invalid state, risk breach or kill request.
A reconnect may enter `RECONCILING`; it cannot enter `READY` on connectivity alone.
After recovery, explicit reset plus a current complete reconciliation is required to
clear the halt. Clearing a latch never relaxes a violated risk limit.

Every reconciliation attempt uses a new generation ID. Ignore stale-generation
responses. Collect positions, open orders, executions and account values together;
partial, conflicting or timed-out snapshots cannot certify readiness. An explicit
empty completed snapshot differs from absent responses. M1 uses synthetic snapshots
with a common as-of sequence; M4 must establish a consistent cut across real streams,
merge intervening events and repeat reconciliation when consistency is uncertain.

For M1, all snapshot components describe the state after the same synthetic broker
sequence, which must be at least the last applied broker sequence. A new fill or
account update arriving during collection invalidates that generation; retain the
event, start another generation and require a snapshot covering it. On completion,
derive expected cash/inventory from the last reconciled baseline plus each distinct
execution through the snapshot sequence. Require exact equality with snapshot
cash/inventory, then replace the baseline and mark those executions accounted for.
Account updates used for freshness/equity never independently add fill cash flows.
Stale snapshots cannot overwrite newer state. External deposits and withdrawals are
unsupported in M1 and therefore cause a reconciliation discrepancy.

### Admission, reservations and order outcomes

Risk checks and reservation creation are one serialized transition. Reserve before
emitting an accepted intent, so two simultaneous buys cannot both spend the same cash.
Each accepted intent ID is permanently associated with its payload for the replay:
identical retry returns the recorded result without another emission; changed payload
under the same ID is an error that halts processing. Rejected intents are also recorded.

Accepted intents enter `PENDING_ACK`, retaining reservations while allowing other
admissions within the remaining limits. An explicit acknowledgement timeout or
disconnect changes unresolved submissions to `UNKNOWN_OUTCOME` and latches HALTED.
Ordinary acknowledgement latency alone is not an unknown-outcome incident.

For pending buys, reserve `remaining_quantity * limit_price`; candidate buys must fit
free cash and maximum order notional. Let `q` be held units, `B` pending buy units and
`S` pending sell units. A candidate buy of `n` must satisfy `q + B + n <= max_units`;
a candidate sell must satisfy `S + n <= q`. Do not offset pending buys against sells:
either side can fill independently. Bound position notional using `(q + B + n)` times
the maximum of current ask and all relevant buy limits (omit `n` for sell evaluation).
Reject if that exceeds the configured position-notional limit.

Daily loss is `max(0, session_start_equity - equity)`; equality with the loss limit
halts new admission. M1 requires authoritative synthetic equity updates, does not
infer P&L from fills, and does not reset the session baseline on restart. Fees and
currency conversion are excluded from this narrow fixture model and required in M2.

Partial fills reduce the reservation only by the filled units and update inventory
and cash at the reported fill price. Fill prices must be positive and respect the
limit. Duplicate execution IDs with identical payload have no effect; conflicting
duplicates, unknown orders or overfills halt. Order-status callbacks cannot double
apply a fill or regress terminal state. Cancellation requests retain reservations
until terminal confirmation and a consistent fill record/snapshot establish remaining
exposure. A timeout is an unknown outcome, never proof of rejection or cancellation.

Reconciliation imports broker-known open-order reservations. An uncertain local order
remains blocking until mapped to a known outcome; absence from open orders alone does
not prove it was never accepted. Unknown external orders or unexplained positions halt
M1, which has no policy for adopting manual trading activity.

Resolution requires complete execution payloads plus one of: a matching open order
whose filled plus remaining quantity equals the submitted quantity; a terminal filled
record with executions totaling that quantity; a terminal cancellation whose filled
quantity equals the execution total; or explicit terminal rejection with zero fills.
All evidence must identify the original order and agree at the snapshot sequence.
Missing terminal evidence, a missed partial fill without its execution record, or
conflicting payloads keeps the order unresolved and the engine halted.

### Kill behavior

Kill means latch HALTED, reject new intents and emit at most one simulated cancel
request per known open order. Keep ingesting fills, account updates and recovery
events. It does not imply cancellation succeeded, positions are flat or disconnect
is safe. Liquidation is a distinct future policy with its own limits and authorization.

### Acceptance scenarios

| ID | Scenario | Required result |
| --- | --- | --- |
| A01 | Startup, missing snapshot, incomplete or old-generation recovery | Zero accepted intents |
| A02 | Complete coherent snapshot and explicit reset | READY only if all prerequisites and limits pass |
| A03 | Missing/invalid config; paper/live mode; malformed money, quantity or time | Deterministic rejection; no accepted output |
| A04 | Freshness/expiry and loss/notional/quantity boundaries | Exact boundary behavior matches this contract |
| A05 | Two buys before first acknowledgement, each affordable alone but jointly over limit | First remains PENDING_ACK and reserves; second rejects for cash |
| A06 | Duplicate intent; same ID with altered payload | No second emission; altered payload halts |
| A07 | Partial fill, duplicate execution, cancel/fill race | Cash/inventory applied once; unresolved units remain reserved |
| A08 | Lost acknowledgement or missed partial fill followed by reconnect | Resolve using complete execution/order evidence; no blind resubmission or automatic readiness |
| A09 | Disconnect and 1101 versus 1102 fixture events | Both block admission; only 1101 requests market-data resubscription |
| A10 | Account-data unsubscription or stale quotes | Block admission until valid state is restored and reconciled |
| A11 | Kill with pending orders and later fills | No new accepted intents; cancellation not reported as flattening |
| A12 | Replaying the same fixture twice | Identical decisions, state and audit output |
| A13 | Snapshot shows external order, conflicting execution, unexplained inventory, older accounting or a fill during collection | HALTED or reconciliation restarted; no duplicate cash charge or rollback |
| A14 | Restart from journal with pending/uncertain orders | Preserve IDs/reservations/loss baseline; require reconciliation |

## Progress record

- 2026-10-04: implemented the static read-only results dashboard and loopback-only
  page server. Automatic demo renders charts/cost variants/provenance and synthetic
  control snapshots. Full checks/build/demo passed with 154 tests; browser checks
  passed, with no external requests. Opened the local viewer for the user.
  [View implementation/evidence](../superpowers/plans/2026-10-04-offline-results-view.md).
  The view establishes neither account connectivity nor market advantage.

- 2026-10-04: published the offline baseline to
  `FrankieBiz/feat-complete-quant-research`. Added strict offline price/distribution/
  calendar intake with declared licenses, consumed hashes, deterministic bounded
  bundles and direct research integration. `make check build demo` passed with
  146 tests; bundled replay financial results matched the original fixture.
  [Intake implementation/evidence](../superpowers/plans/2026-10-04-data-intake.md).
  No real historical data or provider licenses have been independently reviewed.

- 2026-10-04: inspected repository at `6d0e7b4`; only proposal and agent guidance
  existed. No implementation or test suite was present.
- 2026-10-04: checked current primary IBKR documentation, recorded five corrections,
  withdrew unsupported guarantees, and specified M1 acceptance cases.
- 2026-10-04: plan reviewer approved after corrections to pending acknowledgement
  semantics, recovery evidence, snapshot accounting and the initial cash baseline.
  Local document links, 14 acceptance IDs, whitespace and `git diff --check` passed.
  This was document verification, before R1 software implementation.
- 2026-10-04: user delegated market/strategy selection and authorized development.
  Implemented the separately scoped R1 daily ETF simulator; its tests validate
  software behavior on synthetic cases, not strategy advantage. M1 order lifecycle,
  journal and broker recovery have not been implemented.
- 2026-10-04: implemented M1 control/reconciliation/journal/restart and M3
  chronological evaluation/registry/frozen holdout software. Added portable build,
  local end-to-end demo and operator runbook. Final verification evidence follows
  in their implementation plans. Historical calibration and actual broker
  integration remain outstanding; no account actions have been authorized.

- 2026-10-04 authoritative offline release check: `make check build demo`, exit 0.
  Python 3.14.0; 123 tests passed; compilation/whitespace checks passed.
  Portable archive SHA-256:
  `cc9bd0fce63fd6179baca3292f2b4be3efe0908e925ba380a08d205a427d511f`.
  All 14 acceptance IDs exercised, repeated replay byte-identical, duplicate
  holdout blocked, completed report recovered identically, and durable restart
  retained uncertain reservations. Evidence is software behavior on synthetic data.
- 2026-10-04: researched the user's Laya repository and desktop hardware, compared
  relevant open-source stacks, and added H0/A1/F1. Single-checkpoint inference is
  expected to fit; target-machine measurements, financial benefit and framework
  compatibility remain unverified. Existing software checks were not rerun for
  this documentation-only update.
- 2026-10-04: implemented the H0 environment diagnostic in `quant_local`, including
  installed-version inventory, bounded NVIDIA/CUDA probes, fail-closed assessment,
  atomic reports and portable archive dispatch. Independent design/code review
  approved. `make check build demo` passed with 137 tests; archive SHA-256
  `d7b49a8c29c2979e6bf5c219ee8a6bc3b1abf81ce3b3f22f0b7aa850c9a21f12`.
  Current workspace correctly reported blocked (Darwin, 16 GiB, no torch/Laya).
  [Implementation evidence and next work](../superpowers/plans/2026-10-04-local-preflight.md).
  H0 target GPU/model benchmark, M2 real data/calibration, empirical M3, A1, F1
  and all actual broker integration remain outstanding.
