#!/usr/bin/env bash
#
# Build the preview exactly the way the deploy workflow builds production, then run the gates that
# would block a deploy. One command, so there is nothing to paste and no comment can become an
# argument: handing this sequence over as a paste-block once fed a trailing comment to
# `slug_registry --check` as arguments, which made the URL-contract gate error out instead of run.
#
#   ./preview-build.sh            full clean build, then the gates
#   ./preview-build.sh --serve    the same, then serve site/ on http://localhost:8787
#
# Two things this deliberately does NOT do, because they belong to deploying rather than previewing:
# it does not inject or strip the Cloudflare Web Analytics beacon, and it does not copy the parquets
# into site/data/. It also cannot reproduce the Worker, so _headers, the security headers and any
# Worker-side redirect are unverifiable locally and have to be checked after the deploy.

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
SERVE=0
[ "${1:-}" = "--serve" ] && SERVE=1

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Branch and working tree"
git branch --show-current
git log --oneline -1
if [ -n "$(git status --porcelain)" ]; then
  echo "WARNING: the working tree is dirty. The preview will not match any commit." >&2
fi

# Every generated tree goes. This is the whole point: a preview built on top of an accumulated local
# tree hides staleness, which is how 2,821 scroll wrappers across 1,548 pages once went missing from
# the local build while the generators carried them correctly. All of these are gitignored, so
# nothing tracked is at risk.
step "Removing the generated trees"
rm -rf site/college site/colleges site/majors site/findings site/lists site/updates \
       site/og site/components site/components.css site/pg.css \
       site/sitemap.xml site/sitemap-0.xml site/sitemap-core.xml site/sitemap-college.xml \
       site/sitemap-colleges.xml site/sitemap-majors.xml site/sitemap-lists.xml \
       site/sitemap-findings.xml \
       site/value-check/data site/careers/data site/k12/data site/data/lists \
       site/data/value_check_summary.json
rm -f site/sitemap-*.xml

# Build from the committed source in published/, not from whatever is in data/parquet. CI does this,
# and it is what makes the preview a test of the release rather than of the local machine.
step "Staging the committed parquet source"
mkdir -p data/parquet
cp published/value_check.parquet published/institutions.parquet data/parquet/
cp published/careers_demand.parquet data/parquet/ 2>/dev/null || true
cp published/k12.parquet data/parquet/ 2>/dev/null || true
ls -la data/parquet/

step "Shard JSON, careers, K-12, summary"
$PYTHON -m pipeline.build_site
$PYTHON -m pipeline.build_careers
$PYTHON -m pipeline.build_k12
$PYTHON -m analysis.summary

# The URL contract. Fails if a qualified college has no registered slug, rather than deriving one and
# publishing a page at an address nothing links to. This is the gate that silently did not run.
step "URL contract: slug registry"
$PYTHON -m pipeline.slug_registry --check

step "Component assets, social cards, homepage chart"
$PYTHON -m pipeline.build_components
$PYTHON -m pipeline.og_images
$PYTHON -m pipeline.build_home_chart

# The long one: 6,127 profiles plus a social card each. Let it finish. Interrupting it part-way is
# exactly how a half-built tree happens, and the pages it has not reached keep their old content.
step "Pre-rendered pages"
$PYTHON -m pipeline.build_college_pages
$PYTHON -m pipeline.build_majors_pages
$PYTHON -m pipeline.build_lists
$PYTHON -m pipeline.build_stats_exposure
$PYTHON -m pipeline.build_updates
$PYTHON -m pipeline.build_sitemap
$PYTHON -m pipeline.version_assets

step "Gates that would block a deploy"
$PYTHON -m analysis.validate
$PYTHON -m pipeline.honesty_scan --strict
$PYTHON -m pipeline.prune_orphans --check
$PYTHON -m pipeline.build_components --check
$PYTHON -m pytest -q

step "Built"
printf 'college profiles : %s\n' "$(find site/college -name index.html | wc -l | tr -d ' ')"
printf 'major pages      : %s\n' "$(find site/majors -name index.html | wc -l | tr -d ' ')"
printf 'social cards     : %s\n' "$(find site/og -name '*.png' | wc -l | tr -d ' ')"
printf 'sitemap files    : %s\n' "$(ls site/sitemap*.xml 2>/dev/null | wc -l | tr -d ' ')"

if [ "$SERVE" = "1" ]; then
  step "Serving on http://localhost:8787  (ctrl-C to stop)"
  cat <<'PAGES'
Worth opening, given what this branch touched:

  /college/pennsylvania-state-university-main-campus/   the 489-programme tail: search, sort, Show all
  /careers/                                             the static core; try it with JavaScript off
  /compare/?a=223232&b=110538                           the 929px table-to-cards swap
  /college/larry-s-barber-college/                      these two descriptions must differ, by
  /college/larry-s-barber-college-il/                    programmes and recent graduates

PAGES
  cd site && exec "$PYTHON" -m http.server 8787
fi
