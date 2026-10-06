# Windows + WSL operator runbook

Current direction, 2026-10-06: a bounded daily SPY trend overlay with enforced
historical readiness, persistent entry halts and independently checkable health.
[SETUP.md](../../SETUP.md) is the short guide; [README](../../README.md) explains the
strategy and limitations. This workflow never sends broker orders.

## Local environment

Use WSL/Ubuntu with Python 3.11+ and keep the checkout under the Linux home directory.
Install git, make, Python, tzdata, CA certificates and curl. From the checkout:

```sh
make check build demo
```

This uses local synthetic fixtures. No data keys, broker account or model is
required. Build output is `dist/quant-system.pyz`; the synthetic report directory
contains a dashboard, research/evaluation/robustness reports and control rehearsals.

## Study before operations

The current protocol is [spy-trend-v2](../../studies/spy-trend-v2/PROTOCOL.md), not
v1. Its 25% entry target/30% entry cap/10% drawdown entry halt are research defaults,
not guaranteed losses or a personal capital recommendation. V1 remains unchanged.

Review provider entitlement and terms, then save your own Alpaca paper-data keys
in `~/.config/alpaca/paper.env` outside the checkout. Use directory mode 700 and
file mode 600. The file has `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` assignments.
Never share keys in chat, commits or command lines. Dataset outputs stay under
ignored `.research-output/` and must not be redistributed contrary to provider terms.

When you choose to authorize the study's data fetch:

```sh
./scripts/run_study.sh
```

The command records v2 data, validation, robustness diagnostics and the final
holdout/verdict under `.research-output/spy-trend-v2/`. It uses the original shared
`.research-output/spy-daily-v1/experiments.sqlite` registry and unique v2 run IDs.
A genuinely empty legacy study folder can initialize the registry offline. Missing
audit history beside legacy artifacts or old unclaimed holdout releases require
reviewed recovery/migration, never a replacement registry.

If v1 already released v2's proposed historical final sessions, v2 release fails.
Keep all artifacts and freeze a separate protocol on fresh future dates. Do not
rename studies, labels or registries to treat released data as untouched. Code or
config changes also invalidate evidence, without reopening a consumed holdout.
A changed protocol may be evaluated using the explicit CLI commands in the
[component reference](../reference/components.md), keeping the shared registry.

Qualifying historical screening requires a nonnegative 2x-cost trend return and
lower drawdown than matched buy-and-hold. Lower return with lower drawdown qualifies
only as a risk-control overlay. Diagnostics cannot rescue a rejected result.
The readiness gate authenticates the actual bundle/config/protocol/code, freeze,
validation and holdout against original registry payloads; files alone are not enough.

## Manual shadow book

```sh
mkdir -p .research-output/shadow
cp examples/shadow/portfolio.template.json .research-output/shadow/portfolio.json
```

Set cash, settled cash, shares and peak NAV for the modeled strategy account. The
example balance is a fixture. After a modeled BUY/SELL, update the book explicitly.
There is no broker reconciliation or fill accounting. Unpaid dividends/other assets
are not represented in the shadow NAV. External deposits/withdrawals need an
accounting review rather than simply changing cash and resetting the peak.

The ledger keeps observed peaks and latched drawdown entry halts. Restart, recovery
or lowering the declared peak cannot clear a breach. A manual `halted: true` blocks
all proposals, while valid marks continue to record losses. Signal-driven sells
remain eligible after a drawdown halt, subject to order/capacity checks. A halt
neither guarantees cancellation nor liquidation. Legacy ledgers lacking risk memory
block new sessions pending reviewed migration; retain their history.

## Daily operator workflow

```sh
./scripts/run_daily.sh --check
./scripts/run_daily.sh
```

Both fail before keys/services if study evidence is missing, stale for the code,
corrupt or rejected. `--check` performs external calendar/notification setup checks
only after readiness. The runner never starts a study implicitly. `CONFIG=...`
must equal the frozen base config with exactly the selected lookback substituted;
it cannot bypass the gate.

Keep Windows awake and the Ubuntu terminal open. Minimize it; do not close it.
The runner waits for the actual calendar session, normally records at 09:31 New
York and handles holidays/early closes/DST. `--once` handles today; Ctrl-C stops.
A single session can also be invoked with `./scripts/daily_shadow.sh` after the open.

The daily script validates fresh data independently of immutable study evidence.
Cached reports are displayed only if they match integrity-verified ledger bytes
and the current planning config/source. New sessions are chronological; retries
with identical inputs recover bytes, while changed inputs conflict.

## Notifications and independent health

Optional ntfy status delivery requires a private `NTFY_TOPIC` configured in
`~/.config/hft-ibkr/notify.env`; review provider use before enabling. Treat topic
names as private because knowledge of a public-server topic can permit reading it.
Status also goes to `.research-output/shadow/run.log`.

The runner writes `.research-output/shadow/heartbeat.json` about every 30 seconds
while waiting, retaining daily decision deadlines across restarts. Independently run:

```sh
python3 scripts/check_shadow_health.py \
  --heartbeat .research-output/shadow/heartbeat.json \
  --ledger .research-output/shadow/ledger.sqlite
```

Exit 0 means its declared freshness/deadline checks passed. Exit 2 reports missing,
stale, future, failed/stopped heartbeat or an absent/corrupt due decision. Optional
`--session YYYY-MM-DD --deadline UTC_TIMESTAMP` declares an explicit expectation;
`--max-age-seconds 120` is the default freshness limit. A valid BLOCKED decision
counts as a recorded decision, not a trade or economic success.

Use a separate scheduler and alert path to detect a stopped process. This project
does not install a scheduler, remote watchdog or monitoring service. A running
heartbeat alone is not proof that a daily decision arrived or the strategy works.

## Failure and recovery

| Failure | Response |
| --- | --- |
| Evidence/readiness error | Preserve records; compare source/config/protocol and mechanical verdict. No override to force progression. |
| Already released holdout | Keep registry; separately freeze fresh future final dates. |
| Legacy risk ledger | Retain history and review migration; do not delete/reset it. |
| Intake coverage/dividend/calendar error | Stop and review provider data and declared policies. |
| Stale/future quote | Check network and WSL clock; invalid marks cannot alter observed risk memory. |
| Conflicting/corrupt decision | Stop and retain inputs/ledger for investigation. |
| Missing heartbeat/decision | Check PC sleep, process, inputs and log from the independent monitor. |
| Output publication failed | Retry identical inputs to a fresh output path; committed decisions remain frozen. |

Update code locally and rerun `make check build demo`. Research-source changes
require evidence requalification; passing tests alone does not qualify old results.

## Separate broker tools

No IB Gateway is needed for the daily overlay. The existing
[paper Gateway handshake diagnostic](paper-gateway-setup.md) is optional, explicitly
invoked setup tooling and separate from these workflows. It is not a paper-order
adapter. Account reads, paper orders, deployment and live execution require their
own scope, readiness evidence and explicit authorization.
