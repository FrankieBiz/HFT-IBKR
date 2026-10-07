# Reliability and evidence validation — 2026-10-07

This pass repairs operational defects and improves the local study display. It
keeps the daily SPY long/cash rule and frozen research sources/config/protocol
unchanged. It adds no broker execution or unattended maintenance. The user chose
maintenance whenever requested, with tested GitHub pushes and documentation.

## Verified changes

- Quote parsing preserves original timezone offsets before requiring UTC;
  fractional non-UTC timestamps cannot masquerade as current UTC quotes.
  Snapshot NAV uses the fixed Decimal context.
- Fill eligibility and fill accounting share snapshot/hash/book matching. Halt,
  settlement, missing snapshot and altered snapshot regressions are covered.
  Invalid heartbeat data is rejected before browser projection. Offline tool
  checks do not depend on saved provider-key contents.
- Setup projects the authenticated selected SMA, exact planning settings and
  matched held-out trend/benchmark cost scenarios. Missing optional metrics are
  labeled as unrecorded. Historical evidence remains unproven.
- Only the read-only study display is content cached. Evidence bytes, research
  sources and SQLite WAL/journal changes invalidate it, including changes with
  preserved size/mtime. Changing evidence during verification fails closed.
  Portfolio/accounting/history and runner evidence gates are not cached. Hidden
  browser pages stop polling; the backend runner remains independent.
- Continuous daily decisions receive at most three attempts, 600 seconds apart,
  only in the same open New York market session, with fresh calendar/evidence
  checks. `--once` fails fast. Failure health survives retry waits and exhaustion.
- `daily_shadow.sh` recovers exact committed report bytes only after original
  input/source/readiness verification, before intake keys or input regeneration.
  The outer runner retains its gated provider-calendar scheduling role.
- Explicit study runs can restore missing completed validation, original
  registered selection and holdout artifacts using a read-only registry. No
  research is repeated or dates reopened. Unfinished attempts, missing freezes,
  changed inputs, corrupt payloads and divergent outputs require review. Rejected
  completed results can be restored without qualifying them for shadowing.

## Checks and measured performance

`make check build demo` passed on the final source: **347 tests**, compile and
whitespace checks, deterministic portable archive and `offline_workflows_passed`.
Archive SHA-256: `ec559b99968aac5147bcac4ea28cda1732a39aeed33a62571c0de3fde7a7de85`.
Bash and JavaScript syntax checks passed. Chromium integration passed on desktop
and mobile widths with invented fixtures/fake keys, including the strategy panel,
setup, manual fills/recovery, owned Start/Stop, corrupt history and no external
assets or console errors. Independent app/study/input and daily recovery reviews
found no remaining substantive issues.

A cProfile comparison of **40 unchanged Service.snapshot calls** on the same
small invented SIP study fixture measured 0.252171 seconds before and 0.060090
seconds after, about **4.2x faster**. Full readiness calls fell from 40 to 1.
This includes the first verification and local byte hashing, with no portfolio
or decision history. It is a macOS/Python 3.14 fixture measurement, not a WSL,
large-study or production latency guarantee.

`git diff --exit-code 2002e7f -- quant_research studies/spy-trend-v2` passed:
the economic-study source/config/protocol identity is preserved. New operational
source hashes still differ; an already frozen same-day decision cannot be
replanned after updating code. Its history must remain intact.

All validation used temporary invented state. No real keys, account data or
provider requests were used. Windows desktop handoff and authenticated data
connection remain checks on the operator's computer. Independent monitor
scheduling, execution-cost calibration, prospective strategy evidence and a
broker adapter remain outstanding; passing software checks proves none of those.

Primary references checked on 2026-10-07:
[Alpaca latest quotes](https://docs.alpaca.markets/us/reference/stocklatestquotes-1),
[Python ISO parsing](https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat),
[Python Decimal contexts](https://docs.python.org/3/library/decimal.html#decimal.localcontext).
