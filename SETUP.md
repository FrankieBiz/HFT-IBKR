# Setup guide

This guide takes a Windows PC with WSL (Ubuntu) from nothing to a system that runs on
its own each trading day and reports to your phone. Every command runs in the
**Ubuntu (WSL) terminal**. After each step there is a ✅ check, so you know it worked
before moving on.

> **What you're setting up:** once per trading day, one minute after the 09:30 New
> York open, the system decides whether a shadow portfolio should hold SPY or cash. It
> records the decision and pushes it to your phone. **It never places orders.**
> [README](README.md) explains how it decides; the
> [WSL runbook](docs/operations/windows-wsl-runbook.md) has extra detail.

**You need:**

- Windows 10 or 11 with WSL and Ubuntu installed.
- An internet connection.
- About 30 minutes.
- A phone, for notifications (optional).

The IB Gateway is **not** needed.

---

## 1. Install the basics

```bash
sudo apt update
sudo apt install -y git make python3 python3-venv tzdata ca-certificates curl unzip
python3 --version
```

✅ Python must print **3.11 or higher**. If it shows 3.10 (Ubuntu 22.04):

```bash
sudo apt install -y python3.11 python3.11-venv
```

Then add `PYTHON=python3.11` in front of every `make` and `./scripts/...` command
below. For example: `PYTHON=python3.11 make check build demo`.

## 2. Download the code and test it

Keep it in your Linux home folder (`~`), **not** under `/mnt/c`.

```bash
cd ~
git clone -b FrankieBiz/feat-hft-research-review https://github.com/FrankieBiz/HFT-IBKR.git
cd HFT-IBKR
make check build demo
```

✅ Working if the test summary ends in **`OK`** and the final block shows
**`"status": "offline_workflows_passed"`**.

> Once pull request #2 is merged you can use `main` instead:
> `git checkout main && git pull`.

## 3. Get free market-data keys (Alpaca)

1. Sign up at **https://alpaca.markets**. Email only: no card, no deposit.
2. In the dashboard choose **Paper Trading**, then **API Keys → Generate**. Copy both keys.
3. Save them in a private file:

```bash
mkdir -p ~/.config/alpaca && chmod 700 ~/.config/alpaca
nano ~/.config/alpaca/paper.env
```

Type these two lines with your real keys:

```text
APCA_API_KEY_ID=your-key-id
APCA_API_SECRET_KEY=your-secret
```

Save with **Ctrl-O**, **Enter**, **Ctrl-X**, then lock the file:

```bash
chmod 600 ~/.config/alpaca/paper.env
```

> Never paste the keys into chats, commits or commands. The tools read them from this
> file and never print them.

## 4. Set up phone notifications (ntfy)

```bash
mkdir -p ~/.config/hft-ibkr && chmod 700 ~/.config/hft-ibkr
echo "NTFY_TOPIC=hft-ibkr-$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')" > ~/.config/hft-ibkr/notify.env
chmod 600 ~/.config/hft-ibkr/notify.env
cat ~/.config/hft-ibkr/notify.env
```

The last line prints your private channel name, something like
`hft-ibkr-Xy3...`. Anyone who knows it can read your status messages, so keep it to
yourself. Messages contain only status, never keys or account details.

- **Phone:** install the free **ntfy** app (App Store or Google Play), tap **+**, and
  subscribe to your channel name on server `ntfy.sh`.
- **Mac or any browser:** open `https://ntfy.sh/` followed by your channel name.

## 5. Create your shadow portfolio

```bash
mkdir -p .research-output/shadow
cp examples/shadow/portfolio.template.json .research-output/shadow/portfolio.json
nano .research-output/shadow/portfolio.json
```

Set `cash`, `settled_cash` and `peak_nav` to the amount you'd dedicate to the strategy
(default `50000`). Leave `shares` at `0` and `halted` at `false`, then save.

> Nothing updates this file for you. If you want the shadow to follow a BUY or SELL,
> edit the shares and cash yourself afterwards. Setting `"halted": true` blocks all
> decisions.

## 6. Check everything works (do this the night before)

```bash
./scripts/run_daily.sh --check
```

✅ Your phone or browser shows **"Setup check passed"**. If you see `FAILED`, the keys
or network are wrong; see [Troubleshooting](#troubleshooting).

```bash
./scripts/run_study.sh
```

✅ It takes about a minute and finishes with `"outcome": ...`, the verdict of the
one-time pre-registered study. The study can only be released once, so a second run
just reprints the verdict.

## 7. Keep the PC awake

In Windows, open **Settings → System → Power → Screen and sleep**. Set "When plugged
in, put my device to sleep after" to **Never**. Keep the PC plugged in and online.

## 8. Start it each morning

```bash
cd ~/HFT-IBKR && ./scripts/run_daily.sh
```

Then **minimize** the Ubuntu window. **Don't close it**: closing it stops the system.
You can start it any time before the open, for example 6:30 am. It waits on its own
and keeps running day after day until you press **Ctrl-C**.

## 9. Check on it from anywhere

On your phone or at `https://ntfy.sh/<your channel name>` you'll see:

| Notification | When |
| --- | --- |
| **HFT-IBKR started** | As soon as you start it |
| **Study verdict** | First run only, if step 6 was skipped |
| **Waiting for the open** | Right away; shows the minutes until 09:31 New York time |
| **Today's decision** | A little after 09:31 New York time: `BUY` / `SELL` / `HOLD` / `BLOCKED` |
| **Market closed today** | On market holidays |
| **… FAILED** | If something breaks; includes the error. It keeps running. |

No message by about **09:40 New York time** means the PC slept, lost internet or the
window was closed. Back home, the full history is here:

```bash
cat ~/HFT-IBKR/.research-output/shadow/run.log
```

## Updating later

```bash
cd ~/HFT-IBKR && git pull && make check
```

---

## Troubleshooting

| You see | Do this |
| --- | --- |
| `set APCA_API_KEY_ID and APCA_API_SECRET_KEY` or `HTTP 401` | The keys are missing or wrong. Re-check `~/.config/alpaca/paper.env` (step 3). |
| `HTTP 403 ... SIP` | Alpaca's free plan refused the historical data. Stop and report it; don't switch data feeds. |
| `CERTIFICATE_VERIFY_FAILED` | `sudo apt install --reinstall ca-certificates` |
| `ZoneInfoNotFoundError` | `sudo apt install tzdata` |
| `market is closed now` | Normal before 09:30 or after 16:00 New York time. Nothing was recorded. |
| `STALE_QUOTE` or `FUTURE_QUOTE` | The WSL clock drifted. In PowerShell run `wsl --shutdown`, then reopen Ubuntu. |
| `dividend history incomplete` or `daily bars do not match the calendar` | The data failed a safety check and nothing was written. Report it. |
| `Alpaca pay dates disagree with the issuer schedule` | The data failed a safety check and nothing was written. Report it; don't edit the data. |
| `session decision conflict` | Today's decision is already recorded. This protection is intentional. |
| No phone notifications | Check the channel name in the app matches `cat ~/.config/hft-ibkr/notify.env`, then run `./scripts/run_daily.sh --check`. |

## Before you leave home: checklist

- [ ] `./scripts/run_daily.sh --check` reached your phone
- [ ] Windows sleep is set to **Never**, and the PC is plugged in
- [ ] `./scripts/run_daily.sh` is running in a minimized Ubuntu window
- [ ] You received **HFT-IBKR started** and **Waiting for the open**
