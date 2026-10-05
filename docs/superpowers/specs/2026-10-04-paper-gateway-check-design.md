# Paper Gateway connection check

The user has confirmed Gateway is logged into paper trading on Windows. Ubuntu
cannot reach 127.0.0.1:4002 but can reach 172.30.0.1:4002. These are user-reported
TCP results, not evidence of an authenticated API session.

Build a standalone opt-in diagnostic using the official optional `ibapi` SDK.
Unlike a TCP probe, success requires the SDK's `nextValidId` callback and a valid
server version. It disconnects immediately afterward. No strategy, order, cancel,
market-data or account-data request is made. Automatic SDK account callbacks are
discarded. No account IDs, order IDs, raw error messages or credentials are printed.
This is a connection diagnostic, not the M4 broker adapter or trading readiness.

The command accepts only loopback/RFC1918 IPv4 literals, port 4002, a nonzero client
ID, and 1–30 second timeout. Explicit paper and read-only acknowledgements are
required before importing the SDK or opening a socket. They are user attestations;
neither paper mode nor the Gateway read-only setting is inferred from the port.
The diagnostic runs in an isolated child with a parent-enforced total timeout.
SDK logs/stdout/stderr are suppressed; only a small allowlisted JSON result crosses
the process boundary. No automatic retries, installation or model downloads.
The child repeats the CLI validation. Result parsing rejects duplicate/extra fields,
invalid versions, oversized output, and success with a failed exit. The total
deadline covers import, connect, receive and disconnect and kills/reaps a hung child.

Alternatives: a raw TCP probe is insufficient (already passed); implementing the
full order adapter now would exceed this setup step. Use the official SDK rather
than implementing the broker protocol ourselves. Core offline workflows retain
their standard-library-only dependency and do not invoke this script.

Validation uses fake SDK callbacks and subprocess failures only. Test successful
callback/disconnect, TCP-only false positives, timeout, exceptions, privacy,
endpoint restrictions, confirmation gating and malformed worker results. A real
Gateway run must occur on the user's machine; do not claim it happened here.

Primary sources checked 2026-10-04:
- https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/verify-api-connection
  distinguishes socket opening, negotiation and nextValidId session readiness.
- https://interactivebrokers.github.io/ supplies the official SDK ZIP. Stable
  source observed at downloads/twsapi_macunix.1050.02.zip; inspect its Python setup
  requirements before providing installation instructions.
- https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/
  documents paper Gateway port 4002 and Read-Only blocking API orders.
- https://learn.microsoft.com/en-us/windows/wsl/networking explains Windows-host
  IP use under WSL NAT. The host IP may change after restart.
