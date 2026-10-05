# Read-only paper Gateway connection check

This checks API session establishment only. It does not request account balances,
positions, orders, prices or history, and cannot place or cancel orders. It is not
the M4 broker adapter. Keep Gateway logged into **Paper Trading** and **Read-Only
API checked**. The script cannot independently verify those Gateway settings.

## Ubuntu setup

From the checkout on branch `FrankieBiz/feat-complete-quant-research`, update with
`git pull --ff-only`. Install Ubuntu's basic environment tools if needed:

```sh
sudo apt update
sudo apt install -y python3-venv curl unzip
```

Use a separate virtual environment; the offline core still needs no packages.
Download the official **Mac/Linux SDK**, even though Gateway itself runs on Windows.
The SDK is installed in Ubuntu where this diagnostic runs. The source ZIP below
was linked as stable on the [official API page](https://interactivebrokers.github.io/)
on 2026-10-04. Its setup declares GPL-3.0-or-later and protobuf==5.29.5. No SDK source
is redistributed by this repository. Review the vendor's distribution terms for
your use. Pin this version for the diagnostic rather than substituting a similarly
named PyPI package.

```sh
python3 -m venv .gateway-venv
source .gateway-venv/bin/activate
mkdir -p .research-output/gateway-sdk
curl --fail --location --output .research-output/gateway-sdk/api.zip https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip
```

Verify the downloaded ZIP against the digest observed during implementation:

```sh
sha256sum .research-output/gateway-sdk/api.zip
```

Expected SHA-256:

```text
673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3
```

Stop if it differs. This is a locally recorded digest, not a vendor signature.
With a matching digest, extract and install the official Python client:

```sh
unzip -q .research-output/gateway-sdk/api.zip -d .research-output/gateway-sdk
python3 -m pip install ./.research-output/gateway-sdk/IBJts/source/pythonclient
```

Installation also obtains SDK dependencies/build tools from the configured Python
package index. These are optional diagnostic dependencies, not the core's runtime.
Do not rerun unzip over an existing extraction; reuse the verified source directory.

## Run on the user's machine

Keep the virtual environment activated. For the user's currently reported WSL
host IP, run:

```sh
python3 scripts/check_paper_gateway.py --host 172.30.0.1 --confirm-paper --confirm-read-only
```

The two flags acknowledge the actual Gateway settings; they do not change them.
Default port is 4002, nonzero client ID is 91 and total process deadline is 15
seconds. It opens one session and disconnects. There are no retries. If another
application uses ID 91, choose an unused ID with `--client-id N`.

Success prints only:

```json
{"server_version": 200, "status": "api_connected"}
```

The version above is illustrative. Success requires `nextValidId` and a valid
server version, then successful local disconnect. It does not certify paper mode,
account permissions, market-data entitlement, order controls or trading readiness.
Automatic account/ID callbacks and raw errors are discarded rather than printed.

Failure returns exit 2 with a fixed status: `missing_sdk`, `sdk_import_failed`,
`connection_failed`, `callback_timeout`, `process_timeout`, `disconnect_failed`,
`worker_failed`, or `invalid_worker_result`. No exception/account text is emitted.
For failures, check Gateway's status, paper login, API port and connection prompts.
The diagnostic does not disable firewall rules or add trusted IPs automatically.

The Windows host IP may change after a WSL restart. Under NAT use the host IP from
`ip route show default`; mirrored networking may instead support 127.0.0.1.
See [Microsoft's networking guide](https://learn.microsoft.com/en-us/windows/wsl/networking).

The protocol distinction is documented in [IBKR's connection guide](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/verify-api-connection):
TCP reachability alone is insufficient; nextValidId is the readiness callback.

## Validation limits

Automated tests use fake SDK callbacks and process failures, never a broker account.
The official SDK 10.50.2 and protobuf 5.29.5 were installed in an isolated local
Python 3.14 environment. Its actual protobuf decoder dispatched the readiness
callback with simulated transport; no socket was opened for that compatibility test.
No real Gateway/API connection has been performed from this development workspace.
The user must run the command on their trading computer and inspect its result.
