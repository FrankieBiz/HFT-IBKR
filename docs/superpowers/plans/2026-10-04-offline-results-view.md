# Offline results view implementation plan

1. Test minimal valid research/control reports, bad modes/non-finite chart data,
   script-breaking input and output preservation in `tests/test_results_view.py`.
2. Implement `quant_view/render.py` validation/normalization and self-contained
   `template.py`. Use existing atomic publication, no external assets.
3. Add `quant_view/__main__.py` render/loopback serve, source-only archive dispatch,
   and automatic demo rendering. Test loopback routing with an ephemeral server.
4. Run full checks/build/demo. Open the local page, inspect desktop/mobile and
   exercise cost buttons. Record evidence, update docs, commit and push.

Scope: report snapshots only. The current fixture is synthetic; no trading UI.
Progress: all four tasks implemented and reviewed. Full `make check build demo`
passed on 2026-10-04 with 154 tests, compilation and whitespace checks. The demo
generates the dashboard using bundled research and 13 synthetic state snapshots;
A03 is still checked but intentionally has no final-state report.

Archive SHA-256:
`4001e42ee2f62a82cd32a67124fe66d2bf223ccaa1d2fb5a9b71b798c72a76bd`.
Evidence: `.research-output/results-view-verification.log`,
`.research-output/demo-inw7vxyk/summary.json`, and
`.research-output/results-view-browser-check.json`. Browser verification used
installed Chrome via Python Playwright: keyboard cost switch, 390px mobile
overflow, high flat-value chart and script-breaking source string all passed;
zero page errors or external requests. Desktop screenshot is checked into
`docs/images/offline-research-dashboard.png`.

Review fixes: JavaScript-compatible numeric grammar, context-free Decimal bound
checking, representable flat-chart padding, and bounded page reads. The automatic
demo regression covers integer cost multipliers and expected configuration rejection.
The local viewer was started and opened at `http://127.0.0.1:8765`.
