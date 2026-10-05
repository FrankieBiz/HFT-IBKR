# Broker and data feasibility

Dated 2026-10-05. Primary sources accessed 2026-10-04–05. Public-document review only: no account access, subscription purchase, connection, or order. Hardware and running paper Gateway are user reports, not measurements. Capital, budget, location, account entity, pricing plan, permissions and data status remain unknown.

**Decision / inference:** use this Windows/WSL2, RTX 3070 Ti 8 GB, 32 GB machine for bounded offline microstructure research and seconds-to-minutes intraday candidates. Start with minute-scale decisions on a small instrument universe; shorten the horizon only after measuring signal decay and the entire execution path. It is not presently a credible platform for competing in exchange-level latency arbitrage or queue-sensitive HFT. This is a feasibility judgment, not proof that every subsecond strategy is impossible or that slower strategies make money. A GPU can support model training; it cannot remove broker routing, network delay or missing order-book information.

## What IBKR actually provides

The following are documented facts unless explicitly identified as inference.

| Capability | Documented behavior and practical consequence |
| --- | --- |
| Streaming watchlist L1 | `reqMktData` uses time-based snapshots: US stocks/futures/bonds/indices 250 ms, US options 100 ms, forex 5 ms; Europe/Asia 250 ms. These are update intervals, not guaranteed delivery latency. They do not preserve every intervening book event. [Update frequency](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/top-of-book-l-1/market-data-update-frequency). |
| Tick-by-tick | `reqTickByTickData` provides Last, AllLast, BidAsk or MidPoint streams. Concurrent requests are limited to 5% of market-data lines; another request for the same instrument cannot be made within 15 seconds. That is subscription pacing, not a 15-second tick interval. [Request](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/request-tick-by-tick-data), [restrictions](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/introduction). |
| Depth | IBKR describes depth as unsampled/unfiltered, but does not guarantee every quoted price and explicitly excludes odd lots. SMART depth aggregates available exchanges. Thus the 250 ms L1 description must not be applied indiscriminately to depth. [Depth documentation](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/market-depth-l-2/introduction). |
| Subscription count | At 100 market-data lines, the published table gives five tick subscriptions and three depth subscriptions. Higher entitlements change limits; three is not universal. [Specialized lines](https://ibkrcampus.com/docs/general/market-data-subscriptions/market-data-lines/specialized-market-data-lines). |
| Request rate | TWS API allowance is market-data lines divided by two per second: 100 lines implies 50 requests/second. A streaming subscription counts when requested, not on each incoming update. This is **not a 50-tick/second incoming throughput ceiling**. IBKR also warns some orders above 50 requests/second may be queued. [Pacing](https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction). |
| Entitlements | API use is off-platform; free display data in TWS does not establish API rights. Subscriptions attach to usernames; paper access requires its own entitlement or supported sharing. [IBKR subscription explanation](https://www.interactivebrokers.com/campus/trading-lessons/python-receiving-market-data/), [third-party FAQ](https://ibkrcampus.com/docs/third-party-integrations/general-third-party-frequently-asked-questions). |

**Queue inference:** depth callbacks carry row position, side, price, size and exchange/market-maker identity, rather than exchange order IDs and priority IDs. Row position is not your order's queue rank. Neither SMART aggregation nor a trade stream establishes a complete venue-specific queue. Do not derive exact fills from these fields. [Callback schema](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/market-depth-l-2/receive-market-depth).

Historical Time & Sales currently covers up to three years. Requests specify at most 1,000 points, but responses may include extra ticks to finish a second; sessions require separate requests. This is not historical MBO reconstruction. [Coverage](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-time-sales/introduction), [request fields](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-time-sales/requesting-time-and-sales-data). Bars of 30 seconds or less older than six months and securities no longer trading are among documented omissions, introducing coverage/survivorship concerns. Small-bar requests have separate pacing rules. [Unavailable data](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/unavailable-historical-data), [small-bar pacing](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less).

High cancel/replace traffic also encounters IBKR's order-efficiency policy: its lesson describes a submissions/modifications/cancellations-to-executions ratio generally expected around 20 or less. This is distinct from per-second request pacing. `PendingCancel` explicitly allows an execution before cancellation confirmation. **Design implication:** reserve risk through cancel/fill races and prioritize cancellation/recovery traffic. [Order efficiency](https://ibkrcampus.com/campus/trading-lessons/python-complex-orders/), [status semantics](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/order-status/understanding-order-status-message).

## Paper fills are an operational test

IBKR simulates fills from the top of book without deep-book access; some order types are unsupported and complex orders are simulated. An exchange-directed market order's unfilled remainder can be rejected after a partial simulated execution. [Paper limitations](https://www.ibkrguides.com/brokerportal/aboutpapertradingaccounts.htm).

**Inference:** paper trading can test scheduling, order-state handling and recovery, but cannot validate queue priority, adverse selection, market impact or exchange-level profitability. For passive strategies, touching a limit price is insufficient fill evidence. Replay must insert orders after assumed arrival delay, model quantity ahead and partial fills, distinguish cancellation ahead from behind where possible, and retain orders until effective cancellation. Stress pessimistic fills and latency; report uncertainty rather than inventing precision from L1.

## What richer data changes

Nasdaq TotalView covers displayed orders **on Nasdaq**, including securities listed elsewhere; it is not the full US market. ITCH specifies order references and add, execute, cancel, delete and replace messages, with nanosecond timestamps. These enable venue-book reconstruction, not observation of all hidden liquidity or guaranteed hypothetical fills. [Product scope](https://www.nasdaq.com/products/data/equities/nasdaq-totalview), [ITCH specification](https://nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf).

CME MBO supplies individual anonymous orders across price levels, OrderID and PriorityID. CME distinguishes this from aggregated MBP, which cannot precisely establish individual queue position. Linking one's own order requires the relevant private order identity. [CME MBO FAQ](https://www.cmegroup.com/articles/faqs/market-by-order-mbo.html).

Databento is a candidate independent source for licensed historical L2/MBO research: its schemas distinguish MBO, top-ten aggregated depth, trades and bars. Venue coverage, historical start dates and license must be selected explicitly. Its exchange event timestamp and capture-server receive timestamp are different; neither is this desktop's receipt time. Preserve sequence, quality flags, corrections and snapshot boundaries. [Schemas](https://databento.com/stocks), [timestamp conventions](https://databento.com/docs/standards-and-conventions/common-fields-enums-types), [dataset/license selection](https://databento.com/docs/portal).

Costs depend on access and use. Nasdaq's **2026** schedule lists $15/month nonprofessional TotalView subscriber usage, but separately lists direct-access depth charges of $3,340/month per firm and non-display direct-access usage of $412/subscriber for 1–39 subscribers. These are distinct categories, not an all-in quote or a claim that all apply to this user. [Official fee schedule](https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf). Vendor historical estimates depend on dataset/date/schema/volume. Obtain a reviewed estimate before acquisition. [Databento pricing](https://databento.com/pricing/).

Market data access does not itself require becoming an exchange clearing member. Data licensing, execution sponsorship/clearing and physical connectivity are separate arrangements. CME offers distributor access and multiple connectivity choices; its GLink lowest-latency connection is available only at its colocation facility. Direct execution arrangements need clearing/session review. Colocation is a competitive infrastructure choice, not a universal requirement for research. [Licensed distributors](https://www.cmegroup.com/market-data/license-data/licensed-market-data-distributors.html), [connectivity](https://www.cmegroup.com/solutions/market-access/globex/connectivity-options.html), [iLink administration](https://www.cmegroup.com/tools-information/webhelp/cme-customer-center/Content/order-entry.html).

## Small-capital economics: illustrative arithmetic

IBKR's US-stock Pro entry tier is $0.0035/share with $0.35 minimum per order; Fixed is $0.005/share with $1 minimum. Tiered adds relevant third-party charges/rebates; Fixed has its own inclusions/exceptions. Verify actual account/route charges, sell-side fees and modification treatment. Do not assume Lite eligibility or zero total trading cost. [Current commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

**Assumptions, not forecasts:** $100 stock, whole shares, one buy and one sell, each crossing half of an unchanged $0.01 spread; zero additional slippage initially. Ignore commission caps because these examples do not reach them. Before additional fees and overhead:

`round-trip cost = buy commission + sell commission + shares × $0.01`

`break-even midprice move (bps) = 10,000 × cost / entry notional`

| Position | Tiered base round trip + spread | Break-even | Fixed base round trip + spread | Break-even |
| --- | --- | --- | --- | --- |
| 10 shares / $1,000 | $0.35 + $0.35 + $0.10 = $0.80 | 8 bps | $1 + $1 + $0.10 = $2.10 | 21 bps |
| 100 shares / $10,000 | $0.35 + $0.35 + $1 = $1.70 | 1.7 bps | $1 + $1 + $1 = $3 | 3 bps |

Add actual third-party charges, impact, slippage, financing/borrow where applicable, and allocated fixed expenses. An assumed $50 monthly data bill spread across 100 completed round trips adds $0.50/trip: another 5 bps on $1,000 or 0.5 bps on $10,000. This $50 is a sensitivity input, not a vendor quote. At an assumed $2,000 account balance, that bill alone is 2.5% of capital monthly. More turnover does not repair negative per-trade expectancy. Passive fills avoid mechanically crossing both spreads but introduce missed fills and adverse selection; rebates are not free profit.

## Settlement and account eligibility

Buying power must be modeled before estimating turnover. A funded cash-account
purchase may be sold the same day, but its sale proceeds are not immediately
settled cash for another rapid round trip. Different independently funded portions
of cash can support multiple trades; this is not a universal one-trade-per-day rule.
Ordinary US securities generally settle the next business day, using the applicable
calendar. [SEC cash-account bulletin, updated August 7, 2026](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9),
[SEC settlement FAQ](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq).

FINRA's replacement intraday margin standards became effective June 4, 2026 with a
broker transition ending October 20, 2027. IBKR warns that existing PDT rules may
still apply during transition. Do not assume either a universal $25,000 requirement
or its removal for this unknown account; verify entity, account type and adopted
regime. [FINRA Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10),
[IBKR transition notice](https://www.ibkrguides.com/complianceportal/supportpdtreset.htm).

For imbalance features, a BidAsk subscription with `ignoreSize=True` omits size-only
updates. Freeze `ignoreSize=False` for the proposed observation study and still
validate completeness; the flag does not make broker data exchange MBO.
[IBKR request fields](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/request-tick-by-tick-data).

## Conditions for a faster route

Aquilina, Budish and O'Neill's 2022 study found modal latency-arbitrage races lasting 5–10 microseconds in its 2015 London Stock Exchange sample. This is historical empirical evidence about competition, not a current IBKR latency measurement or universal HFT definition. [Primary paper](https://academic.oup.com/qje/article/137/1/493/6368348).

Advance only when:

1. Licensed venue-appropriate data supports a reproducible, time-aware holdout result after conservative costs, delayed arrival and queue assumptions; selection trials and uncertainty are disclosed.
2. Measured feed age, callback backlog, decision, acknowledgement and cancel-confirmation tails are comfortably shorter than the measured edge lifetime. No desktop or Gateway timing is inferred from GPU specifications.
3. A written budget covers data/non-display rights, storage, connectivity, execution/clearing and operations, with applicable account restrictions reviewed for the actual region and instruments.
4. Independent fail-closed controls, reconciliation and restart/cancel-race tests pass before separately authorized paper orders; live deployment requires separate evidence and authorization.

If expected returns disappear under these conditions, stop the candidate. Buying faster hardware, FIX access or colocation before establishing those dependencies does not establish an edge.
