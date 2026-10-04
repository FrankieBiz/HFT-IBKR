# Architecture proposal coverage

Status: local implementation prepared 2026-10-03–04. The original proposal is preserved as requirements context, not verified broker, legal or financial guidance. This map distinguishes executable local components from integration and empirical work.

| Proposal section | Implemented locally | Remaining work |
|---|---|---|
| 1. Strategy/research separation | Strategy protocol, illustrative MA baseline, reproducible evaluation | A real hypothesis, suitable market dataset, capacity and economic evidence |
| 2. Infrastructure | Direct native build, local CLI, optional Python container definition, manual CI definition | No VPS, colocation, HA, latency measurement or deployment; requires authorization and evidence |
| 3. Data and API throughput | Validated CSV, immutable SQLite cache, provenance, gaps, native configurable token bucket | Broker-specific pacing, snapshot subscriptions, live data ranking/promotion and vendor limits deferred to adapter design |
| 4. Authentication/gateway | Broker absence enforced structurally; simulation is only configurable mode | IBKR/IBC/Gateway, credentials, 2FA and sessions intentionally untouched |
| 5. Native event engine | C++20 SPSC queue, strict native build, risk/order state machine and deterministic replay | No Python/native in-process bridge, socket adapter, durable native ledger or latency guarantee |
| 6. Execution/costs | Stable continuous linear-impact AC/TWAP scheduler; synthetic limit/partial fills; Python spread/fees/slippage/participation impact | Empirical impact calibration, discrete/permanent-impact AC extensions, queue/venue behavior, production currency precision |
| 7. Research validation | Close-barrier labels, interval purging/embargo, CPCV folds and prediction-path reconstruction, walk-forward candidate selection, PSR/DSR, separate CSCV PBO, trial registry | Pipeline uses walk-forward; it does not claim fitted CPCV portfolio paths. Real datasets, dependent-return inference and independent holdout review remain |
| 8. AI research layer | Research packet export and persistent manual review notes; no dynamic model execution in trading code | Local model choice/download/runtime wiring requires separate authorized setup |
| 9. Risk/operations | Python order/cash/symbol/gross/net/sector/loss/stale-data/jump controls; native reservations, duplicates, partial fills, cancel acknowledgements, timeouts, daily loss, drawdown, queue-overflow halt, reconciliation | Cross-process persistence, broker truth reconciliation, account margin/multicurrency, automated monitoring/alert transport and real session calendars |

## Boundaries

The Python simulator and native engine are **separate execution models**. The Python path uses subsequent-bar close execution plus costs; native replay uses explicit synthetic limit fills. The native queue, scheduler and limiter are integrated in its replay example; they are not claimed to handle real broker events. Native accounting is floating point and initially bootstraps only a flat account. Recovery inside one running process is tested; fresh-process restoration is not implemented.

Historical data versions and research trials persist in SQLite. Simulation artifacts preserve events, configuration, fills and valuations for inspection. They are not a production transaction journal. Price adjustments, delisted universes, borrow/margin, corporate actions, tick/lot rules and exchange sessions require additional explicit modeling before real-data conclusions.

The strategy is an example. No profitability, statistical proof, guaranteed slippage reduction, authentication autonomy or production readiness is asserted. No funded service, model download, infrastructure deployment, broker connection or live/paper broker order was performed.

## Local acceptance checks

- CSV/metadata rejection and atomic versioned import.
- Subsequent-bar causality, costs/cash accounting, partial volume fills and deterministic multi-symbol allocation.
- Exposure, stale valuations, price jumps, loss halts and recovery-limit regression cases.
- Native threaded FIFO, overflow halt, stable schedule conservation, message limiter, duplicate events, partial fills, cancel/late-fill races and reconciliation.
- Purging boundaries, CPCV path coverage, failed-trial accounting, forward-only parameter selection and future-data perturbation.
- CLI simulation/research workflows, repeat-seed reproducibility, JSON/HTML output, overwrite and symlink protection.
- `make check` is the authoritative local command. GitHub hosted CI and container builds are defined but have not been executed.

## Next integration order

1. Supply a local real-data sample and document provenance/adjustments/sessions; calibrate costs and extend instrument accounting.
2. Select the final execution path and implement durable account/order journaling, restart recovery and Python/native integration fixtures.
3. Select/install a local research model only if desired and authorized.
4. Verify and implement IBKR's current paper adapter with explicit account access authorization and offline event fixtures.
5. Evaluate deployment and monitoring only after real workloads are measured; live execution requires separate approval.
