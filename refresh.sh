#!/usr/bin/env bash
#
# The manual data refresh, end to end. Run from a machine with open network; a GitHub runner is
# refused by both Scorecard hosts, measured by `pipeline.reachability_probe`.
#
#   ./refresh.sh            download, rebuild, validate, diff, repackage, then report
#   ./refresh.sh --dry-run  everything except the download, using whatever is already in data/raw
#
# This exists because "run python -m pipeline.download" was being written down as though it were the
# refresh. It is step one of seven. Downloading alone leaves the parquets, the published package, the
# checksums and the dated snapshot all describing the previous release, and the site still quoting it.
#
# Nothing here commits. It ends by printing what changed and what to review, because a data refresh
# is a thing a person should look at before it ships, not a thing a script should decide is fine.

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
note() { printf '    %s\n' "$1"; }

BEFORE_RELEASE="$(grep -oE '^SCORECARD_RELEASE = "[0-9-]+"' pipeline/build_package_data.py | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')"
step "Before: the site claims release $BEFORE_RELEASE"

# 1. Fetch. The only step that needs network, and the only one a runner cannot do.
if [ "$DRY" = "1" ]; then
  step "1/7 Download: SKIPPED (--dry-run), using the existing data/raw"
else
  step "1/7 Download the current bulk files, and archive a dated snapshot"
  $PYTHON -m pipeline.download
fi

# 2 and 3. Rebuild the warehouse from the CSVs, then recompute the earnings-premium flags. Step 3
# also writes the dated value_check_snapshot.parquet, which is what makes a future diff possible.
step "2/7 Rebuild the spine from the raw CSVs"
$PYTHON -m pipeline.build_spine

step "3/7 Recompute Value Check, and write the dated monitor snapshot"
$PYTHON -m pipeline.value_check

# 4. The gate. Before anything is packaged or published, so a bad refresh stops here rather than
# being discovered downstream.
step "4/7 Data-quality gate"
$PYTHON -m analysis.validate

# 5. What actually changed since the last archived snapshot. Skipped honestly when there is only one.
step "5/7 Diff against the previous snapshot"
if $PYTHON -m pipeline.monitor_diff; then
  :
else
  note "No comparable prior snapshot, so no diff. This is expected until two exist."
fi

# 6. Repackage. The published/ directory is the build source CI deploys from, so it has to move with
# the data or the next deploy rebuilds the site from the old release.
step "6/7 Refresh the published build-source"
$PYTHON -m pipeline.build_package_data
mkdir -p published
for f in value_check institutions careers_demand k12; do
  [ -f "data/parquet/$f.parquet" ] && cp "data/parquet/$f.parquet" "published/$f.parquet"
done

# The checksum manifest had no generator, which meant every refresh silently left it describing the
# previous files. The monitor verifies these, so a stale manifest would have it reporting corruption
# in data that was merely newer than its record.
step "7/7 Rewrite the checksum manifest"
( cd published && sha256sum *.parquet > SHA256SUMS.txt ) 2>/dev/null || \
  ( cd published && shasum -a 256 *.parquet > SHA256SUMS.txt )
cat published/SHA256SUMS.txt

step "Integrity and freshness check over the result"
$PYTHON -m pipeline.monitor_check || true

AFTER_RELEASE="$(grep -oE '^SCORECARD_RELEASE = "[0-9-]+"' pipeline/build_package_data.py | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')"

step "What to review before committing"
if [ "$BEFORE_RELEASE" = "$AFTER_RELEASE" ]; then
  cat <<EOF
    SCORECARD_RELEASE is still $AFTER_RELEASE.

    If the download brought a NEW release, this constant has to move with it, in BOTH
    pipeline/build_package_data.py and pipeline/build_canonical_profiles.py. It is declared twice,
    which is its own hazard: the monitor fails when they disagree, deliberately, because a site
    quoting one vintage while the data holds another is the kind of wrong that reads as right.
EOF
else
  note "SCORECARD_RELEASE moved $BEFORE_RELEASE -> $AFTER_RELEASE."
fi

echo
note "Files changed:"
git status --porcelain | sed 's/^/      /'
echo
cat <<'EOF'
    Look at the diff output above before committing. A refresh that changes thousands of verdicts
    is either a real revision by ED or a bug in ours, and the diff is the only place that shows
    which. Then commit archive/, published/ and any release-constant change together, so the
    snapshot, the data and the claim move in one step.
EOF
