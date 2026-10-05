# Pivot decision and delivery priorities

**Historical decision:** the daily-first sequencing below was superseded on
2026-10-05 by the [HFT research decision](2026-10-05-hft-research-decision.md)
and [research plan](../plans/hft-edge-research-plan.md). Preserve this record for
provenance; it is not the current research priority.

Decision date: 2026-10-04. **No complete rewrite. Change delivery priority toward
an integrated daily shadow/paper workflow.** The SPY 200-session trend rule remains
an unproven benchmark, not a selected profitable strategy. No intraday trade-count
target or AI trading authority is adopted.

Two independent reviews reached the same recommendation. Preserve causal signals,
Decimal sizing/costs, data bundles, chronological evaluation, experiment registry,
synthetic risk/recovery reference, dashboard and Gateway diagnostic. Existing
control snapshots use synthetic coherent broker sequences and exclude real fees;
do not rename SIM to a real account or assume those snapshots map directly to IBKR.

The previous product framing suggested a complete HFT/AI trader while the actual
deliverable was offline daily research. Correct that framing. More dashboard or
model features do not close the missing operational loop. A higher trade count
without evidence introduces turnover rather than a demonstrated advantage.

## Chosen build sequence

1. Connect dataset → completed-session signal → explicit synthetic quote/portfolio
   snapshot → cost-aware independent sizing/admission → durable shadow decision
   ledger. Rehearse buy/hold/sell/blocked cases end to end without network or orders.
2. Separately specify real IBKR read-only callback capture/normalization. Handle
   account ownership, settled cash, fees, positions, open orders, executions and
   asynchronous snapshot completion before any paper order adapter. Test offline
   callbacks first; request specific authorization before account reads.
3. Review licensed real price/dividend/calendar sources and calibrate execution
   assumptions. Freeze one baseline and at most one alternative before comparative
   evaluation. Run chronological validation and one frozen holdout, report net
   return, drawdown, turnover, exposure, trade frequency and regime stability.
4. Run prospective shadow decisions and compare estimated versus observed
   executable prices. Build and exercise paper order handling only after controls
   and evidence are reviewed and paper actions are specifically authorized.
5. Live review remains separate. Capital/loss limits, market permissions, measured
   broker latency, watchdogs and reconciliation drills need real evidence.

Optional Laya experiments and framework replacement are deferred from the critical
path. The existing official SDK diagnostic is sufficient for connection readiness;
no framework is presumed to solve account reconciliation or strategy profitability.

## Evidence and limitations

- [Time-Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum)
  motivates investigation of trend signals across diversified futures/forwards;
  it does not validate our single-SPY 200-session rule.
- [IBKR commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
  shows per-share charges and minimums with pricing-dependent external fees. Our
  fixture costs remain illustrative until actual account pricing is reviewed.
- [IBKR API market data](https://www.interactivebrokers.com/campus/trading-lessons/python-receiving-market-data/)
  documents off-platform entitlements and delayed data. A reachable socket is not
  evidence of current executable data or of a complete operational adapter.
- [Historical TRADES](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bar-what-to-show/trades)
  is split-adjusted, not dividend-adjusted; [ADJUSTED_LAST](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bar-what-to-show/adjusted-last)
  includes dividend/split adjustments. Neither can blindly enter the raw-plus-
  dividend accounting pipeline; avoid double counting and document normalization.
- [Small-bar pacing](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less)
  adds data-acquisition constraints for short intraday bars; it is not a prohibition
  on intraday trading or proof daily trading is more profitable.
- [FINRA Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
  describes a new intraday-margin framework effective 2026-06-04 with broker
  transition through 2027-10-20. Do not repeat a universal current $25k PDT claim;
  actual broker/account applicability requires a separate review.

These primary sources were checked on 2026-10-04. The recommendation is engineering
judgment. No real market dataset, broker account or trade was accessed for this
decision, and no return/latency/annual-trade-count forecast has been established.
