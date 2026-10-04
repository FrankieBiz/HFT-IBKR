# Offline results view design

Build a self-contained read-only HTML view of completed research reports and
optional control replay reports. The user authorized autonomous building and
wants progress visible without terminal commands. It is a report viewer, with
no strategy editing, account connections, broker endpoints or order controls.

Choose static HTML with embedded bounded validated data and vanilla JavaScript;
no npm, remote fonts, CDNs or browser network dependencies. An optional loopback
server exposes only that page, rather than listing report directories. This is
simpler to audit and distribute than an app server or SPA for the current scope.

Design: a light research ledger with warm paper backgrounds, ink typography,
teal strategy and ochre benchmark lines. Show the synthetic/historical declared
kind prominently, an offline status, the date interval, net results, maximum
drawdown, trades/rejections, final cash/shares and cost scenarios. Interactive
cost selection updates chart and metrics from stored calculations, never reruns
or invents trades. A controls section shows supplied scenario IDs and final
state/reasons, explicitly describing them as synthetic replay outcomes. Include
source hashes and important limitations; do not suggest positive sample results
establish an edge. Responsive layout and keyboard-operable selection required.

`quant_view render --research PATH [--control PATH ...] --output NEW_HTML`
reads strict JSON with a 32 MiB file cap, validates supported mode/schema and
chart values, creates HTML atomically without overwrite. Escape JSON `<`, `>`,
`&` and Unicode line separators; all dynamic labels use textContent. Reject
unsupported or malformed inputs. No file uploads or remote retrieval.
`quant_view serve --page PATH --port N` binds only 127.0.0.1 and serves only `/`
or `/index.html`; other paths 404, other methods unsupported. Page is a snapshot.

Package `quant_view/{__init__,render,template,__main__}.py` is included in the
portable archive with `view` dispatch. Extend demo to generate `dashboard.html`.
Test malformed reports, script-breaking strings, output collisions, and HTTP path
restriction. Verify cost-switch interaction, chart rendering and mobile overflow
in a browser. Start and open the verified view here for the user.
