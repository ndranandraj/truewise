# Truewise pipeline. Run targets from the repo root.
# The download step needs open network (your Mac or GitHub Actions), not the
# restricted build sandbox. The build/flags/test steps run anywhere.

# Python interpreter. macOS ships `python3`, not `python`; override with `make PYTHON=python`.
PYTHON ?= python3

.PHONY: install data spine flags value-check site careers careers-demand bls k12-source k12 package-data value test lint format all

install:
	pip install -r requirements-dev.txt

# 1) Download the current Scorecard Field-of-Study file + save a dated snapshot.
data:
	$(PYTHON) -m pipeline.download

# 2) Load the CSV into DuckDB, resolve the field mapping, write Parquet.
spine:
	$(PYTHON) -m pipeline.build_spine

# 3) Compute the Value Check earnings-premium flags.
flags value-check:
	$(PYTHON) -m pipeline.value_check

# 4) Generate the static site JSON (school index + per-state program shards).
site:
	$(PYTHON) -m pipeline.build_site

# 5) Generate the Careers field-of-study data (what a major pays).
careers:
	$(PYTHON) -m pipeline.build_careers

# 5b) Download BLS/NCES sources + build the Careers demand layer (needs network).
bls:
	$(PYTHON) -m pipeline.download_bls
careers-demand:
	$(PYTHON) -m pipeline.build_careers_demand

# 5c) K-12 advanced-course access from the CRDC (needs the CRDC School CSVs locally).
k12-source:
	$(PYTHON) -m pipeline.build_k12_source
k12:
	$(PYTHON) -m pipeline.build_k12

# 6) Refresh the data bundled inside the truewise-data pip package.
package-data:
	$(PYTHON) -m pipeline.build_package_data

# Full local build (assumes `make data` already ran on a networked machine).
value: spine flags site careers package-data

test:
	pytest

lint:
	ruff check . && ruff format --check .

format:
	ruff format . && ruff check --fix .

# End-to-end on a networked machine.
all: data spine flags test
