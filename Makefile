# Truewise pipeline. Run targets from the repo root.
# The download step needs open network (your Mac or GitHub Actions), not the
# restricted build sandbox. The build/flags/test steps run anywhere.

.PHONY: install data spine flags value-check test lint format all

install:
	pip install -r requirements-dev.txt

# 1) Download the current Scorecard Field-of-Study file + save a dated snapshot.
data:
	python -m pipeline.download

# 2) Load the CSV into DuckDB, resolve the field mapping, write Parquet.
spine:
	python -m pipeline.build_spine

# 3) Compute the Value Check earnings-premium flags.
flags value-check:
	python -m pipeline.value_check

# Full local build (assumes `make data` already ran on a networked machine).
value: spine flags

test:
	pytest

lint:
	ruff check . && ruff format --check .

format:
	ruff format . && ruff check --fix .

# End-to-end on a networked machine.
all: data spine flags test
