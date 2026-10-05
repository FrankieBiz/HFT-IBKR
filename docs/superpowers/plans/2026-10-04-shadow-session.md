# Integrated Daily Shadow Session Implementation Plan

**Goal:** Connect causal research decisions, quote-time risk sizing and a durable
audit in one executable offline workflow, without broker or order authority.

**Architecture:** Pure input/decision units in `quant_session`, a SQLite ledger and
thin CLI. Integrate package into deterministic zipapp and synthetic demo. Retain
the existing control simulator unchanged as a reference model.

**Tech Stack:** Python standard library, existing quant_research/quant_data helpers.

1. Implementer: write failing acceptance tests, then `quant_session/{__init__,inputs,
   planner,ledger,__main__}.py`. Follow the reviewed spec exactly. Run focused tests;
   no SDK/network/order calls. All source files remain bounded/responsibility-focused.
2. Root integrator: add package/command to `scripts/build.py`, compilation check;
   add synthetic schedule/snapshots and demo scenarios BUY/HOLD/SELL/BLOCKED,
   retry consistency and conflicting-session rejection. Add meaningful CLI/archive
   regression tests. Run `make check build demo`.
3. Independent spec compliance review, then code-quality review. Resolve concrete
   issues and repeat relevant verification. Update README/runbook and delivery plan
   to reflect completed mechanics and remaining real-world requirements.
4. Commit and push reviewable changes on existing authorized feature branch. Report
   what is built and the remaining read-only normalization, historical validation,
   prospective shadow and separately authorized paper-order stages.

## Execution evidence

- Independent strategy research and repository audit both recommended preserving
  the tested foundations and changing delivery priority, without an HFT/AI rewrite.
- Spec review amended conservative effective-NAV/drawdown and exact causal schedule
  coverage before implementation. A separate agent implemented the package/tests.
- Spec-compliance and subsequent independent code-quality reviews approved the
  implementation with no remaining blockers. Focused tests passed with
  ResourceWarnings treated as errors.
- Fresh `make check build demo` passes all 178 tests, compile checks and archive
  build. The demo validates BUY/HOLD/SELL/BLOCKED, byte-identical retry and rejected
  changed-session input. Evidence: `.research-output/shadow-session-verification.log`;
  latest demo `.research-output/demo-6r8g84id/`.
- No SDK, broker/account connection, order or infrastructure was used by this
  workflow. Strategy profitability, real broker semantics and target-machine
  latency remain unverified.
