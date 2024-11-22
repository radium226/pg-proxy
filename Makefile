#!/usr/bin/make -f

SHELL := bash
.SHELLFLAGS := -euEo pipefail -c

.ONESHELL:

.DEFAULT_GOAL := all


.PHONY: all
all:
	uv sync --all-packages --link-mode="copy"
	uv run pg_proxy --version


.PHONY: clean
clean:
	uv clean
	find "." -name "*.egg-info" -exec rm -Rf "{}" \;
	rm -Rf "./.venv"


.PHONY: test
test: test-pg


.PHONY: test-pg test-pg_proxy
test-pg:
	uv run pytest --capture="no" "packages/pg"


.PHONY: test-pg_proxy
test-pg_proxy:
	uv run pytest --capture="no" "packages/pg_proxy"


.PHONY: test-construct
test-construct:
	uv run pytest --capture="no" "packages/pg_proxy" -k "test_construct"