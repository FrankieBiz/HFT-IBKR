# Offline operation and remaining delivery gates

Updated 2026-10-04. Supported local runtime: Python 3.11+ on macOS/Linux; evidence
was collected with Python 3.14.0 on macOS. The configured CI matrix has not been
executed remotely. There are no runtime dependencies beyond the standard library.

## Build and demonstrate

Run `make check build demo` from the repository root. The deterministic archive is
`dist/quant-system.pyz`; the demo prints its fresh artifact directory and writes
`summary.json` there. The demo runs the built archive outside the repository:

- Daily research with 1x/2x/5x cost stress and buy-and-hold comparison.
- Development/validation selection, frozen artifact, and separate holdout release.
- Repeated holdout rejection and byte-identical recovery of the stored report.
- A01–A14 synthetic control cases; A03 intentionally fails input validation.
- Byte-identical repeated control replay.
- Durable continuation and restart preserving uncertain reservations.

`python3 -m quant_research` and `python3 -m quant_control` expose the same commands.
Output paths must be new. A successful replay may contain risk rejections, open
positions or a halted final state. Exit 0 means the requested simulation ran; exit 2
means invalid input/storage/destination; exit 1 means an unexpected runtime failure.

## Durable control recovery

The control journal stores a complete explicit synthetic configuration and all input
events, including rejected and duplicate intents. Inputs are flushed/fsynced before
the reducer changes state or returns simulated outputs. On macOS the sync uses
`F_FULLFSYNC` (SQLite stores use `PRAGMA fullfsync`), because plain fsync there can
leave data in the drive cache; it falls back to fsync where unsupported. A failed write may already
have reached storage: never continue that runtime instance or assume its input was
not recorded. Close it, preserve the log, resolve the storage condition and validate
the entire journal before continuing. A truncated or corrupted record is an error;
the program never removes it or silently skips it.

`quant_control.journal.replay_journal(path, config)` reconstructs historical state
without restarting. Its outputs are historical simulated decisions, never traffic
to resend. `OfflineRuntime(path, config)` takes an exclusive lock and automatically
journals restart when reopening an existing log. It enters RECONCILING and retains
all unresolved orders. New intents require complete current-generation snapshot
evidence and explicit reset. A fill, account or order event during collection starts
a new generation but keeps the attempt's original reconciliation deadline, so a
continuously updating account ends in `RECONCILIATION_TIMEOUT` rather than
reconciling indefinitely. A consistent cut across real broker streams remains M4 work. A continuation fixture's first sequence is the prior
last sequence plus two (one for restart), with a nondecreasing relative clock.

Journal files must not be changed, moved or rotated while a writer holds them.
Keep the original immutable log and configuration when investigating errors; there
is no automatic destructive repair. M1 keeps events/executions in memory and its
log grows without rotation. It is suitable for bounded offline scenarios. Retention,
growth limits, backup drills and storage-failure operational recovery must be
implemented and exercised before a continuously running broker adapter.

## Experiment recovery

Use one durable SQLite registry for a study. Validation attempts reserve their IDs
before computation; completions/failures are separate append-only entries. Freeze
registration binds one selected artifact to the original stored completed report.
Changing the candidate and recomputing a checksum does not authorize holdout.
Holdout claims use a stable input identity rather than run/report metadata. Claims
are transactional and remain consumed after interruption, even if publication fails.

Completed validation and holdout payloads are stored with their hashes. Use
`quant_research recover --registry PATH --run-id ID --output NEW_PATH` to export a
stored result without recomputation. If a run remains reserved after interruption,
there may be no completed result to recover. Preserve that attempt in the registry;
do not delete/recreate the registry to make an interrupted holdout appear untouched.
Frozen selections are also retained in the registry's `frozen_selections` table.
This is a local audit mechanism, not protection against an operator changing files.

## Completed-results dashboard

`make demo` builds `dashboard.html` from its actual synthetic replay reports.
It supports keyboard cost selection and responsive layouts, keeps provenance
labels visible, and shows supplied synthetic control state snapshots. It has no
execution functions. Portable `view render` creates another snapshot; `view serve`
binds to loopback and serves only the page, never a report directory.

