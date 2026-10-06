# Setup guide

The current project is a bounded daily SPY research/shadow overlay. It never sends
orders. Set it up locally first; daily operator scripts require approved historical
evidence that matches the revised settings. [README](README.md) explains the policy.

## Existing Windows/WSL installation: launch the app

If your keys and study are already set up, reuse them. Stop a runner in its existing
terminal with Ctrl-C, then run this in Ubuntu:

```sh
cd ~/HFT-IBKR
git pull --ff-only origin FrankieBiz/compare-built-system-to
./scripts/run_app.sh
```

The app opens in your Windows browser at **http://localhost:8765**. If the browser
does not open, enter that address yourself. The service binds only to `127.0.0.1`.
Keep the launch terminal open; Ctrl-C stops the backend and its owned jobs. Closing
the browser leaves them running. Optional: copy `Start-Trading-App.cmd` from the
checkout to your Windows desktop. Double-click it for future starts; it expects
`~/HFT-IBKR` in your default WSL distribution.

Retain `.research-output/`, the shared study registry, portfolio and decision/fill
ledgers. **Do not rerun your completed study or re-enter existing keys to use the
app.** The recent-SIP request-window repair is retained; see step 3 if needed.
If local source edits prevent the fast-forward pull, preserve them before updating.

## Use the app

| Tab | What to do |
| --- | --- |
| Overview | Review readiness, heartbeat and latest verified proposal. Start runner explicitly; Stop stops the current app-owned job. |
| Setup | Complete only missing steps; existing files are reused. |
| Decisions | Inspect verified BUY/SELL/HOLD/BLOCKED proposals and recorded inputs. |
| Portfolio | Inspect declared simulated holdings and dated NAV marks; record an explicit simulated fill or confirm settlement. |
| Activity | Read recent job progress and safe failure details. |

Setup key fields stay blank; **Save keys locally** writes only on your action to
`~/.config/alpaca/paper.env`, outside Git, with restrictive permissions. Existing
key values are never displayed. **Create simulated book** accepts starting cash
only for a fresh book with no existing decision/fill history; it cannot replace a
portfolio. **Download data & run study** contacts the provider only after you click
and confirm it. A completed qualified study is reused. **Check data connection**
and **Start runner** also contact configured services after readiness checks.
Opening or refreshing the app only reads local state and starts none of these jobs.

The runner records proposals, not fills. In Portfolio, record only the full latest
verified BUY/SELL with your declared positive fill price and nonnegative fees. The
app verifies the session snapshot against the current cash, settled cash, shares
and halt state, journals the fill exactly once and rejects duplicates or mismatches.
If an interrupted fill is pending, use **Recover pending accounting** to complete its
journal recovery without declaring settlement or changing a halt. Unexpected book
divergence blocks recovery; retain the files for review. Pending/corrupt fill
journals also block terminal runners before readiness or network calls.
Buys spend settled cash; sells add unsettled proceeds. Use **Confirm cash settled**
only when your simulated settlement assumption is satisfied; there is no automatic
settlement clock. Deposits, withdrawals and partial fills are unsupported.

**Halt all proposals** sets the manual global halt and blocks all proposals. The ledger's separate drawdown entry
latch blocks new buys while permitting eligible signal exits. The app preserves
both and offers no halt reset. Neither means the account is flat. Stop app-owned
jobs before book/key changes; a runner owned by another terminal must be stopped
there. The NAV chart shows recorded simulated marks, not broker balances or live P&L.

## 1. First installation and offline verification

Use Python 3.11+ on macOS, Linux or Windows with WSL/Ubuntu. This is a browser app
backed by a POSIX Python service, not a native Windows installer. It uses bundled
HTML/CSS/JavaScript and the standard library; no npm or CDN dependency is needed.
On WSL keep the checkout in the Linux home directory rather than `/mnt/c`.

If WSL is not installed, run this in **PowerShell as Administrator**, restart if
prompted, then open Ubuntu and complete its username/password setup:

```powershell
wsl --install -d Ubuntu-24.04
```

In Ubuntu:

```sh
sudo apt update
sudo apt install -y git make python3 tzdata ca-certificates curl nano
python3 --version
```

For a new installation, clone the published revision:

```sh
git clone --branch FrankieBiz/compare-built-system-to https://github.com/FrankieBiz/HFT-IBKR.git ~/HFT-IBKR
cd ~/HFT-IBKR
```

If you already have this repository on the computer, update that checkout instead.
Retain `.research-output/`, including study registries and shadow ledgers; do not
replace it with an empty folder to bypass previously consumed holdouts or halts.
Commit or otherwise preserve local source edits before switching branches:

```sh
cd ~/HFT-IBKR
git fetch origin
git switch FrankieBiz/compare-built-system-to
git pull --ff-only origin FrankieBiz/compare-built-system-to
```

Then verify the checkout:

```sh
make check build demo
```

Tests should finish with `OK`; the synthetic demo should report
`offline_workflows_passed`. No data keys, broker login or network access are needed
for these checks. The portable application is `dist/quant-system.pyz`. Then launch
`./scripts/run_app.sh` and follow the app workflow above.

## 2. Understand the study gate

The default is [spy-trend-v2](studies/spy-trend-v2/PROTOCOL.md): a 25% entry target,
30% entry exposure cap and 10% persistent drawdown halt on new buys. The original
study is retained, but its different settings cannot qualify this version.

The study shares `.research-output/spy-daily-v1/experiments.sqlite`. If v1 already
released the final sessions, v2 cannot release them again. Stop and define a study
on fresh future dates; retain the registry and old reports. Missing, rejected or
changed-code evidence also blocks the daily workflow. This is intentional.

