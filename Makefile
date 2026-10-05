PYTHON ?= python3

.PHONY: test check build demo
test:
	$(PYTHON) -m unittest discover -s tests -v

check: test
	$(PYTHON) -m compileall -q quant_research quant_control quant_local quant_data quant_view quant_session quant_economics scripts tests
	git diff --check

build:
	$(PYTHON) scripts/build.py

demo:
	$(PYTHON) scripts/demo.py
