# Trading desk reliability and evidence

The authorized improvement pass preserves the completed economic experiment and
all existing books, journals and decisions. It changes operational code and the
local app; it does not change `quant_research`, strategy configuration, protocol,
broker execution capability or maintenance scheduling. Maintenance is on demand.

Required repairs:

1. Preserve and validate quote timezone offsets; fix Decimal context for NAV.
2. Make displayed fill eligibility use the same snapshot/book checks as recording
   a fill. Validate heartbeat data before exposing it. Offline checks must work
   independently of malformed saved provider keys.
3. Show the qualified study's selected lookback, risk settings and cost evidence.
   Cache only its read-only display verification by content identity, including
   registry sidecars. Changed content invalidates the display cache; execution
   readiness, book, ledger and accounting remain freshly verified.
4. Retry a failed daily decision at most three times in the same open session,
   ten minutes apart. Recheck readiness/calendar each time. `--once` fails fast.
   In `daily_shadow.sh`, recover a committed decision's missing report before
   regenerating inputs or reading intake credentials. The outer continuous runner
   still uses the provider calendar after its historical gate to schedule work.
5. Recover missing study artifacts only from verified completed stored payloads
   and registered freezes. Preserve reserved/failed runs for explicit review;
   never reset the registry or rerun a consumed holdout.
6. Update README/setup and record verification. Commit and push this branch.

Validation uses invented local fixtures, no provider account calls or keys.
Software checks do not establish strategy profitability. Strategy remains the
daily SPY long/cash sleeve; optional grids/DCA/crypto are not added without an
independent experiment.

Primary references checked 2026-10-07:
- https://docs.alpaca.markets/us/reference/stocklatestquotes-1 (IEX feed semantics).
- https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat
- https://docs.python.org/3/library/decimal.html#decimal.localcontext
