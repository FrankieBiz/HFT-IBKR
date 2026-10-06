# Alpaca intake feed access, 2026-10-06

An operator reported HTTP 403 saying the subscription does not permit querying
recent SIP data. The intake hard-coded SIP for daily bars and minute cross-checks;
the CLI offered no feed selector. Reproduced offline using a transport that rejects
SIP while permitting IEX. No operator keys or authenticated requests were used.

Primary sources reviewed on 2026-10-06:

- [Historical stock data](https://docs.alpaca.markets/us/docs/historical-stock-data-1):
  `feed` selects the source; IEX is the single-exchange feed available without a
  subscription. SIP is consolidated across exchanges.
- [Market data FAQ](https://docs.alpaca.markets/docs/market-data-faq): historical SIP
  without a subscription requires `end` at least 15 minutes old. Latest SIP endpoints
  require a subscription. Thus this error does not establish that all historical
  SIP access requires payment; the denied query may instead be too recent.
- [Market data API plans](https://docs.alpaca.markets/us/docs/about-market-data-api):
  Basic provides IEX real-time coverage and restricts the latest 15 historical minutes.

Decision: default new intake to explicit IEX. Provide a standalone `--feed sip`
option when the operator has permitted access. Daily and sampled minute requests
use the same selected feed, including pagination. An explicit SIP failure remains
a failure; there is no automatic downgrade. Metadata and cross-check reports label
the selected feed. Previously published intake folders are never overwritten.

Upgrade compatibility: daily operations obtain the feed from the authenticated
study's bound intake manifest. An existing SIP-qualified study keeps SIP downloads;
a new IEX study uses IEX. Readiness compares existing and newly prepared daily
bundles with that feed before cache presentation or planning. Unknown/ambiguous
operational feed declarations fail closed. Offline generic study verification
remains available without assuming that its data came from Alpaca.

IEX prices/volume are exchange-specific and may have sparse coverage. Existing
calendar equality, dividend completeness and sampled minute-bar checks still apply;
they must fail rather than invent missing data. Passing them does not verify official
auction prices or consolidated coverage. Neither access success nor software tests
establish economic qualification. Preserve prior registries, studies and ledgers;
do not replace a consumed holdout or relabel its data to requalify a changed source.

Verification: reproduced the subscription failure with an offline rejecting transport
before changing the default. Feed/provenance and operational mismatch regressions
passed after the fix. Independent review resolved feed-switching and synthetic-daily
acceptance issues and found no remaining blockers in scope. `make check build demo`
exited 0 with 273 tests, compilation, diff checking and the synthetic demo passing.
No authenticated provider request was made; the operator must retry their download.

## Follow-up: qualified SIP daily download

The operator then supplied a daily-run failure at 2026-10-06 15:39 EDT after
historical readiness passed. Preserving the qualified SIP feed was correct, but
the daily intake still advanced a date-only end into the current date. The previous
default-feed repair did not address that request boundary. The provider's exact
interpretation was not tested with credentials; eliminating date-only ambiguity
and enforcing the documented historical delay is the bounded repair.

Reviewed the [historical bars reference](https://docs.alpaca.markets/us/reference/stockbars)
and [Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) on
2026-10-06: RFC3339 boundaries are supported, the end is inclusive, and unsubscribed
historical SIP requires an end at least 15 minutes old.

Intake now sends explicit UTC timestamps from New York dates, ending just before
the following session's midnight label or 16 minutes before the captured clock,
whichever is earlier. It requires the final requested calendar close to be no
later than that bound before requesting any bars. This retains completed daily
bars and keeps all sampled minute closes and paginated daily requests outside the
recent-data window. Existing qualified feed, study records and ledger are preserved.
HTTP errors expose validated feed/timeframe/date context while excluding keys,
opaque page tokens and arbitrary query fields.

Regressions failed before the repair and passed afterward for explicit delayed SIP
bounds, pagination, summer/winter label exclusion, incomplete-session rejection,
and redacted query diagnostics. Validation is offline; actual API recovery requires
the operator's rerun, not re-release or deletion of completed study evidence.

Follow-up verification: `make check build demo` exited 0 with 277 tests, compilation,
diff checks and the synthetic demo passing. Independent request-bound and secret-
redaction reviews found no remaining blockers within scope.
