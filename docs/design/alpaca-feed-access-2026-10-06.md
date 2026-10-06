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
