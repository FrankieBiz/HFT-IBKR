#!/usr/bin/env bash
# Start in WSL/Ubuntu or another POSIX checkout; open the local browser UI.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo 'Python is missing. In Ubuntu run: sudo apt update && sudo apt install -y python3 git make tzdata ca-certificates curl' >&2
  exit 2
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 2)'; then
  echo 'This app requires Python 3.11 or later. Ubuntu 24.04 includes a suitable version.' >&2
  exit 2
fi
exec "$PYTHON" -m quant_app "$@"
