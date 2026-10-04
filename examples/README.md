# Synthetic daily research fixture

`synthetic_spy_daily.csv` contains 460 invented weekday observations, deterministic
rise/decline/recovery regimes and three invented dividends. This is neither SPY
history nor an exchange calendar. It exercises the default 200-session warmup and
entry/exit/receivable behavior without downloading data.

`research_config.json` explicitly supplies simulator capital, risk limits and assumed
fees/spread/slippage/impact. The illustrative per-share commission is not a complete
broker commission schedule. No account, credential or production configuration is
included.

`synthetic_spy_manifest.json` contains the exact CSV hash, synthetic provenance and
session list. After intentionally changing the fixture, regenerate its hash/session
list; a mismatch fails validation. For historical inputs, use a trusted exchange
calendar and reviewed raw-price corporate-action records rather than this calendar.

`synthetic_protocol.json` predeclares development/validation/holdout ranges, five
embargo sessions and three illustrative lookbacks. It demonstrates the evaluation
workflow; no candidate performance on invented prices is economic evidence.

`control/A01.json` through `A14.json` map the delivery plan's control acceptance
IDs to invented events. A03 is intentionally malformed and must exit 2 with no
report. All other cases are valid simulations, some deliberately ending HALTED or
RECONCILING. Expected outcomes are recorded in `tests/test_control_cli.py`.
