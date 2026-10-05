# Daily edge evidence implementation plan

**Goal:** Make the existing G3 pilot uncertainty/cost arithmetic executable without
claiming empirical G3 completion or opening a broker connection.

**Architecture:** Strict daily-series parser; pure integer-accounting and block
bootstrap; thin CLI reusing deterministic provenance and output publication.

**Tech stack:** Python standard library / unittest; no dependencies.

Design: [contract](../specs/2026-10-05-edge-evidence-design.md).

- [x] Write `tests/test_edge_evidence.py`: arithmetic, percentile/block mechanics,
  deterministic method, adverse scenarios, unbounded/constraint handling and inputs.
  Confirm failure before implementation with `python3 -m unittest discover -s tests
  -p 'test_edge_evidence*.py' -v`.
- [x] Implement `quant_evidence/inputs.py` for exactly 30 aligned sessions, explicit
  unbounded outcomes and bounded signed decimal amounts converted to integer units.
- [x] Implement `quant_evidence/statistics.py`: prefix-sum block resampling, exact
  percentile interpolation, cost totals and drawdown; `assessment.py` for precedence
  and mandatory diagnostic-only metadata. No caller-tunable statistical search.
- [x] Add CLI, synthetic fixture and CLI tests; include exact input/code identity,
  RNG/runtime metadata, no-overwrite publication and portable archive parity.
- [x] Integrate `scripts/build.py`, `scripts/demo.py`, `Makefile`, README and plans.
- [x] Obtain independent spec/code review, fix material findings, run `make check
  build demo`, record evidence, commit and push to the existing GitHub branch.

The next empirical dependency remains a licensed intraday sample and the real G0
capital/cost/data contract. No financial performance result follows from this build.

Verification: 219 tests plus build and full synthetic demo passed; independent
review complete. See the [evidence record](../../research/2026-10-05-edge-evidence-implementation.md).
