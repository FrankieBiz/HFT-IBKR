# Local operating guide

## Supported environment

Python 3.11+ and a C++20 compiler. The reference build was verified on macOS with Python 3.14 and Apple clang. There are no Python runtime dependencies. Commands run from the repository root. Native code is compiled directly; no package manager or build-system download is required.

`make check` runs Python unit/CLI tests, builds native code with strict warnings, runs native tests/replay, compiles Python modules, and checks whitespace. `make demo RUN_DIR=artifacts/new-name` runs synthetic simulation. `make research RUN_DIR=artifacts/new-name` evaluates the generated dataset. The research registry defaults to `artifacts/research.sqlite` and intentionally accumulates attempted searches.

## A reproducible run

1. Keep each input CSV and its supplied metadata. Import records the raw CSV SHA-256, normalized UTC bars and a dataset ID incorporating metadata. The CSV, metadata, configuration and code revision together identify the experiment.
2. Use a unique output folder. The CLI refuses to replace prior result/report files, including symlinks. Artifact files are individually published atomically after rendering; completion of the command indicates the bundle is complete. Cross-file transactionality is not claimed.
3. Inspect `result.json` for state, halt reason, assumptions, fees, cost totals, inventory and valuation flags. The report is static local HTML, without external assets. Final inventory is marked at last close; it has not been liquidated.
4. Inspect `research.json` for selected parameters, train/test indices, undefined statistics, failed attempts, and campaign trial count. Never remove failed runs to improve a diagnostic. Rerunning a campaign suppresses DSR when comparable earlier-trial variance is unavailable.
5. Keep the dataset and registry SQLite files with the run artifacts. They are ignored by Git to avoid accidentally publishing market data or later account information. Use a filesystem copy only after CLI commands exit, or SQLite's backup API while a database is open.

Source and runtime hashes are recorded. Registry UUIDs and creation times differ across repeated runs; deterministic prices, decisions, fills and returns can still be compared. Synthetic data is a software fixture, not a market calibration dataset.

## Research commands

```sh
python3 -m quantlab research --database artifacts/first-run/history.sqlite --config examples/simulation.toml --candidates 3:12,5:20,10:40 --output artifacts/research-01 --registry artifacts/research.sqlite
python3 -m quantlab trials --registry artifacts/research.sqlite
python3 -m quantlab review TRIAL_ID --registry artifacts/research.sqlite --state reviewed --note "Inspected data provenance and offline holdouts"
```

Supply `--dataset ID` if a database contains multiple versions. Each trial is persisted before evaluation, including invalid candidate configurations. Human review is a local annotation; no review state triggers execution. The registry is append-only through its application API, not tamper-proof storage.

## Halts and recovery

Python simulation starts with an empty, reconciled synthetic account. Stale held marks, bad valuation, clock regression, marked exposure breaches, loss limits and price jumps halt execution. Halted simulation remains halted; rerun from the immutable dataset after diagnosing the cause. Do not change limits solely to erase an unfavorable result. Stale equity rows remain last-observed estimates and carry `valuation_valid=false`.

The native engine starts BOOT and requires a flat snapshot for initial bootstrap. Disconnect or queue overflow halts it. Recovery is explicit: begin recovery, compare cash/positions/open orders, then restart only after fresh marks and all risk checks. Pending orders keep cash/inventory reserved until filled or cancellation acknowledged. A late fill is accounted even when halted; a fill after cancellation acknowledgement forces reconciliation. Acknowledged cancellation is simulated, not proof that a broker canceled anything.

A driver must call `poll(now_ns)` even when no events arrive. Native time is monotonic replay nanoseconds. Its daily loss boundary is a 24-hour replay day starting at zero; Python uses UTC calendar dates. Neither implements a real exchange session calendar. The native core is not a durable account ledger and cannot adopt nonflat state on a fresh process. These are explicit integration requirements for the later broker phase.

## Local model workflow

`research-packet.md` is an export for manual use with a local model. No model is selected, installed, downloaded or contacted. Include only data you intend to share. Model output stays a research proposal: review generated code, track trials, test offline and review out-of-sample results. No model output enters the risk/execution modules dynamically.

## GitHub and containers

Changes are committed and pushed to `FrankieBiz/ridley`. The main branch is not merged automatically. The GitHub Actions definition is manual-only; it does not consume hosted runner time on pushes. It needs to exist on the default branch before normal workflow-dispatch use. Runner billing policy and automatic triggers remain an owner decision. No workflow was dispatched during setup.

`ops/Dockerfile` prepares a nonroot Python research image with no exposed ports. It has not been built or pulled. If explicitly authorized later, build from repository root with `docker build -f ops/Dockerfile -t quantlab-offline .`; the build requires obtaining its base image. Run only with `--network none`, an appropriate writable artifacts mount and a read-only root filesystem. The image contains the Python simulator, not the C++ compiler/core. No gateway or broker images are included.

Primary tool references checked 2026-10-03: [checkout action](https://github.com/actions/checkout), [Dockerfile reference](https://docs.docker.com/reference/dockerfile/), [sqlite3](https://docs.python.org/3/library/sqlite3.html). The workflow uses checkout v7 with credential persistence disabled and read-only repository permissions. Container and hosted-runner execution are not part of local verification.

## IBKR integration comes last

Before adding an adapter: verify current API/authentication/market-data rules and fees from primary broker sources, define instrument/tick/currency/session semantics, choose exact decimal accounting, persist order/event identity and recovery state, and replay broker event fixtures. Reconcile account state before enabling even paper submission. Connect only after explicit authorization for that broker action. Real-market data access, credentials, paid services, deployment and live orders remain outside this setup.
