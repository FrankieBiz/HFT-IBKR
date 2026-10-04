# Local ML preflight implementation plan

> **For agentic workers:** Follow the design contract and implement task-by-task;
> use test-driven-development and verification-before-completion.

**Goal:** Produce an actionable local environment report without downloads or accounts.

**Architecture:** Standard-library collector plus pure fail-closed assessment.
Optional installed PyTorch runs in a short-lived isolated child; it never blocks
or changes the trading engines. H0 model benchmarking remains a separate task.

**Tech Stack:** Python 3.11+ diagnostic runtime, unittest, subprocess, existing
atomic publication helper and deterministic zipapp builder.

## Task 1: Environment evidence and assessment

Files: create `quant_local/__init__.py`, `quant_local/preflight.py`,
`tests/test_local_preflight.py`.

- [x] Write tests for unavailable/malformed evidence and explicit deployment gates.
- [x] Run `python3 -m unittest discover -s tests -p test_local_preflight.py -v`
      and observe missing implementation failure.
- [x] Implement bounded nvidia-smi and isolated CUDA probes, metadata and assessment.
- [x] Repeat targeted tests; no unperformed measurement may pass a required gate.

## Task 2: CLI and portable artifact

Files: create `quant_local/__main__.py`; modify `scripts/build.py`,
`tests/test_build.py`, `Makefile`; extend `tests/test_local_preflight.py`.

- [x] Test blocked reports, skipped CUDA, invalid indices and existing output preservation.
- [x] Implement `preflight --output PATH [--gpu-index N] [--skip-cuda]` with
      atomic non-overwriting publication; add archive `local` dispatch.
- [x] Exercise archive outside checkout; blocked diagnostics must still produce JSON.

## Task 3: Evidence and handoff

Files: modify `README.md`, `docs/plans/quant-trading-delivery-plan.md`,
`docs/operations/offline-runbook.md`; update this progress record.

- [x] Run `make check build demo` and record exact results/artifact hash.
- [x] Run the preflight here and record actual blockers; do not call this a GPU test.
- [x] Explain the target-machine command and the outstanding model/data/adapter work.

## Progress

Implemented and independently reviewed. All tasks below are complete for the
environment diagnostic; H0's model benchmark is not implemented.

Verification on 2026-10-04: `make check build demo`, exit 0; 137 tests passed,
compilation and whitespace checks passed. Archive SHA-256:
`d7b49a8c29c2979e6bf5c219ee8a6bc3b1abf81ce3b3f22f0b7aa850c9a21f12`.
Evidence: `.research-output/local-preflight-verification.log` and
`.research-output/demo-fy9qx8ml/summary.json`. Archive preflight was tested outside
the checkout. Real child timeout and non-overwriting symlink behavior were tested.

Actual workspace report: `.research-output/workspace-local-preflight.json`;
exit 2, `blocked`, Darwin, 16 GiB RAM, no torch/Laya distributions or CUDA evidence.
This is not the user's target workstation and establishes no NVIDIA compatibility.

Next: run the diagnostic in the target Linux/WSL2 environment, then implement and
run the single-checkpoint memory/latency/fallback benchmark. Historical data
review/calibration (M2), empirical strategy evaluation (M3), Laya financial-feature
evaluation (A1), framework study (F1), and broker integration remain outstanding.
