# Local operator app implementation plan

> **For agentic workers:** Use subagent-driven-development for isolated implementation
> tasks and requesting-code-review for spec and quality gates. The user approved
> the design and requested the complete build; proceed without another handoff question.

**Goal:** Launch a local WSL browser app that guides setup, controls the shadow
runner and shows verified proposals and a manually maintained simulated portfolio.

**Architecture:** A separate standard-library `quant_app` package owns the local
interface, status projection and allowlisted jobs. Reuse study readiness, ledger
verification, portfolio validators and runner scripts. Local action capability,
Host/Origin checks, ownership locks and atomic storage protect operator actions.

**Tech stack:** Python 3.11+, SQLite/Decimal, POSIX locks, plain HTML/CSS/JavaScript,
Bash and a Windows launcher. No new installed runtime dependencies.

## File ownership and tasks

- [x] Review approved spec and plan independently; resolve blockers.
- [x] Backend service: create `quant_app/{__init__,service}.py` and
  `tests/test_app_service.py`. Read setup/readiness/verified ledger/health; save
  blank-entered keys outside Git; initialize manual book explicitly; record explicit
  verified-proposal simulated fills exactly once with recoverable accounting;
  preserve manual/global and ledger drawdown halts. No network on status reads.
- [x] Add `DecisionLedger.history()` with read-only whole-chain verification and
  bounded returned history. Add corruption/missing/read-only regressions.
- [x] Process layer: create `quant_app/jobs.py`, `scripts/runner_lock.py`,
  `tests/test_app_jobs.py`, `tests/test_runner_lock.py`; integrate a runner-wide
  ownership lock into `scripts/run_daily.sh`. Allow only checks, study, setup_check,
  runner. Serialize jobs, bound/redact logs, stop only owned process groups and
  stop owned jobs on server shutdown. Detect external runners without killing them.
- [x] HTTP layer: create `quant_app/{server,__main__}.py` and
  `tests/test_app_server.py`. Loopback only; validate Host/Origin; reject cross-site
  fetches; require unpredictable capability on JSON API reads/actions; restrict
  bodies/content-type/routes; use fixed assets and JSON escaping, no shell/path API.
- [x] Frontend: create `quant_app/assets/{index.html,app.css,app.js}`. Responsive
  sidebar, Overview/Setup/Decisions/Portfolio/Activity, refresh local state, key/book
  forms, explicit simulated fills and halt controls, charts and decision detail.
  Clear missing/corrupt/stale/empty states. Do not invent prices or filled trades.
- [x] Launchers: `scripts/run_app.sh`, `Start-Trading-App.cmd`; show prerequisite
  failures, open local browser, explain console lifetime and shutdown ownership.
- [x] Build/docs: package app/assets in `scripts/build.py`, include app in compile
  checks and portable dispatch. Update README/SETUP/WSL runbook/component reference.
- [x] Browser integration: use installed Playwright and invented temporary fixture
  root/home only. Check setup, navigation, simulated history, Start/Stop states,
  errors, mobile layout, no external asset requests and console errors. Save screenshots.
- [x] Independent spec compliance then code/security review; fix substantive issues.
- [x] Run `make check build demo`, shell/JS checks, staged diff checks; record evidence.
- [x] Commit/push the existing feature branch, update its draft PR, verify remote
  SHA and report exact Windows/WSL launch instructions and limitations.

## Shared Python / JSON contract

`Service(root, config_home=None)` resolves paths once. `snapshot()` returns:
`mode`, `generated_at`, `environment`, `credentials` (present/path, never values),
`study` (ready/outcome/feed/error), `portfolio` (ready/book/error), `history`
(rows/total/error), and `health`. Rows expose session, action, quantity, reference
price, modeled NAV, signal, reason, decision_id and mark_valid. No raw keys or
arbitrary file paths are accepted. Service actions: `save_keys(payload)`,
`initialize_book(payload)`, `record_fill(payload)`, `set_halt(payload)` and optional
`settle_cash(payload)`. Use InputError for rejected operator actions.

`JobManager(root, config_home)` offers `start(action)`, `stop()`, `snapshot()` and
`close()`. Snapshot returns current action/running/exit_code, recent jobs and logs.
Shell jobs use fixed scripts and scrub config/path overrides from inherited env.

HTTP GET `/api/status` merges those contracts with `jobs` and `capabilities`.
POST `/api/action` accepts `{action, ...payload}` for the fixed jobs, stop, key/book
and fill/halt/settlement actions. An action must not mutate settings/books while
any app-owned job or external runner is active. A common runner lock also closes
the race with terminal starts. GET `/api/session` establishes the browser capability
only for valid local navigation; API calls require it in a header. Static assets
come from the package's fixed asset map. No execution is implicit at startup.

## Regression-first execution

For each implementation unit, write focused tests and observe expected failure
before adding production behavior. Use actual SQLite/files/processes where possible;
mock authenticated services and use fake keys only. Run focused regressions after
each unit, review component contracts, then one authoritative full integration run.
Do not weaken existing gates or erase history to make application tests pass.

## Independent review resolutions

- Fill recovery uses a durable SQLite intent containing unique decision identity,
  validated before/after books and their hashes. Commit the intent before atomic
  portfolio replacement. Recovery under the shared lock accepts only the expected
  before or after hash; any unexplained divergence blocks further accounting.
  Explicit full-quantity fills use bounded positive price/nonnegative fees; buys
  consume settled cash and sells require inventory. Sale proceeds remain unsettled
  until an explicit settlement action. Test both sides of atomic replacement.
- The same lock covers both `run_daily.sh` and direct `daily_shadow.sh` calls.
  Guardians safely inherit the locked file descriptor for nested calls, retain it
  until child exit, and forward shutdown signals. App mutations use the same lock.
- Capability bootstrap checks exact local Host/Origin and Fetch Metadata; no CORS
  or caching. Stop authority comes from owned process handles, never stored PIDs.

## Verification evidence — 2026-10-06

- Independent design/plan and final spec reviews approved; code/security review
  approved after separating manual global halt from entry-only drawdown memory,
  providing explicit recovery, covering terminal accounting gates and closing the
  surviving-descendant shutdown case. Study jobs use the same group guardian.
- Actual macOS process tests exercise nested runners and uncooperative descendants
  on both Stop and close. Linux zombie/group parsing uses invented `/proc` fixtures;
  an actual Windows/WSL installation was not available locally.
- `make check build demo`: **318 tests** passed; see [validation notes](../../research/2026-10-06-operator-app-validation.md).
- Browser integration: Chromium, invented temporary checkout/config and fake keys.
  Setup preserves the qualified SIP fixture; key/book actions, verified decision
  detail, explicit fill, pending recovery, Start/Stop, active-job controls, corruption
  errors, mobile width, no external assets and no browser console errors pass.
- `node --check quant_app/assets/app.js`, Bash syntax and diff whitespace checks pass.
- Source includes `scripts/check_app_browser.py` to reproduce optional UI checks.
  Playwright remains an optional developer dependency, not an app prerequisite.
