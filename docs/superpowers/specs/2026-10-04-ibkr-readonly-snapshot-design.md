# Read-only IBKR paper observation capture

Date: 2026-10-04. Status: proposed next-stage contract, not implemented.
This design follows the offline daily session planner. It does not authorize a
broker connection, account-data retrieval, order submission or cancellation.

## Scope and authorization

First implement callback normalization and capture assessment against fake SDK
clients and invented fixtures. Actual account reads require separate explicit
authorization naming the paper account session and data to be read. The user's
Gateway setup and handshake confirmation do not establish that authorization.

A future opt-in runner requires confirmation of paper login, Gateway Read-Only
API, and account-data access. These are operator attestations, not facts proved
by port 4002, account-name prefixes or nextValidId. Choose a nonzero, non-master
client ID; never change Gateway settings automatically. No credentials are read,
stored or accepted by the tool. Gateway authentication remains with the user.

The transport exposes an explicit allowlist: connect, disconnect, reqPositions,
cancelPositions, reqAccountSummary, cancelAccountSummary, reqAllOpenOrders and
reqExecutions. Subscription cancellation here stops data streams, never orders.
Exclude placeOrder, cancelOrder, reqGlobalCancel, exerciseOptions, what-if orders,
reqOpenOrders, reqAutoOpenOrders and automatic binding. Do not use client ID 0.
IBKR documents that reqAllOpenOrders does not bind orders, while binding may
cancel/resubmit an exchange order. [Order binding semantics](https://www.interactivebrokers.com/docs/tws-api/doc/orders/modifying-orders).

No historical/live market-data request belongs to this first capture. No model,
strategy, scheduler or risk path can invoke its transport.

## Dependency boundary

Use the official Mac/Linux SDK in the separate Ubuntu environment documented in
[paper Gateway setup](../../operations/paper-gateway-setup.md): SDK archive
10.50.02, installed ibapi version 10.50.2, protobuf 5.29.5. Recorded archive SHA-256:
`673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3`.
This digest is an observed artifact checksum, not a vendor signature. Reverify
the vendor download and license before a dependency update. Do not substitute an
unreviewed PyPI package or redistribute SDK source in the standard-library core.

The already-downloaded SDK source was inspected locally without a connection:
its wrapper implements commissionAndFeesReport and its client implements the four
read requests above. Current narrative documentation still names commissionReport
in places. Normalize the pinned SDK callback, test its protobuf decoder with fake
transport, and treat SDK upgrades as compatibility changes. Do not dispatch both
legacy and protobuf paths independently and double-record one message.
[Current commission narrative](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/commission-and-fees-report),
[current report fields](https://www.interactivebrokers.com/docs/tws-api/ref/commission-and-fees-report).

## Capture sequence and completion

Only after nextValidId readiness, select the sole managed account in memory and
assign a project alias such as PAPER_PRIMARY. Multiple accessible accounts are
unsupported for the first implementation: stop before issuing data queries.
AccountSummary group All is a group selector, not a way to select an arbitrary
account ID. Some requests expose all accessible accounts; the one-account
restriction prevents accidental collection across a linked account structure.
[Account-summary request semantics](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-summary/requesting-account-summary).

Every attempt starts a new connection/capture generation, unique request IDs and
an explicit total monotonic deadline. No unbounded retries. Fresh connection per
attempt prevents request-less end callbacks being attributed to a later capture.

| Component | Request and callbacks | Completion evidence and limits |
| --- | --- | --- |
| Positions | reqPositions; position | positionEnd marks initial enumeration, not all future updates. Keep observing until the capture closes; cancelPositions on cleanup. Explicit empty enumeration differs from no callback. |
| Account summary | reqAccountSummary with one bounded tag list; accountSummary | accountSummaryEnd matching request ID; all required tag/currency rows separately present and valid. End alone does not prove all fields exist or account state is current. Cancel subscription on cleanup. |
| Open orders | reqAllOpenOrders; openOrder and orderStatus | openOrderEnd on this generation. Enumeration is a one-time response, not an ongoing subscription. Empty means no orders observed in that response, not a guarantee that no later/external orders exist. |
| Executions | reqExecutions with account filter; execDetails | execDetailsEnd matching request ID. Store the exact filter and limited retrieval window. This is not complete lifetime trade history or terminal evidence for an absent order. |
| Commissions and fees | commissionAndFeesReport, correlated by execId | Each captured execution must have a valid matching report before fees are considered covered. There is no independent end marker here; execDetailsEnd must not be used as a fee-completion marker. Missing reports remain blockers at deadline. |

Verified sources on 2026-10-04:
[request positions](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/positions/request-positions),
[receive positions](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/positions/receive-positions),
[receive account summary](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-summary/receiving-account-summary),
[all submitted orders](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/requesting-currently-active-orders/all-submitted-orders),
[open-order callbacks](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/open-orders),
[request executions](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/request-execution-details),
[receive executions](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/receive-execution-details).

The current execution request page says current-day retrieval; the receive page
says last 24 hours. Record this documentation inconsistency. Treat retrieval as
a restricted broker-session window until pinned SDK/Gateway behavior has measured
evidence. Never infer that an older uncertain submission had no fill because this
enumeration is empty. No certainty is derived from a guessed timezone at midnight.

## Observation schema and privacy

Output is a new versioned schema with mode ibkr_paper_readonly_observations and
data_kind broker_observation. It is incompatible with SIM/synthetic inputs.
Persist only account aliases; account IDs are retained only in process memory for
filtering. Do not hash account IDs into an ostensibly anonymous identifier.

Store capture generation, SDK/server versions, operator attestations, request
parameters with account alias, start/end UTC, and per-callback receipt monotonic
offsets. A strictly increasing local receive index records observation order; it
is explicitly not a broker sequence, shared broker time or atomic snapshot cut.
Preserve broker execution timestamps with their stated timezone/uncertainty.

For values retain tag, currency, decimal string, component/request ID and receipt
time. Require finite bounded numbers; distinguish missing values and vendor unset
sentinels from numeric zero. Quantities may be fractional at capture time; flag
unsupported downstream scope rather than rounding them to whole shares.
Contract identity includes conId, security type, currency, multiplier and symbol;
a symbol string alone cannot certify SPY identity.

Order identity retains client/order/permanent IDs only within the local protected
report. Execution identities and their commission correlation remain local too.
Do not publish these reports or include them in Git, shared dashboards, build
archives or telemetry. Console output contains fixed status/counts only, never
balances, positions, IDs or raw SDK exceptions. Persist no free-text orderRef,
account names, rejection JSON, raw error text or arbitrary object representations.
SDK logs/stdout/stderr must be suppressed at the subprocess boundary; vendor
Gateway logs remain separately managed by the user.

Write under a dedicated ignored local directory, owner-only permissions where
supported, bounded file size, atomic create without overwrite, and no symlink
destination. A failed deadline produces only a sanitized status unless the user
explicitly requested a local partial observation report.

## Consistency and cash blockers

No combination of four end markers establishes an atomic account snapshot. The
result describes observations received over a bounded interval. Retain changes
arriving during collection, including position/account/order/execution updates.
Flag conflicting duplicates, changed quantities, orphan commissions, correction
executions, disconnects and request failures. Never overwrite a newer observation
with an older generation or silently merge inconsistent copies.

Initial implementation always reports trading_readiness blocked and
coherence not_certified. A useful capture may be complete for each requested
enumeration while still containing blockers. Future reconciliation must specify
how broker state, local journal, fills, fees and intervening updates are joined.
A quiet callback interval or two equal captures cannot prove atomicity, current
broker cash, no unobserved external activity, or known outcomes of uncertain orders.

Capture AccountType, NetLiquidation, TotalCashValue, SettledCash, AvailableFunds,
ExcessLiquidity and the selected USD ledger rows. The exact returned currency and
account segment are part of their meaning. Base-currency aggregate values must
not be relabeled USD spendable cash. Do not use BuyingPower or AvailableFunds as
cash for a cash-funded strategy; do not replace missing SettledCash with
TotalCashValue. Preserve negative values and flag unsupported borrowing.

Account-type labels may describe account structure rather than certify a cash vs
margin funding policy. SettledCash descriptions across current documentation are
not fully aligned: the reference states cash-account equivalence to TotalCashValue,
while the account window semantics describe settlement-dependent adjustments.
These observations alone do not establish settlement availability or cash-spending
authority. Leave cash_funding_policy unverified until account configuration,
USD/segment semantics, settlement constraints, pending-order reservations and
commission/dividend treatment are reviewed using the actual authorized account.
[Summary-tag reference](https://ibkrcampus.com/docs/tws-api/ref/account-summary-tags),
[account value keys](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-updates/account-value-keys),
[legacy SDK cash descriptions](https://interactivebrokers.github.io/tws-api/classIBApi_1_1EClient.html).
The last source is deprecated and is used only to identify the discrepancy, not
to choose a current settlement rule.

Unsupported positions, other currencies, outstanding orders, unknown external
activity, missing fees and any uncertain prior order remain visible blockers.
This capture does not import positions into quant_control, automatically adopt
manual trades, flatten a portfolio, reset a halt or authorize a strategy entry.

## Status vocabulary

- capture_complete: all requested enumeration markers arrived; report contains
  the requested observations and declared limitations. No readiness claim.
- capture_incomplete: missing marker, deadline, missing required rows, SDK failure
  or disconnect. Do not reinterpret missing responses as empty state.
- blocked: unsafe authorization/configuration/identity/privacy prerequisites.

Always include orders_enabled false, trading_readiness blocked and reason codes
covering consistency, visibility, history, cash semantics and unsupported scope.
Commission coverage is separately complete, incomplete or not_applicable for an
explicitly empty completed execution enumeration; it is never asserted as complete
history or evidence about old orders.

quant_session must reject this schema and mode. Real snapshots must never enter
the current synthetic SIM planner by changing labels. A future broker-observation
planner requires a new boundary, authorization policy and reconciliation contract.
Likewise quant_control must retain its synthetic broker_sequence/as_of assumptions;
local callback receive indexes must not be used to counterfeit those fields.

## Implementation sequence and acceptance evidence

1. Implement pure bounded callback records and validation, with synthetic tests
   only. Preserve Decimal values, IDs and explicit empty/completion distinction.
2. Implement a fake-transport capture owner and deadline cleanup. Allowlist request
   methods; fail any fake call to binding/order/modification/cancellation APIs.
3. Test pinned SDK callback/protobuf dispatch without opening a socket. Verify one
   normalized event per message and future/legacy callback mismatch rejection.
4. Review privacy output and domain isolation. Only then implement an opt-in runner
   and ask for specific authorization before actual paper account reads.

Minimum tests: missing/out-of-order/stale-generation end markers; empty enumerations;
changed position during capture; duplicate conflicting execution; execution correction;
late or missing commission; request error and timeout/disconnect cleanup; unsettled or
wrong-currency cash; fractional/foreign holdings; unknown orders; multiple accounts;
account ID or raw-error text cannot leak to console/report; order/binding APIs never
called; future collector output rejected by SIM planner/control; complete capture
still reports blocked trading readiness. Tests cannot contact a broker account.

Acceptance ends at a reviewed read-only observation tool. Account-level order
reconciliation, strategy scheduler, market-data entitlement, fees calibration,
paper order submission and all live execution remain separate milestones.
