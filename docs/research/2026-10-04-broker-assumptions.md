# Broker assumption review — 2026-10-04

Scope: public primary documentation reviewed for planning. No broker connection,
account inspection, subscription purchase, latency measurement, or trading occurred.
These are documented behaviors, not results observed against a configured account.

## Verified corrections

| Original proposal | Evidence and correction | Design consequence |
| --- | --- | --- |
| 2100 is a margin/regulatory warning | It reports account-data unsubscription. [IBKR error codes](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes) | Invalidate account freshness; block new exposure until updates are restored and reconciled. |
| 1100 severs a connection to a matching engine | It indicates TWS/Gateway lost connectivity to IB servers. 1101 restores connectivity with data lost; 1102 restores it with data maintained. [IBKR system messages](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/system-message-codes) | Reconcile after either recovery event. Resubscribe market data for 1101; do not blindly duplicate subscriptions for 1102. |
| A universal fixed 50-message limit, purchasable FIX equivalence | TWS request pacing is documented as market-data lines divided by two per second; 100 lines implies 50 requests/second. This is not a latency guarantee or protocol equivalence. [IBKR pacing](https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction) | Configure and validate the effective budget for the selected API, session and entitlements. Keep headroom and prioritize cancellation/recovery traffic. |
| Historical pacing applies identically to all requests | The cited limits concern bars of 30 seconds or less: identical requests within 15 seconds; six or more requests for the same contract/exchange/tick type within two seconds; more than 60 in ten minutes. BID_ASK requests count twice. [IBKR small-bar pacing](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less) | Use a request-class-aware rolling-window scheduler, weighted counts, caching and bounded backoff. Do not replace this with independent worker sleeps. |
| IBC/ib_async guarantees indefinite unattended authentication | IBKR documents daily restart settings and a weekly authentication cycle that can require manual login. [IBKR reauthentication](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication) | Remove seed extraction, push-loop workarounds and permanent-session assumptions. An operator login and recovery runbook is required. |

All five sources above were accessed on 2026-10-04. Recheck them before building a
broker adapter and record the actual TWS/Gateway/API versions used. Legacy message
tables and account-specific configuration can differ; unresolved differences block
the affected capability rather than silently choosing the most permissive value.

## Claims withdrawn from the implementation baseline

- NY4 location, direct cross-connect access, sub-millisecond order execution, 99%
  slippage reduction and five-nines system availability: not established for this
  account or deployment. Vendor advertising is not end-to-end execution evidence.
- Fixed monthly costs, quote-booster prices, minimum account equity and FIX minimum
  commissions: not verified here. Build a dated budget for the chosen instruments,
  account entity, professional/nonprofessional data status and trading volume before
  any purchase. Do not reuse the proposal's dollar amounts as a budget.
- Three depth subscriptions and 50 concurrent historical requests: do not adopt as
  universal limits without checking the applicable current request documentation
  and entitlements. Snapshot requests are not a free or unlimited screening path.
- C++/Rust, lock-free queues and colocation as prerequisites: deferred engineering
  choices. Measure event backlog, processing percentiles and recovery behavior before
  adding these components. Language choice does not establish determinism.
- Guaranteed 15–20% savings from Almgren–Chriss: no system-specific calibration or
  comparison exists. Begin with a transparent baseline and explicit cost scenarios.
- CPCV as an impenetrable firewall, automatic PBO output, or PBO < 5% as a sufficient
  deployment gate: withdrawn. Validation methods and thresholds need a separate
  research specification; no strategy has been statistically validated here.

## Remaining research gates

| Gate | Evidence required before dependent work |
| --- | --- |
| Data acquisition | Product, license, adjustment policy, timestamp semantics, coverage, delistings, corrections, cost and request-specific limits. |
| Paper connectivity | User authorization for account access, supported API versions, operator authentication, permissions, account identity and read-only checks. |
| Paper order submission | Separate explicit authorization, supported order behavior, fill-simulation limitations and completed recovery tests. |
| Live readiness | User-selected jurisdiction/entity/instruments; current primary-source review of applicable trading, margin, short-sale and reporting obligations; budget and loss limits. No legal applicability conclusion is made in this review. |
| Hosting | Measured gateway path and application latency, supported failover, recovery objectives, current pricing and explicit deployment authorization. |

None of these gates prevents offline work with synthetic data.
