# Windows + WSL runbook: set up once, test each trading day

For a Windows PC with WSL (Ubuntu) and IB Gateway on Windows. Written 2026-10-05.
**Nothing here places, modifies or cancels orders.** IBKR Lite has no API access
(IBKR's plan comparison lists the APIs as unavailable on Lite), so the system uses
free Alpaca data. The Gateway step only checks whether an API session can open.

| When | What | Time |
| --- | --- | --- |
| Once, tonight or before the open | Steps 1–3: install, verify, add free Alpaca keys | ~20 min |
| Once, any time | Step 4: run the pre-registered study and read its verdict | ~5 min |
| Once, Gateway logged in | Step 5: read-only API connection check | ~15 min |
| Each trading day, 09:30–16:00 New York | Step 6: `./scripts/daily_shadow.sh` records the day's decision | ~1 min |
| Unattended, checked from your phone | Step 7: `./scripts/run_daily.sh` waits for the open and notifies you | start once |

The strategy is daily: one decision per session, from the previous close. Running
it more often adds nothing. A second run the same day just reprints the recorded
decision.

## 1. Prepare Ubuntu (in the WSL terminal)

```sh
python3 --version          # needs 3.11 or newer; Ubuntu 24.04 ships 3.12
sudo apt update
sudo apt install -y git make python3 python3-venv tzdata ca-certificates curl unzip
date -u                    # compare with https://time.gov; it must be within a second or two
```

- **Python too old (Ubuntu 22.04 has 3.10):** run `sudo apt install -y python3.11 python3.11-venv`.
  Then add `PYTHON=python3.11` before every `make` and script command below, and use
  `python3.11` in place of `python3`.
- **Clock wrong:** WSL's clock can drift after Windows sleeps. Run `sudo hwclock -s`, or
  `wsl --shutdown` in PowerShell and reopen Ubuntu. Quote freshness checks block
  decisions when the clock is off.

## 2. Get the code and verify it

Clone into your Linux home, not `/mnt/c`. The journal needs POSIX file locking, and
`/mnt/c` is slow.

```sh
cd ~
git clone https://github.com/FrankieBiz/HFT-IBKR.git
cd HFT-IBKR
git checkout FrankieBiz/feat-hft-research-review   # or stay on main once the PR is merged
make check build demo
```

Expected results:

- The tests end with `OK`.
- The demo prints `"status": "offline_workflows_passed"`.

If either fails, stop and send the output.

## 3. Free Alpaca keys (once)

1. Sign up at https://alpaca.markets with email only; no card or funding is needed.
2. In the dashboard, select **Paper Trading**, then **API Keys → Generate**. Copy the
   Key ID and the Secret.
3. In the WSL terminal, save them where only you can read them, outside the repository:

```sh
mkdir -p ~/.config/alpaca && chmod 700 ~/.config/alpaca
nano ~/.config/alpaca/paper.env
```

Enter these two lines, then save with Ctrl-O, Enter, Ctrl-X:

```text
APCA_API_KEY_ID=your-key-id
APCA_API_SECRET_KEY=your-secret
```

```sh
chmod 600 ~/.config/alpaca/paper.env
```

Never paste the keys into chat, commits or command lines. The tools read them from
this file. Alpaca's terms forbid redistributing the data, so it stays in the ignored
`.research-output/` directory. The tools refuse to write it elsewhere inside the repo.

## 4. Run the pre-registered study (once)

The rules are fixed in
[`studies/spy-daily-v1/PREREGISTRATION.md`](../../studies/spy-daily-v1/PREREGISTRATION.md).
Do not edit `studies/spy-daily-v1/*.json` after fetching; any change would be a new study.

```sh
cd ~/HFT-IBKR
set -a; . ~/.config/alpaca/paper.env; set +a
D=.research-output/spy-daily-v1 && S=studies/spy-daily-v1 && mkdir -p "$D"
python3 -m quant_data fetch-alpaca --start 2016-01-01 --end 2026-10-02 --output-dir "$D/alpaca"
python3 -m quant_data prepare --prices "$D/alpaca/prices.csv" --distributions "$D/alpaca/distributions.csv" \
  --calendar "$D/alpaca/calendar.csv" --metadata "$D/alpaca/metadata.json" --output "$D/spy.qdata"
python3 -m quant_data inspect --bundle "$D/spy.qdata" --output "$D/inspect.json"
python3 -m quant_research evaluate --bundle "$D/spy.qdata" --config $S/config.json --protocol $S/protocol.json \
  --registry "$D/experiments.sqlite" --selection "$D/selection.json" --output "$D/validation.json" --run-id validation-1
python3 -m quant_research holdout --bundle "$D/spy.qdata" --config $S/config.json --protocol $S/protocol.json \
  --registry "$D/experiments.sqlite" --selection "$D/selection.json" --output "$D/holdout.json" --run-id holdout-1
python3 scripts/study_verdict.py "$D/holdout.json"
```

The last command applies the pre-registered rule and prints one of:

- `DOMINATES` or `RISK_REDUCING` with `proceed_to_shadow: true`: shadowing the rule is supported.
- Anything else: the rule did not earn a shadow period.

The holdout can be released only once; a repeat is refused by design. A failed step
stops with `intake error` or `input error` and writes nothing partial; see
[Troubleshooting](#troubleshooting).

## 5. Check the IB Gateway API session (read-only)

This tells you whether your Gateway login accepts API clients at all. Because IBKR
lists the APIs as unavailable on Lite, a failure here is plausible and informative.
Nothing in steps 4 and 6 depends on the Gateway.

1. In IB Gateway, log in to **Paper Trading**.
2. Open **Configure → Settings → API → Settings** and set:
   - **Read-Only API** checked;
   - **Socket port** 4002;
   - note the **Allow connections from localhost only** box for the networking step.
3. Make WSL reach Windows. Use one of these:
   - **Mirrored networking (Windows 11 22H2 or newer, simplest).** Create
     `C:\Users\<you>\.wslconfig` containing these two lines:
     ```text
     [wsl2]
     networkingMode=mirrored
     ```
     Then run `wsl --shutdown` in PowerShell and reopen Ubuntu. Use host `127.0.0.1`.
     Localhost-only can stay checked.
   - **Default NAT networking.**
     - Find the Windows host with `ip route show default | awk '{print $3}'`, and WSL's own
       address with `hostname -I`.
     - In Gateway, uncheck localhost-only and add WSL's address under **Trusted IPs**.
     - If Windows Firewall prompts, allow it. Otherwise, in an administrator PowerShell:
       `New-NetFirewallRule -DisplayName "IB Gateway paper from WSL" -Direction Inbound -Protocol TCP -LocalPort 4002 -RemoteAddress 172.16.0.0/12 -Action Allow`
     - The host address can change after a WSL restart.
4. Install the official IBKR Python SDK in its own environment. Follow the checksum
   steps in the [paper Gateway setup](paper-gateway-setup.md#ubuntu-setup), then run:

```sh
source .gateway-venv/bin/activate
python3 scripts/check_paper_gateway.py --host 127.0.0.1 --confirm-paper --confirm-read-only   # or the NAT host IP
deactivate
```

| Result | Meaning |
| --- | --- |
| `api_connected` | This login accepts API sessions; the handshake completed |
| `connection_failed` | Nothing accepted the socket: port, networking, Trusted IPs or firewall |
| `callback_timeout` | Socket opened but no API session. Check for a Gateway prompt; this is also how a refused API (for example on Lite) can appear |

## 6. Each trading day: record the shadow decision

Once, create the shadow book: the cash this strategy would control, and no shares.

```sh
mkdir -p .research-output/shadow
cp examples/shadow/portfolio.template.json .research-output/shadow/portfolio.json
nano .research-output/shadow/portfolio.json     # set cash, settled_cash and peak_nav to your amount
```

Then, any time between **09:30 and 16:00 New York time** (13:30–20:00 UTC while US
daylight time lasts):

```sh
cd ~/HFT-IBKR && ./scripts/daily_shadow.sh
```

The script:

1. Downloads raw daily bars through yesterday and builds a fresh bundle.
2. Takes SPY's free real-time IEX quote.
3. Records one frozen decision in `.research-output/shadow/ledger.sqlite`.
4. Prints the result, for example:

```text
2026-10-06: PROPOSED  signal=LONG (from 2026-10-05 close)  quote=alpaca_iex_realtime
  proposal: BUY 72 SPY near ... -- shadow only; nothing was sent to any broker
```

Reading the result:

- **HOLD:** the signal and the book already agree.
- **BLOCKED:** a gate failed; each reason is printed (stale quote, warmup, drawdown and so on).
- **Run before 09:30:** the data is prepared and then the script stops with
  `market is closed now`. Nothing is recorded; run it again after the open.

After a `PROPOSED` decision nothing happens anywhere. To let the shadow book follow
it, edit `portfolio.json` as if filled: shares, and cash reduced by about quantity ×
price. The IEX quote is one venue's price, not the national best quote. The strategy
config is the pre-registered one (`CONFIG=...` overrides it). Do not trade real money
on these proposals unless step 4's verdict supports it. Even then, it is a historical
replay, not proof of future returns.

## 7. Leave it running and check it from your phone

`scripts/run_daily.sh` runs the one-time study if it hasn't run, then waits for each
open. One minute after the open it records the day's decision. It posts status to a
private [ntfy](https://ntfy.sh) channel you can read on a phone or in any browser.
Only status text is sent: started, verdict, decision and errors, never keys or
account data. Anyone who knows the channel name can read it, so keep it private.

Once, create the channel and test it:

```sh
mkdir -p ~/.config/hft-ibkr && chmod 700 ~/.config/hft-ibkr
echo "NTFY_TOPIC=hft-ibkr-$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')" > ~/.config/hft-ibkr/notify.env
chmod 600 ~/.config/hft-ibkr/notify.env
cat ~/.config/hft-ibkr/notify.env          # your private channel name
./scripts/run_daily.sh --check             # your phone should get "Setup check passed"
```

To read the channel:

- **Phone:** install the free **ntfy** app, tap **+**, and subscribe to that name on `ntfy.sh`.
- **Mac or any browser:** open `https://ntfy.sh/<your channel name>`.

Before leaving the computer:

- In Windows **Settings → System → Power → Screen and sleep**, set sleep when plugged in
  to **Never**. A sleeping PC pauses everything.
- Keep the Ubuntu window open; minimizing is fine. Closing it stops the runner.

Then start it:

```sh
cd ~/HFT-IBKR && ./scripts/run_daily.sh
```

Expected notifications:

| Notification | Meaning |
| --- | --- |
| **HFT-IBKR started** | Runner is up |
| **Study verdict** | First run only |
| **Waiting for the open** | Includes the minutes until 09:31 New York |
| **Today's decision** | Recorded shortly after 09:31 |
| **… FAILED** | Includes the last error lines; the runner keeps going |

If nothing arrives by about 09:40 New York time, the PC slept, lost network or the
window was closed. The same lines are always in `.research-output/shadow/run.log`.
It keeps going day after day until you press Ctrl-C. `--once` handles only today.
To update later, run `git pull` in `~/HFT-IBKR`.

## Troubleshooting

| Message | Fix |
| --- | --- |
| `set APCA_API_KEY_ID and APCA_API_SECRET_KEY` / `HTTP 401` | Keys missing or wrong; check `~/.config/alpaca/paper.env` |
| `HTTP 403 ... SIP` | The free plan refused consolidated history; stop and report it rather than switching feeds |
| `CERTIFICATE_VERIFY_FAILED` | `sudo apt install --reinstall ca-certificates` |
| `ZoneInfoNotFoundError` | `sudo apt install tzdata` |
| `dividend history incomplete` / `daily bars do not match the calendar` | Data failed a validity check; nothing was written; report it |
| `market is closed now` | Run between the open and the close |
| `FUTURE_QUOTE` / `STALE_QUOTE` blockers | Fix the WSL clock (step 1) |
| `session decision conflict` | Today's decision is already frozen; that protection is intentional |
| `output directory exists` | Reruns reuse finished steps; for a manual command, choose a new output path |
