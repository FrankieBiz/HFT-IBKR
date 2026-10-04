PYTHON ?= python3
RUN_DIR ?= artifacts/demo

.PHONY: check test native demo research
check: test
	$(PYTHON) -m compileall -q quantlab
	git diff --check

test:
	$(PYTHON) -m unittest discover -s tests -v
	CXX="$(CXX)" ./native/build.sh

native:
	CXX="$(CXX)" ./native/build.sh

demo:
	$(PYTHON) -m quantlab demo --output "$(RUN_DIR)"

research:
	$(PYTHON) -m quantlab research --database "$(RUN_DIR)/history.sqlite" --config examples/simulation.toml --output "$(RUN_DIR)/research" --registry artifacts/research.sqlite