## 3. Configure data access only when you choose to run a study

The intake defaults to IEX daily/minute bars, with Alpaca dividends/calendar and an
IEX quote for shadow pricing. IEX covers one exchange; its prices and volume are
not consolidated market data. The strict calendar/dividend/minute checks remain
enabled. Operational downloads retain the authenticated study's declared price
feed; upgrading cannot silently change an existing SIP study to IEX. Cached daily
bundles must match that feed before a decision can be displayed or planned.
Review current provider terms and your entitlement before use.
Save your own paper-data keys in `~/.config/alpaca/paper.env`, outside the repo:

```sh
mkdir -p ~/.config/alpaca
chmod 700 ~/.config/alpaca
touch ~/.config/alpaca/paper.env
chmod 600 ~/.config/alpaca/paper.env
nano ~/.config/alpaca/paper.env
```

```text
APCA_API_KEY_ID=your-key-id
APCA_API_SECRET_KEY=your-secret
```

In nano, save with Ctrl-O, Enter and exit with Ctrl-X. Never paste keys into chats,
commits or command lines. No IB Gateway is needed for this workflow.

Run the explicit study command when you authorize fetching its inputs:

```sh
./scripts/run_study.sh
```

If an older checkout reports HTTP 403 with "subscription does not permit querying
recent SIP data", update the published branch using step 1 and rerun this command.
The updated default requests IEX explicitly. Preserve existing artifacts and the
registry; a failed fetch publishes no intake directory. Never relabel previously
downloaded SIP data as IEX or delete released study history to rerun a holdout.
An existing qualified SIP study continues to request SIP; a new feed requires
reviewed evidence rather than relabeling or resetting consumed holdouts.
If the completed study passes readiness but the daily runner reports **recent SIP
data** HTTP 403, stop the runner with Ctrl-C, update the branch and restart it.
The corrected daily intake uses explicit UTC bounds, excludes the following
session, and caps requests at least 16 minutes before its clock. It requires the
final requested session to have closed before that cutoff. **Do not rerun the
completed study or remove its registry for this repair.** Errors now show only
safe feed/timeframe/date bounds alongside the endpoint; keys and page tokens are
excluded from request context.
For a separately authorized standalone SIP download, `quant_data fetch-alpaca`
accepts `--feed sip`; it never falls back to another feed after an access failure.

It preserves finished steps, records diagnostics and applies the mechanical verdict.
A successful command alone does not mean the verdict permits shadowing. The daily
runner independently authenticates the records and enforces that verdict.

## 4. Prepare the manual shadow book (CLI alternative)

```sh
mkdir -p .research-output/shadow
test -f .research-output/shadow/portfolio.json || cp examples/shadow/portfolio.template.json .research-output/shadow/portfolio.json
nano .research-output/shadow/portfolio.json
```

Set `cash`, `settled_cash` and `peak_nav` to your **modeled strategy account** value;
leave `shares` at zero initially. The example capital is not an allocation
recommendation. For a CLI-only book, edit shares and cash yourself after a modeled
fill; the CLI has no fill journal. Prefer the app's explicit simulated-fill workflow
above once you use its journal. No broker position is read or proposal filled
automatically. Direct edits to an app-journaled book can block accounting recovery.
Do not mix deposits, withdrawals or other assets into an ongoing ledger.

Setting `halted` to true blocks all proposals. Drawdown memory is held in the ledger
and cannot be cleared by lowering this file's peak or restarting. Preserve legacy
ledgers; those without risk memory require reviewed migration, not deletion.

## 5. Start only after readiness passes (CLI alternative)

```sh
./scripts/run_daily.sh --check
./scripts/run_daily.sh
```

Both commands fail before external calls if study evidence is absent or rejected.
The runner does not create a study for you. Keep the computer awake and the terminal
open. It waits for the calendar's open and records one decision at about 09:31 New
York. Stop with Ctrl-C. `--once` handles the current day only.

Optional phone notifications use operator-configured `NTFY_TOPIC` in
`~/.config/hft-ibkr/notify.env`. Review the provider before enabling it. Status also
goes to `.research-output/shadow/run.log`; a channel name should stay private.

## 6. Check health independently

From a separate terminal or scheduler:

```sh
python3 scripts/check_shadow_health.py \
  --heartbeat .research-output/shadow/heartbeat.json \
  --ledger .research-output/shadow/ledger.sqlite
```

The checker is offline. Exit 0 means the declared health checks pass; exit 2 means
missing/stale/future/failed state or a missed decision deadline. The runner records
its expected daily deadline. You can also supply `--session YYYY-MM-DD --deadline
UTC_TIMESTAMP` to the checker explicitly. A stopped runner cannot send an alert
about its own death: use an independent scheduler and alert path if you need that.
No scheduler or monitoring service is installed by this project.

## Troubleshooting

| Result | Action |
| --- | --- |
| Readiness/evidence failure | Preserve artifacts; check protocol, source identity, registry and verdict. Do not bypass it with a custom config. |
| Holdout already released | Preserve registry; use a separately frozen protocol on fresh future dates. |
| Legacy ledger | Retain history for reviewed migration; do not reset it to erase a halt. |
| Corrupt/conflicting decision | Stop; preserve the ledger and inputs for investigation. |
| Stale/future quote | Check clock/network; invalid marks do not update risk memory. |
| Intake/calendar/dividend failure | Stop and review data quality; do not edit data to force acceptance. |
| Stale heartbeat/missing decision | Check whether the PC slept, runner stopped or inputs failed. |

See the [component reference](docs/reference/components.md) for offline commands and
[Windows/WSL runbook](docs/operations/windows-wsl-runbook.md) for operator details.
