# Daily edge evidence diagnostic: implementation evidence

Date: 2026-10-05. Implements statistical arithmetic from G3 without completing G3.

## Delivered

`quant_evidence` accepts one candidate's 30 scheduled sessions with explicit gross
P&L, variable costs, recurring costs, boundedness and constraint declarations in
four required scenarios. It reports accounting, drawdown, concentration and the
plan's fixed moving-block bootstrap of primary net daily dollars. The command is
included in the portable application and automatic demo.

The synthetic example earns a mean $1/day solely because one day earns $30 net.
All three block sensitivities return a zero lower bound. Removing the best day
leaves zero net P&L, and the numeric assessment is inconclusive. These invented
numbers test the diagnostic; they are not strategy or market observations.

Unknown outcomes remain in the cohort and suppress aggregate results for their
scenario. Missing rows are rejected. Explicit constraint failures reject the
numerical criteria. Every report forbids promotion, even when the numeric criteria
are met. Costs and stress construction are caller declarations; the tool does not
verify brokerage bills, risk policy, licensing, execution, or holdout isolation.

## Research interpretation

The [design](../superpowers/specs/2026-10-05-edge-evidence-design.md) cites the
primary research and defines the project's simpler percentile procedure. It is
not a studentized Sharpe test, a multiple-testing correction or a claim that a
30-session pilot establishes durable alpha. Repeated diagnostic runs remain possible
and cannot confer the authority of the future sealed intraday evaluation.

The next empirical dependency remains G0: real capital/risk and data-budget inputs,
a licensed feed sample with specified clocks/coverage, and calibrated execution
costs/delays. After that, implement the predeclared causal A/B feature ablation,
executable labels and hand-audited replay. Adding candidates before those inputs
are resolved would increase the search without supplying reliable evidence.

## Verification

`make check build demo` passed on Python 3.14.0 / macOS:

- 219 tests, including 20 new evidence/parser/statistics/CLI tests.
- Compile checks, diff checks, portable build and all synthetic workflows.
- Source/archive report equivalence, no-overwrite output and exact input/code hashes.
- Independent spec and adversarial implementation review. The reviewer compared
  bootstrap calculations independently, including truncated blocks. A parser
  precision mismatch was reproduced in regression tests and fixed; subsequent
  extreme-value probes and all 20 focused tests passed with no remaining findings.

Local demo: `.research-output/demo-atclpu4_/edge-evidence.json` and its
`summary.json`. Build SHA-256:
`e471ad196a9666f15f2006ffc75aa9d42083b3b52506e4efe7bc6480983a3a4b`.
Generated artifacts remain excluded from Git. No account access, paid data,
market-data collection or order submission was performed.
