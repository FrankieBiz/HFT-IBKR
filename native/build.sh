#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
"${CXX:-clang++}" -std=c++20 -Wall -Wextra -Werror -pedantic -pthread -Iinclude tests/test_core.cpp -o build/test_core
"${CXX:-clang++}" -std=c++20 -Wall -Wextra -Werror -pedantic -pthread -Iinclude src/replay.cpp -o build/replay
./build/test_core
./build/replay
