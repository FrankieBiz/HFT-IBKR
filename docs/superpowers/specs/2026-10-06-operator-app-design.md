# Local operator app — approved design

Status: approved by the user on 2026-10-06: "Build the whole thing then."

## User outcome

Replace routine terminal commands with a local app for the user's existing Windows
and WSL/Ubuntu installation. Open it in the Windows browser. Show setup progress,
the daily runner, understandable errors and a verified history of shadow decisions.
Keep historical research, manual simulated holdings and broker execution distinct.

## Choice of interface

Recommended: a browser interface backed by a Python service in the existing WSL
checkout. It reuses the current scripts and needs no new runtime dependencies.
Provide one launch command and a Windows launcher for subsequent starts. First-time
WSL/Python installation remains a guided prerequisite; the app cannot run without
its runtime. Existing installations and study evidence are reused.

Alternative: a native Windows desktop installer. That requires a new packaging and
WSL integration layer before the same controls can be exposed, and adds more setup
maintenance. A read-only dashboard alone is smaller but cannot simplify starting
and stopping the workflow. The approved version is the local browser app.

## Screens and operator actions

1. **Overview:** stopped/running/waiting/failed status, heartbeat age, next expected
   decision and the latest verified decision. Show current feed and study readiness.
   Start and Stop control the shadow runner only. Opening a page starts no jobs.
2. **Setup:** check Python/project tools, detect the existing credentials file,
   authenticate historical evidence and validate the manual portfolio. Show an
   actionable next step for missing inputs. Explain data-download actions before
   their buttons run. Never rerun a completed study or initialize replacement audit
   history to make the screen green. Optional local key entry, if implemented, is
   blank on reload, saved only on an explicit operator action outside the checkout,
   and never echoed to the page, logs or reports.
3. **Decisions:** date, BUY/SELL/HOLD/BLOCKED, proposed shares, reference price,
   reason and modeled NAV. Read the integrity-verified ledger, not arbitrary plan
   files. Include an explicit empty state and a decision-detail view. These are
   proposals; no execution or fill is inferred from them.
4. **Portfolio:** declared simulated cash and shares, last observed NAV and a chart
   of recorded NAV marks. Label the mark's date; no live account balance or real
   P&L is claimed. A guided manual editor supports the existing accounting model,
   preserves ledger peaks/halts, validates changes and never treats a proposal as
   automatically filled. External deposits/withdrawals remain unsupported.
5. **Activity:** bounded job output and understandable failure details, including
   existing safe Alpaca feed/timeframe/date diagnostics. Do not expose credentials
   or arbitrary local files. Health updates read local state; they do not poll a
   broker or market-data service just because a browser page is open.

## Components and contracts

Add a separate `quant_app` package for the local HTTP interface, status/history
projection and job supervision. Reuse readiness, heartbeat, portfolio validation
and verified ledger logic. Keep financial calculations in the existing modules.
Serve bundled HTML/CSS/JavaScript with no third-party runtime/CDN assets.

Use a small allowlist of fixed subprocess argument lists rooted at the checkout:
environment/offline checks, explicit study, setup check and daily shadow runner.
The browser supplies action identifiers, never shell commands, executable paths,
config overrides or study/registry locations. Report background job progress and
exit status. Bound job concurrency and retained logs. A rejected study retains
its evidence and provides a readable explanation rather than a reset option.

Starting the app does not start a study, fetch data, contact notification services
or start the runner. Those actions require the operator's corresponding button.
Existing qualified SIP studies retain SIP; new studies follow the current default.
All readiness, feed, source, stale-input and risk gates remain in effect.

## Process ownership and storage

Prevent duplicate app-owned jobs. Add a runner-wide ownership lock if necessary so
an app and terminal cannot start two runners together. If a terminal owns the
runner, show that state and instruct the user to stop it there; never kill an
unrelated PID. Stop only owned process groups and ensure existing shutdown hooks
record heartbeat status. Define shutdown behavior explicitly and explain it in
the launcher. Closing the browser is distinct from closing the backend.

Keep study files, shared registry, shadow ledger and heartbeat in their established
locations. New app state/logs live under ignored `.research-output/`. Never overwrite
existing portfolio or evidence during setup; do not clear a risk latch. Use atomic
writes and validate source files before changing an existing manual book.

## Local access boundary

Bind only to loopback. Validate Host and Origin for browser requests, reject cross-
origin mutations and require a session/CSRF capability for every action. Do not put
secrets in URLs. No arbitrary filesystem-serving or command-execution endpoint.
Serve escaped data and restrictive response headers; bound request bodies and
responses. Treat the UI as a convenient controller, not a replacement risk engine.

## Validation and delivery

Use invented fixtures and mocked provider transports. Test corrupted ledger and
study records, missing setup inputs, truthful empty/stale states, job failures,
duplicate starts, owned stop/shutdown, origin/token rejection and secret redaction.
Verify the browser screens and button states without triggering real downloads or
reading actual API keys. Run the repository's full checks/build/demo.

Update Windows/WSL setup documentation, publish source on the existing GitHub
branch and provide the exact launch steps. Document which bootstrap prerequisites
are still necessary. A native executable, broker orders, automatic fill accounting,
intraday price charts and unattended Windows installation are outside this version.

## Concrete first-version choices

Include blank local key-entry fields and a Save keys action; keys are written with
restrictive permissions to the existing Alpaca config file only on that action.
Do not read/display previous key values. API keys accept only a bounded simple
token alphabet so they cannot inject commands into the existing shell env file.
Tests use fake keys exclusively. The agent will not save or inspect real keys.

Initialize a fresh manual book explicitly from the UI with a chosen starting cash
amount. For an existing book, allow operator-declared simulated fills matched to a
verified proposal and explicit settled-cash/manual halt updates. Apply accounting
with Decimal and append fill records; forbid repeated fills, external cash changes
and edits that lower peak memory or clear an existing halt. This avoids a general
cash editor that could silently mix deposits into strategy results.

The app owns runner/study/check processes, stops them on backend shutdown, and
keeps the browser separate from backend lifetime. A single runner lock also covers
terminal starts. Actions serialize book changes against an active app job/runner.
Existing history and evidence never need to be discarded to use the app.

Visual direction: slate blue (#18364a), cool white (#f6f8fb), dark ink (#142b38),
muted teal (#176b63), soft amber (#a46012), and restrained red (#a63c44). Use system
Segoe UI for controls and tabular numerals for finance. A left navigation rail and
large status band frame a wide decision ledger; charts and setup steps are secondary.
Prioritize readable daily actions, calm empty/error states and accessible controls.

Primary design references verified 2026-10-06:
- [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking):
  Windows browsers can access WSL applications using localhost; keep binding local.
- [Python HTTP server](https://docs.python.org/3/library/http.server.html): the standard
  library server supports local serving, but its basic checks require explicit Host,
  Origin, request-size, capability and filesystem boundaries for this app.

Shutdown implementation reference checked 2026-10-06:
- [Linux proc_pid_stat(5)](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html):
  process state and group fields let Linux shutdown distinguish non-running zombie
  records from surviving owned work; the guardian retains locks through group cleanup.
