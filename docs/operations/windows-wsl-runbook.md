# Windows + WSL operator runbook

Current direction, 2026-10-06: a bounded daily SPY trend overlay with enforced
historical readiness, persistent entry halts and independently checkable health.
[SETUP.md](../../SETUP.md) is the short guide; [README](../../README.md) explains the
strategy and limitations. This workflow never sends broker orders.

## Update and open the app

For your existing `~/HFT-IBKR` checkout, stop any terminal runner with Ctrl-C and
run these commands in Ubuntu:

```sh
cd ~/HFT-IBKR
git pull --ff-only origin FrankieBiz/compare-built-system-to
./scripts/run_app.sh
```

The launcher opens the Windows browser through `cmd.exe` at
**http://localhost:8765**; enter the address yourself if it does not open. The
backend binds only to `127.0.0.1`. For subsequent starts, optionally copy
`Start-Trading-App.cmd` to the Windows desktop. It runs the checkout in the default
WSL distribution at `~/HFT-IBKR`; it does not install WSL, Python or the repository.

Keep the app's launch window open. Ctrl-C stops its backend and owned jobs;
closing the browser leaves them running. Overview's **Start runner** and **Stop**
control app-owned jobs. A runner already owned by a separate Ubuntu terminal is
shown as external; stop it with Ctrl-C in that terminal. The shared ownership lock
prevents duplicate app/terminal runners. Opening the app starts no jobs or downloads.

Keep existing keys, completed study evidence, `.research-output/`, the shared
registry, portfolio and ledgers. Updating or opening the app never requires
rerunning a completed study. The recent-SIP request-window correction below still
applies to your existing study and declared feed.

## App workflow

Use **Overview** for readiness, runner status, heartbeat and the latest proposal.
**Setup** detects existing files; complete only missing steps. **Decisions** shows
integrity-verified proposal history and details. **Portfolio** shows declared
simulated holdings and dated NAV marks. **Activity** shows bounded job output and
safe errors. Refreshing reads local files only; it does not poll a data provider.

Keys remain blank in Setup. **Save keys locally** explicitly writes your input to
`~/.config/alpaca/paper.env` outside the checkout with private permissions; existing
values are never displayed. Starting cash can initialize only a fresh book without
existing portfolio or decision/fill history. The app does not replace audit history
or clear halts to make Setup pass.

**Download data & run study** requires an explicit click and confirmation before
provider downloads. Completed qualified evidence is reused; rejected/corrupt
evidence remains available for review. **Check data connection** runs the existing
readiness-gated calendar/notification check; **Start runner** uses the existing
readiness-gated daily workflow. These actions may contact configured services.
Stop active jobs before changing keys or the book.

For a simulated fill, stop the runner and open Portfolio. Only the full latest
verified BUY/SELL can be recorded, exactly once. Declare a positive fill price and
nonnegative fees. The session snapshot must match current cash, settled cash,
shares and manual halt state; a mismatch blocks accounting. The app journals the
before/after book durably and recovers only an expected state after interruption.
Use **Recover pending accounting** for an interrupted fill; it restores an expected
journal state without declaring settlement or changing a halt. Retain the journal
and portfolio if it reports divergence; do not repair by deleting history.
Pending/corrupt fill journals also block terminal runners before readiness or
network calls. Decisions alone never change holdings.

Buys consume settled cash. Sells add unsettled cash; **Confirm cash settled** is an
explicit manual declaration, with no automatic settlement timing. Partial fills,
external deposits and withdrawals are unsupported. Recorded NAV is simulated and
dated, not a live account balance or P&L. **Halt all proposals** sets the manual
global halt, blocking all proposals;
ledger drawdown entry halts block buys while permitting eligible signal exits.
Neither halt is cleared by the app, settlement, recovery or restart.

## Local environment

Use WSL/Ubuntu with Python 3.11+ and keep the checkout under the Linux home directory.
Ubuntu 24.04 provides a suitable Python. First-time WSL and package installation is
in [SETUP.md](../../SETUP.md). Install git, make, Python, tzdata, CA certificates and
curl. The runtime uses the standard library and bundled assets, with no npm install
or CDN. This is not a native Windows installer. From the checkout:

```sh
make check build demo
```

This uses local synthetic fixtures. No data keys, broker account or model is
required. Build output is `dist/quant-system.pyz`; the synthetic report directory
contains a dashboard, research/evaluation/robustness reports and control rehearsals.

Intake now defaults explicitly to IEX for both daily bars and sampled minute bars.
It records the feed in source metadata and the cross-check report. IEX is a single
exchange, so volume and prices do not represent consolidated SIP/official auctions.
The strict quality checks remain active. Update the branch and retry a failed fetch
if an older version reports a SIP subscription 403; keep registry/history intact.
Standalone `fetch-alpaca --feed sip` remains available for permitted SIP access,
without automatic fallback or relabeling of cached inputs.
Operational history retains the feed declared in the authenticated study bundle.
Existing SIP studies continue to fetch SIP; cached and newly prepared daily bundles
are checked for feed equality before decisions. Unknown/ambiguous feeds block.

For a recent-SIP 403 after historical readiness passed, update and restart the
runner without rerunning the completed study. Intake uses explicit UTC timestamps
from New York session dates, excludes the next session's midnight label and caps
the end at least 16 minutes behind the captured clock. It checks the final calendar
close before requesting bars; incomplete/unavailable sessions fail rather than
publishing partial daily data. Pagination retains the same bound. Error context
includes only validated feed/timeframe/date fields, excluding keys and page tokens.

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

## Manual shadow book (CLI alternative)

```sh
mkdir -p .research-output/shadow
test -f .research-output/shadow/portfolio.json || cp examples/shadow/portfolio.template.json .research-output/shadow/portfolio.json
```

Set cash, settled cash, shares and peak NAV for the modeled strategy account. The
example balance is a fixture. The CLI-only book requires explicit JSON updates
after a modeled BUY/SELL and has no fill journal. The app adds the separate manual
simulated-fill journal described above; use those controls for an app-journaled
book, since direct JSON edits can block accounting recovery. Neither workflow
reconciles with a broker. Unpaid dividends/other assets are not represented in the
shadow NAV. External deposits/withdrawals are unsupported in the app; do not simply
change cash or reset the peak.

The ledger keeps observed peaks and latched drawdown entry halts. Restart, recovery
or lowering the declared peak cannot clear a breach. A manual `halted: true` blocks
all proposals, while valid marks continue to record losses. Signal-driven sells
remain eligible after a drawdown halt, subject to order/capacity checks. A halt
neither guarantees cancellation nor liquidation. Legacy ledgers lacking risk memory
block new sessions pending reviewed migration; retain their history.

## Daily operator workflow (CLI alternative)

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
| App port occupied | Reuse the existing app or stop its launch terminal; alternatively launch with `./scripts/run_app.sh --port 8766` and use `http://localhost:8766`. |
| External runner active | Stop the runner in its owning terminal before app Start or book changes. |
| Fill snapshot/journal mismatch | Preserve portfolio, snapshot and accounting journal; review divergence before further changes. |
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
