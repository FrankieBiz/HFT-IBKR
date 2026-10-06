# Operator app validation — 2026-10-06

The local browser app exposes setup, owned job control, verified shadow decisions,
a manual simulated portfolio and bounded activity output. It sends no broker
orders. This verification used invented data and fake keys exclusively; no real
account credentials were inspected or provider requests made.

## Authoritative checks

- `make check build demo` passed: **318 tests**, compile checks, diff whitespace,
  deterministic standard-library archive build and `offline_workflows_passed` demo.
- `node --check quant_app/assets/app.js` and Bash syntax checks passed.
- Chromium browser integration passed via `scripts/check_app_browser.py` against
  a temporary checkout/config. It verifies blank key saving, book initialization,
  retained qualified SIP fixture, decision detail, explicit simulated fill,
  interrupted-fill recovery without settlement/halt changes, owned Start/Stop,
  active-job controls, corrupt-ledger error, mobile width, no external assets and
  no console errors. The README screenshot uses this invented fixture.
- Independent spec and code/security reviews approved the final implementation.

Financial tests cover full-quantity Decimal accounting, insufficient settled
cash/inventory, precision rejection, duplicate decisions, snapshot identity/book
matching, before/after replacement crashes and unexplained divergence. Ledger
reads verify the whole risk-memory chain. Manual global halt remains separate
from the ledger's buy-only drawdown latch, allowing eligible reducing exits.

HTTP tests exercise real loopback requests, Host/Origin/Fetch Metadata rejection,
capability checks, bounded request/response sizes, strict action fields and fixed
assets. A real CLI launch serves the app without starting jobs or reading keys,
rejects a second instance and shuts down on a signal.

Process tests exercise real nested guardians, duplicate ownership, app study and
runner shutdown, and children that ignore SIGTERM on both Stop and close. The
shared lock covers terminal daily entrypoints and blocks pending/corrupt accounting
before their scripts run. Linux zombie handling uses invented `/proc` fixtures.

## Limits of the evidence

The actual process/browser runs were on macOS with Python 3.14 and Chromium.
Python 3.11/3.14 Ubuntu CI is configured separately. A real Windows/WSL desktop
was not available locally, so the Windows launcher/browser handoff was reviewed
but not exercised on that host. Provider subscription behavior and authenticated
connection still need the operator's explicit connection check on their computer.

Software verification establishes interface/accounting/control behavior, not
profitability, strategy qualification on real data or production broker readiness.
Existing financial evidence and audit history are preserved; no study was rerun
or reset to obtain a passing application check.
