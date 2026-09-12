"""The orphan guard's failure modes.

`prune_orphans` deletes pre-rendered pages, so the expensive mistake is not missing an orphan, it
is reporting a clean tree when the build is simply incomplete. Every missing input must raise
rather than return an empty list. These build tiny fake site trees so each branch is exercised
without a real build.
"""

from __future__ import annotations

import json

import pytest

from pipeline.build_stats_exposure import PUBLISHED_FINDINGS
from pipeline.prune_orphans import find_orphans

FINDING = PUBLISHED_FINDINGS[0]


def _site(
    tmp_path,
    *,
    slugs=("alpha-college",),
    findings=(FINDING,),
    index=True,
    slug_map=True,
    cards=None,
):
    """A minimal site tree: a college dir per slug, a findings dir per finding, plus the map.

    `cards` is an optional {area: [stem, ...]} of social cards to place under site/og/.
    """
    site = tmp_path / "site"
    college, found = site / "college", site / "findings"
    college.mkdir(parents=True)
    for s in slugs:
        (college / s).mkdir()
        (college / s / "index.html").write_text("<html></html>")
    if slug_map:
        (college / "slug-map.json").write_text(json.dumps({str(i): s for i, s in enumerate(slugs)}))
    if findings is not None:
        found.mkdir(parents=True)
        for f in findings:
            (found / f).mkdir()
            (found / f / "index.html").write_text("<html></html>")
        if index:
            (found / "index.html").write_text("<html></html>")
    for area, stems in (cards or {}).items():
        d = site / "og" / area
        d.mkdir(parents=True, exist_ok=True)
        for stem in stems:
            (d / f"{stem}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return site


def test_a_card_without_a_published_route_is_an_orphan(tmp_path):
    """Cards are PNGs, not directories, so the page sweep never saw them. Ten retired college
    cards were still returning 200 on a preview while their pages correctly 404'd, which is worse
    than a stale page: a card is what gets unfurled into someone's timeline."""
    site = _site(tmp_path, cards={"college": ["alpha-college", "retired-college"]})
    assert find_orphans(site) == ["/og/college/retired-college.png"]


def test_a_retired_page_and_its_card_are_both_found_in_one_pass(tmp_path):
    """The card authority is the slug map, not the directories on disk. When it was the disk, a
    retired page and its card needed TWO runs: the first deleted the page, and only then did the
    card look orphaned. Authorities do not move when the first orphan is removed."""
    site = _site(tmp_path, cards={"college": ["alpha-college", "retired-college"]})
    (site / "college" / "retired-college").mkdir()  # page still present alongside its card
    (site / "college" / "retired-college" / "index.html").write_text("<html></html>")
    assert find_orphans(site) == [
        "/college/retired-college/",
        "/og/college/retired-college.png",
    ]


def test_findings_cards_use_the_published_list(tmp_path):
    site = _site(tmp_path, cards={"findings": [FINDING, "data-audit"]})
    assert find_orphans(site) == ["/og/findings/data-audit.png"]


def test_underscore_prefixed_cards_are_left_alone(tmp_path):
    """A leading underscore marks a non-route asset rather than a stale one."""
    site = _site(tmp_path, cards={"college": ["alpha-college", "_sample"]})
    assert find_orphans(site) == []


def test_clean_tree_reports_no_orphans(tmp_path):
    assert find_orphans(_site(tmp_path)) == []


def test_finds_orphans_in_both_trees(tmp_path):
    site = _site(tmp_path)
    (site / "college" / "alpha-college-mn").mkdir()
    (site / "findings" / "data-audit").mkdir()
    assert find_orphans(site) == ["/college/alpha-college-mn/", "/findings/data-audit/"]


def test_missing_findings_tree_is_an_error_not_a_pass(tmp_path):
    """The 2026-09-02 review caught this: skipping an absent findings tree reported success on a
    tree that had never been built, inverting the interrupted-build guarantee."""
    site = _site(tmp_path, findings=None)
    with pytest.raises(SystemExit, match="no findings tree"):
        find_orphans(site)


def test_missing_findings_index_is_an_error(tmp_path):
    """The detail pages can exist while the build died before writing the index."""
    site = _site(tmp_path, index=False)
    with pytest.raises(SystemExit, match="no findings index"):
        find_orphans(site)


def test_missing_slug_map_is_an_error(tmp_path):
    site = _site(tmp_path, slug_map=False)
    with pytest.raises(SystemExit, match="no slug map"):
        find_orphans(site)


def test_incomplete_college_tree_is_not_mistaken_for_orphans(tmp_path):
    """A mapped slug with no directory means the build stopped early. Pruning here would delete
    real pages just because the run was interrupted."""
    site = _site(tmp_path, slugs=("alpha-college", "beta-college"))
    (site / "college" / "beta-college" / "index.html").unlink()
    (site / "college" / "beta-college").rmdir()
    with pytest.raises(SystemExit, match="missing from disk"):
        find_orphans(site)


def test_incomplete_findings_tree_is_not_mistaken_for_orphans(tmp_path):
    site = _site(tmp_path, findings=())
    with pytest.raises(SystemExit, match="missing from disk"):
        find_orphans(site)
