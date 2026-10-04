# Offline data intake implementation plan

**Goal:** Make strict local exports directly usable by the research engine.
**Architecture:** Standard-library normalization, deterministic bounded ZIP bundle,
existing loader reuse, and atomic publication. No new broker or ML dependency.

1. Create `quant_data/{__init__,bundle,__main__}.py` and tests in
   `tests/test_data_intake.py`. First test valid preservation and rejection cases;
   run them before implementing. Normalize read-once inputs and bind provenance.
2. Test bundle corruption, publication collisions and source-only CLI operation.
   Implement fixed-member bounded reading and atomic prepare/inspect publication.
3. Modify `quant_research/__main__.py` to accept either `--bundle` or the existing
   data/manifest pair for replay/evaluate/holdout. Test mutual exclusion and causal
   bundled evaluation. Add `data` archive dispatch in `scripts/build.py`.
4. Create clearly synthetic source exports in `examples/intake/`; extend
   `scripts/demo.py` to build and inspect a bundle and replay it automatically.
   Update README/runbook/delivery status; run `make check build demo`.
5. Review the implementation, commit and push the verified increment to the
   existing feature branch. Report mechanics versus outstanding real-data review.

Progress: all five tasks implemented and reviewed. `make check build demo` passed
on 2026-10-04 with 146 tests, compilation and whitespace checks. The automatic
demo prepared/inspected a bundle, verified financial replay equality with the
original fixture, evaluated/released/recovered holdout using that bundle, and
passed all 14 control scenarios plus durable restart. No account was contacted.

Archive SHA-256:
`b1a12b09344f1ab0ff6b486baccbeeb55c03226ecfae994dd4ff31794fea0826`.
Local evidence: `.research-output/data-intake-verification.log` and
`.research-output/demo-sjk83uai/summary.json`. Code review identified malformed
compressed data escaping as a runtime exception; reproduced and fixed with a
regression asserting input error/exit 2. Follow-up review approved the fix.

Source input examples are invented. M2's reviewed historical dataset, provider
license evidence, exchange-calendar review and calibrated costs remain outstanding.
