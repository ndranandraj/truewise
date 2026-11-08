"""Build only the two pages tests/sectnav_focus.js walks: the FVT/GE finding and UCLA's profile.

    python -m tests.build_sectnav_fixture
    node tests/sectnav_focus.js

The production renderers write into site/ from the committed parquets, so the section links, the
header and the stylesheets are the real ones. It takes seconds, so the browser check can run on
a pull request with no publish step and no full site build (review of 5 November 2026). The deploy job
still runs the same check on the full build. This is layout evidence only: it says nothing about the
figures on either page.
"""

from __future__ import annotations

import json
import shutil

import duckdb

from pipeline import build_components, build_fvtge
from pipeline.build_canonical_profiles import LIVE_STATIC_ROWS, canonical_page
from pipeline.build_college_pages import build_slugs, profile_meta, qualifying_schools
from pipeline.build_profile_pilot import all_profiles
from pipeline.build_site import build_model
from pipeline.config import ROOT

UCLA = "110662"
UCLA_NAME = "University of California-Los Angeles"
UCLA_SLUG = "university-of-california-los-angeles"


def main() -> None:
    staged = ROOT / "data" / "parquet"
    staged.mkdir(parents=True, exist_ok=True)
    for name in ("value_check.parquet", "institutions.parquet", "careers_demand.parquet"):
        shutil.copyfile(ROOT / "published" / name, staged / name)

    build_components.build(False)
    con = duckdb.connect()
    schools = qualifying_schools(build_model(con)[0])
    slugs = build_slugs(schools)
    profiles = all_profiles(con)

    school = schools[UCLA]
    if school["name"] != UCLA_NAME or slugs[UCLA] != UCLA_SLUG:
        raise SystemExit(f"{UCLA} is {school['name']} at {slugs[UCLA]}: the fixture has moved")
    pmeta, rows = profiles[UCLA]
    meta = profile_meta(school, pmeta, True)
    page, tail = canonical_page(
        meta, rows, slugs[UCLA], school.get("threshold"), LIVE_STATIC_ROWS, school.get("net_price")
    )
    folder = ROOT / "site" / "college" / slugs[UCLA]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page)
    if tail:
        (folder / "programs-tail.json").write_text(tail)
    (folder.parent / "slug-map.json").write_text(json.dumps(slugs, separators=(",", ":")))

    build_fvtge.main()
    print(f"Built /college/{slugs[UCLA]}/ and /findings/{build_fvtge.SLUG}/ under site/")


if __name__ == "__main__":
    main()
