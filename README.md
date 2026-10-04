# QuantLab — offline research and execution simulation

An executable implementation of the local portions of the [architecture proposal](docs/plans/optimize-quant-trading-system.md). Python runs data ingestion, research and portfolio simulation. C++20 supplies a separately tested execution core and synthetic replay. **There is no IBKR connection or live order path.**

## Start locally

Requires Python 3.11+ and a C++20 compiler (`clang++` on this Mac, or `g++`). Python commands use only the standard library; no package installation is necessary.

```sh
make check
python3 -m quantlab demo --output artifacts/first-run
python3 -m quantlab research --database artifacts/first-run/history.sqlite --config examples/simulation.toml --output artifacts/first-run/research --registry artifacts/research.sqlite
open artifacts/first-run/report.html
```

The demo generates **synthetic** DEMO bars with a fixed seed, imports an immutable SQLite dataset, simulates a moving-average strategy, and writes `result.json`, `report.html`, and `research-packet.md`. Reports have no external assets or scripts. Use a new output directory for every run; existing artifacts are never overwritten. `open` is macOS-specific; elsewhere open the HTML file in a browser.

Run `./native/build.sh` for the C++ tests and order replay. It demonstrates risk checks, AC slicing, rate limiting, partial fills, disconnect handling and explicit recovery. It is independent of the Python bar simulator. Both use synthetic assumptions; results do not establish profitability or operational readiness.

## Your own local CSV

Input columns must be exactly:

```csv
timestamp,symbol,open,high,low,close,volume
2026-01-02T14:30:00Z,DEMO,100,102,99,101,1000
```

Times denote **bar starts**, must include a timezone, and normalize to UTC. Rows must be unique and sorted by timestamp, then symbol. OHLC must be finite and positive; volume is a nonnegative integer. Supply provenance describing source, price adjustment policy, survivorship limitations and interval length. Gap counts include overnight gaps because no exchange calendar is assumed. See [example metadata](examples/provenance.json).

```sh
python3 -m quantlab import-csv /path/to/bars.csv --metadata /path/to/provenance.json --database artifacts/history.sqlite
python3 -m quantlab datasets --database artifacts/history.sqlite
python3 -m quantlab validate-config examples/simulation.toml
python3 -m quantlab backtest --database artifacts/history.sqlite --dataset DATASET_ID --config examples/simulation.toml --output artifacts/my-run
```

Edit a copy of the config for symbols/sectors and cost assumptions. Missing sector classifications fail closed. Price data must match the declared interval. All costs are **illustrative and uncalibrated**, not broker fee estimates.

## Behavior and limits

Signals use completed bars. Fills use an entire subsequent bar, are booked at its end, and use its close plus half spread, slippage and square-root participation impact. Volume caps allow partial fills; unused quantities expire at that attempt. This approximates bar execution and makes no claim about opening fills, queue priority or intrabar paths.

The Python simulator supports integer, long-only cash equity positions in one currency. It enforces order size, symbol/gross/net/sector exposure, stale marks, price jumps, daily loss, drawdown and cash limits. Simultaneous symbols allocate in alphabetic order. Halts cancel simulated pending intentions and preserve inventory for inspection. Missing/stale held marks halt the run and flag valuation quality. End inventory stays marked; no automatic liquidation is implied.

The research command compares parameter candidates using training-only selection and separate holdout portfolios. It records attempted, completed and failed trials in SQLite. Statistical diagnostics may be undefined; undefined means insufficient evidence, never a pass. Local review status never enables trading. Research is currently single-symbol. See [methods and limitations](docs/implementation/research-methods.md).

Native and Python components have distinct execution models. The C++ core uses synthetic limit fills with floating-point accounting and in-memory state. It is not a broker accounting engine and makes no latency guarantees. See [native contracts](native/README.md).

## Project map

| Location | Purpose |
|---|---|
| `quantlab/data.py` | Strict CSV ingestion, provenance, immutable dataset versions |
| `quantlab/config.py`, `risk.py`, `simulation.py` | Offline cost model, risk checks and portfolio accounting |
| `quantlab/strategy.py` | Example strategy and strategy protocol |
| `quantlab/research/` | Labels, purged validation, statistical diagnostics, registry and evaluation |
| `quantlab/reporting.py`, `cli.py` | Reproducible artifacts and local commands |
| `native/` | C++20 queue, lifecycle/risk engine, scheduler, limiter, replay and tests |
| `tests/` | Python unit and command workflow tests |
| `docs/implementation/` | Design, methods, operations and plan coverage |
| `.github/workflows/offline-checks.yml` | Manual CI definition; no automatic hosted runs |
| `ops/Dockerfile` | Optional unbuilt research container definition |

See the [operating guide](docs/implementation/operations.md) and [plan coverage](docs/implementation/coverage.md) for what is implemented and what remains before IBKR integration.
