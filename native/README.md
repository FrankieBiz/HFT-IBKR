# Offline C++20 execution foundation

Run `./native/build.sh` from the repository root. Requires a local C++20 compiler
(default `clang++`, override `CXX`). Builds with `-Wall -Wextra -Werror -pedantic`
and runs native tests and a deterministic replay. No downloads, network calls,
broker SDK, credentials, infrastructure, or live execution path exist here.

`include/execution.hpp` is a header-only, single-owner execution core; only the
queue is intended for concurrent use. The replay dequeues a fixed-size intent,
checks the parent intent on an engine copy, generates a schedule, applies a
configurable token bucket, checks each child against current reservations,
simulates partial fills, prints an in-memory audit, disconnects, reconciles,
and manually restarts. Output is synthetic and contains no strategy result.

## API and contracts

- `SpscQueue<T, Capacity>` accepts trivially copyable payloads and a power-of-two
  capacity. Exactly one producer calls `push` and one consumer calls `pop`.
  Acquire/release sequence publication prevents reading unwritten slots or
  overwriting unread slots. Full returns false and increments an atomic overflow
  counter (including retry attempts); empty returns false. Unsigned sequence
  wrap is supported with power-of-two indexing. A caller must halt or explicitly
  retry on overflow; silently dropping an execution event is unsafe.
- `Engine(Limits)` begins in `BOOT`. `begin_recovery`, `reconcile(snapshot, now)`,
  then `restart()` are all required before `READY`. Initial bootstrap requires
  a flat snapshot with no open orders. Reconnect snapshots must exactly match
  local cash, positions, and remaining open quantities. Unknown or conflicting
  state halts; there is no automatic adoption of external state or unhalt.
  Mismatches require investigation outside this demonstration.
- `quote(symbol, price, timestamp, now)` and `submit(order, now)` use nonnegative
  monotonic **nanoseconds within a replay**, never Unix timestamps. Clock
  regression, future/stale quotes, conflicting same-time quotes, price jumps,
  missing marks, exposure breaches, and drawdown halt. Restart uses the latest
  engine clock, so advance quotes/reconcile with current time before restarting.
  All held positions and working orders need fresh marks. Drawdown uses peak
  marked equity since bootstrap and persists through recovery.
- `poll(now_ns)` advances the clock and checks stale marks, portfolio limits,
  and pending-order timeout (default 30 seconds). The driver must call it even
  when no events arrive. Timeout halts without assuming cancellation.
- Orders are long-only limit orders in integer units. Cash and notional values
  are in one synthetic currency; prices are currency per unit. All buys reserve
  remaining quantity times limit; exposure uses the larger of quote and limit.
  Sell orders reserve held units and never rely on outstanding buys. Filled and
  pending sell quantities cannot exceed holdings. `Limits` caps each order,
  aggregate symbol quantity/notional, gross exposure, open-order count, price
  jumps, quote age, sector exposure, daily loss, and drawdown. Symbols require explicit sector mappings. Daily loss uses replay days of 86,400 seconds from time zero, not an exchange session calendar. Drawdown and daily loss halt at equality as well as beyond the threshold. Defaults are simulation fixtures, not advice.
- Identical accepted order IDs and fill IDs are idempotent. Reusing an ID with
  different fields halts. Fills above remaining quantity, beyond the limit price,
  with invalid numbers, or for unknown orders halt before mutation. Valid fills
  are accounted even while halted, because fills may arrive after disconnect;
  a fill during recovery invalidates the reconciled flag. Accepted fills can
  trigger a portfolio halt after accounting. A false return therefore requires
  reading state/audit, not assuming that no accounting occurred.
- `TokenBucket(capacity, tokens_per_second, start_ns)` limits one token per
  successful `take(now_ns)`. Backward time is rejected without adding tokens.
  Capacity must be <= 10^9 so unit consumption remains representable. Parameters are configurable simulation values, **not asserted IBKR limits**.
- `schedule(total, slices, horizon_seconds, risk_aversion, sigma, eta)` samples
  the continuous linear temporary impact Almgren–Chriss inventory trajectory
  `x(t) = X sinh(k(T-t))/sinh(kT)`, with `k = sqrt(lambda sigma^2 / eta)`.
  Sigma is arithmetic price volatility in currency/unit/sqrt(second), eta is
  linear temporary price impact per trading rate, and lambda has the units
  needed for expected cost plus lambda times cost variance. Parameters must be
  calibrated consistently outside this code. Zero lambda or sigma gives TWAP.
  Exponential ratios avoid hyperbolic overflow; the small-k limit avoids loss
  of precision. Rounded integer inventories yield nonnegative child quantities
  that sum exactly to the parent. Zero-size slices are valid and should be
  skipped by consumers. Limits: total <= 10^12, slices <= 10^6. Negative, NaN,
  infinite, or otherwise invalid inputs are rejected with `invalid_argument`.

Model reference: Almgren and Chriss, *Optimal Execution of Portfolio
Transactions*, continuous-time linear impact solution,
https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf
(reference checked by the coordinating task on 2026-10-03). This implementation
is an educational continuous approximation, not the full discrete impact model.

## Validation and limits

Tests cover full/empty/overflow queue behavior, 100,000 concurrent ordered
transfers, schedule conservation and extreme parameters, rate limiting,
recovery transitions, partial fills, duplicates and conflicts, cash and sell
reservations, invalid inputs, stale/future time, order timeout, price jumps, and drawdown.

The engine uses floating-point cash with exact snapshot comparison; it is not
suitable for broker accounting. No fees, spread, adverse selection, market
impact in fills, exchange calendars, tick/lot rules, durable
journal, process-restart recovery, multi-currency, portfolio margin, fill
corrections, or broker event adapter are implemented. Identifiers and audit
records remain in memory without eviction. The engine allocates memory and
has no hard real-time or performance guarantee. Fill time must be represented
by the event driver's current engine clock; fill records do not carry their own
timestamp. Halt does not cancel outstanding orders or flatten positions.
A successful replay demonstrates software plumbing only.

Cancellation: `cancel_request(order_id)` retains reservations until `cancel_ack(event_id, order_id)`. Duplicate acknowledgements are idempotent. A valid late fill after acknowledgement is accounted and halts for reconciliation. `queue_overflow()` latches an execution halt; the integration test demonstrates full-queue handling. Cancellation does not imply a broker API exists.
