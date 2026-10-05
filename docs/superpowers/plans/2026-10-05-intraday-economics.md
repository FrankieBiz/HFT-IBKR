# Intraday economics implementation plan

Date: 2026-10-05.

**Goal:** Implement the G0 conditional break-even table and funding bound without
inventing market data, account eligibility or executable performance.

**Architecture:** Strict input parser, exact rational cost model with Decimal
report amounts, thin offline CLI.
Reuse report publication and source hashes; package with the existing portable CLI.

**Tech stack:** Python standard library, unittest; no new dependencies.

Design: [economics contract](../specs/2026-10-05-intraday-economics-design.md).

- [x] Add `tests/test_economics.py` and `tests/test_economics_cli.py`: hand-calculated
  cost/capital boundaries, malformed input, deterministic reporting and archive parity.
  Run `python3 -m unittest discover -s tests -p 'test_economics*.py' -v` and confirm
  missing implementation before adding production code.
- [x] Add `quant_economics/inputs.py`: strict validated dataclasses; required metadata,
  date and decimal fields; bounded unique grids and side-specific fee schedules.
- [x] Add `quant_economics/model.py`: continuous capped fees, analytic exit-price
  break-even, scenario grid, funding constraints and explicit no-operation benchmark.
- [x] Add `quant_economics/__main__.py`, `__init__.py` and
  `examples/economics/synthetic.json`: deterministic report, hashes, no-overwrite CLI.
- [x] Extend `scripts/build.py` and `Makefile`; exercise archive from outside checkout.
- [x] Update authoritative research/delivery plans and README with implementation
  state, commands and next empirical dependencies. Add a dated research decision.
- [x] Perform independent adversarial review, resolve findings, run `make check build
  demo`, record actual verification and leave a reviewable change on the current branch.

G0 remains unresolved after this implementation. Completing a calculator is
software evidence; affordable real data, source semantics and economic calibration
remain required before intraday feature/replay construction.

Completed 2026-10-05: 199 tests passed; compile, build and full synthetic demo
passed. Independent spec and implementation reviews completed; two numerical
findings were reproduced with tests and corrected using exact rational arithmetic.
See the [evidence record](../../research/2026-10-05-economics-and-edge-gates.md).
