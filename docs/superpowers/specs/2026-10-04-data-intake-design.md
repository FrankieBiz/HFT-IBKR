# Offline data intake design

Authorized scope: the user asked to build all locally available components and
commit/push verified increments. This implements M2's intake mechanics; reviewed
historical data and calibrated trading assumptions remain separate dependencies.

## Decision

Normalize local exports into a single deterministic `.qdata` ZIP bundle containing
`dataset.csv`, `manifest.json`, and `intake.json`. This permits atomic non-overwriting
publication of the whole dataset. A multi-file output folder could expose partial
results; downloading from a provider would require a separate provider/license
decision. No credentials, network calls or paid data retrieval are involved.

## Input and provenance contract

Prices: exact CSV header `session,open,high,low,close,volume`.
Distributions: `ex_date,amount,pay_date`; no duplicate ex-dates or out-of-interval
events; amounts are positive, pay dates later than ex-dates. An empty distribution
file must still have its header. Calendar: `session`, increasing exact sessions.
All files are UTF-8, consumed once, bounded at 32 MiB each.

Metadata schema version 1 declares SPY/USD, synthetic or historical kind,
`raw_unadjusted`, `complete_dividends_no_splits`, `splits_in_interval: false`,
a nonempty review note, and three source entries (prices, distributions, calendar).
Each entry requires `name`, `reference`, `license_reference`, `retrieved_at` in UTC.
These are declarations, not independent verification of license or completeness.
The bundle records hashes of all four original inputs and binds its intake audit
into the existing manifest source field without changing the manifest schema.

Reuse the existing loader for numerical, OHLC, volume, dividend, hash and session
validation. Never fill calendar gaps, infer missing pay dates, silently adjust
prices or claim a synthetic example is historical evidence. First-session dividends
remain unsupported by the existing loader; supply a preceding session when needed.

## Bundle and CLI

`quant_data prepare --prices P --distributions D --calendar C --metadata M --output B`
validates and publishes the bundle. `quant_data inspect --bundle B --output R`
validates and publishes a source/coverage report; no strategy selection occurs.
Add portable `data` dispatch. Add `--bundle` to research replay/evaluate/holdout,
mutually exclusive with the existing `--data` + `--manifest` pair.

Bundle reads require exactly the three expected members, reject duplicate names,
and bound each decompressed member. No ZIP paths are extracted. Read fixed members
to private temporary files and reuse strict JSON/dataset loaders. Require the
audit to match the manifest's bound source. Standard input hashes detect accidental
change, not deliberate rewriting of all declarations.

Exit 0: valid operation; 2: invalid input/publication. Output parent must exist,
existing files/symlinks are preserved, and publication uses fsync plus atomic hard
link. Normalization produces LF CSV and deterministic ZIP timestamps/order.

## Verification

Tests: valid bars preserved; header/calendar gaps; duplicate distributions;
adjusted/split declarations; malformed money/pay dates; missing license references;
deterministic bytes; invalid ZIP members/duplicates/oversize/corrupt hashes/audit;
CLI non-overwrite; bundled replay and chronological evaluation match the original
bars and financial results. Extend the automatic demo to prepare/inspect/use the
synthetic bundle. No original licensed inputs or generated bundles are pushed.