Do not interpret a control row's READY state as account readiness. A03's invalid
configuration is checked by the demo but intentionally emits no report, so the
default dashboard lists 13 state snapshots while the harness exercises 14 cases.
Source statements are declared; even historical data labels do not establish
independent verification or strategy profitability.

## Local ML environment diagnostic (preflight)

Run `python3 -m quant_local preflight --output PATH` or the archive's
`local preflight` command on the target workstation. PATH's parent must exist
and PATH must not exist. This reads local metadata and runs bounded diagnostics;
it installs nothing and downloads no checkpoints.

Report status `blocked` exits 2 and lists required checks that did not pass.
Inspect `evidence.cuda.error` for driver/wheel/probe errors. `--skip-cuda` always
leaves a blocker. Nvidia-smi indices are advisory; `--gpu-index` selects the
logical device visible to PyTorch, including CUDA visibility remapping.

Status `ready_for_model_benchmark` exits 0 and permits only the next hardware
experiment. It proves neither model inference nor dependency compatibility.
The memory budgets are project policy, not measured Laya requirements. WSL2's
guest memory may be lower than host RAM; this check measures the guest. A future
single-checkpoint benchmark must record load time, dtype, peak VRAM, headroom,
warm latency, fallback and crash behavior before H0 can be marked complete.

## Historical validation dependency

The offline intake implementation prepares a bounded deterministic bundle from
`--prices`, `--distributions`, `--calendar`, and `--metadata` local paths using
`python3 -m quant_data prepare --output NEW_BUNDLE` (supply all four input flags).
`quant_data inspect --bundle PATH --output NEW_REPORT` exports checked coverage
and provenance. The archive exposes these as `data prepare` and `data inspect`.
Research commands accept `--bundle PATH`; it cannot be mixed with data/manifest
paths. Only fixed stored/deflated ZIP members are supported, with no path extraction.
The [input contract](../superpowers/specs/2026-10-04-data-intake-design.md) requires
raw prices, explicit pay dates, exact sessions and source/license references.
These declarations still require provider review; a valid bundle is not that review.

The repository supplies invented data only. A reviewed historical interval needs:
raw unadjusted daily SPY OHLC/volume, cash distribution ex-dates and pay dates,
an independently reviewed exact trading calendar, source/retrieval/license evidence,
and no splits in that interval. The CSV/manifest contract is documented in README.
Checksums and internal validation cannot prove those declarations true.

Replace illustrative fees/spread/slippage/impact with dated, justified assumptions
and sensitivity bounds. Predeclare the protocol before inspecting holdout metrics.
Judge trend performance against the common-period benchmark and drawdown/capacity
constraints. Passing software checks or favorable synthetic returns is not evidence
of economic advantage. This remains M2 empirical work, even though replay and M3
evaluation software now exist.

## Broker integration dependency

No IBKR transport, SDK dependency, broker order-ID mapping, authentication or actual
order path exists in this build. M1's common synthetic snapshot sequence must not
be treated as something IBKR supplies. M4 needs its own adapter implementation and
current primary-source verification before relying on broker behavior.

The adapter must reconcile non-atomic position/order/execution/account streams,
map durable intent IDs to broker/permanent order IDs, handle commissions/corrections,
establish account/client visibility, pace requests, handle uncertain outbound writes,
resubscribe appropriately, and prove restart/cancel/fill behavior in an authorized
paper account. Whole-share cash funding also needs actual settlement-aware cash
and broker-specific commission reservations before admission can be reused.

Repository [AGENTS.md](../../AGENTS.md) and the
[quant skill](../../.agents/skills/quant-trading-system/SKILL.md) require specific
authorization before accessing accounts, sending orders, deploying or incurring
expenses. Development authorization does not by itself authorize those actions.
Paper validation, instrument-specific production limits and an explicit live
readiness review remain required before any actual live execution.
