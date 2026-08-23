# Truewise pipeline. Run targets from the repo root.
# The download step needs open network (your Mac or GitHub Actions), not the
# restricted build sandbox. The build/flags/test steps run anywhere.

# Python interpreter. macOS ships `python3`, not `python`; override with `make PYTHON=python`.
PYTHON ?= python3

.PHONY: install components tokens tokens-check data spine flags value-check site careers careers-demand bls k12-source k12 package-data value test test-compare test-search test-embed test-search-gold test-components lint format all

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

# 4a0) Copy the isolated component assets (components/) into the deployed site/ so the canonical
# profile and pilot can reference /components.css and /components/*.js.
components:
	$(PYTHON) -m pipeline.build_components

# Assemble a servable preview of the canonical-profile pilot (rendered pages + their assets) so it
# can be measured in a real browser (Lighthouse/axe). Prints the http.server command to run.
pilot-preview: tokens components
	$(PYTHON) -m pipeline.build_profile_pilot --preview

# 4a) Regenerate design tokens (CSS custom properties + Python colour constants) from
# design/tokens.json. Run after editing tokens.json; tokens-check fails if outputs are stale.
tokens:
	$(PYTHON) -m pipeline.build_tokens
tokens-check:
	$(PYTHON) -m pipeline.build_tokens --check

# 4b) Generate the pre-rendered HTML pages (SEO volume engine): college/state, majors, sitemap.
college-pages:
	$(PYTHON) -m pipeline.build_tokens
	$(PYTHON) -m pipeline.build_components
	$(PYTHON) -m pipeline.og_images
	$(PYTHON) -m pipeline.build_home_chart
	$(PYTHON) -m pipeline.build_college_pages
	$(PYTHON) -m pipeline.build_majors_pages
	$(PYTHON) -m pipeline.build_lists
	$(PYTHON) -m pipeline.build_stats_exposure
	$(PYTHON) -m pipeline.build_updates
	$(PYTHON) -m pipeline.build_sitemap
	$(PYTHON) -m pipeline.version_assets

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

# Headless check of the /compare/ page against the generated schools.json (needs `make site` first).
test-compare:
	node tests/compare_smoke.js

# Headless check of the college search ranking against the generated schools.json (needs `make site`).
test-search:
	node tests/search_smoke.js

# Headless check of the /embed/ widget card against the generated schools.json (needs `make site`).
test-embed:
	node tests/embed_smoke.js

# Gold-set gate for search ranking. Run BEFORE and AFTER any change to the matcher: four smoke
# queries cannot approve a ranking change, because ranking regressions are silent.
test-search-gold:
	node tests/search_gold.js

# Behavioural smokes for the Stage 3 components (jsdom; run `npm install jsdom` first).
test-components:
	node tests/components_smoke.js
	node tests/table_smoke.js
	node tests/ui_smoke.js
	node tests/integration_smoke.js
	node tests/profile_smoke.js

lint:
	ruff check . && ruff format --check .

format:
	ruff format . && ruff check --fix .

# End-to-end on a networked machine.
all: data spine flags test
