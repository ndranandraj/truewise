"""Dates in the sitemaps and a year's cache for fingerprinted files (Prototype S).

What these guard:
  * a lastmod that is not honest: the build date, or a date on a page with no source for one;
  * a family date in the future, or one that hides a newer data release;
  * a year-cached file referenced without its current hash, which would serve an old file for a year;
  * a year-long cache on a file that is not fingerprinted.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import pipeline.build_sitemap as bsm
import pipeline.version_assets as va
from pipeline.build_canonical_profiles import SCORECARD_RELEASE
from pipeline.build_fvtge import UPDATED_ON

ROOT = Path(__file__).resolve().parent.parent
RELEASE = bsm._iso(SCORECARD_RELEASE)


def _site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    for rel in (
        "index.html",
        "methodology/index.html",
        "college/baylor-university/index.html",
        "colleges/tx/index.html",
        "majors/accounting/index.html",
        "lists/highest-paying-majors/index.html",
        "findings/fvtge-reporting/index.html",
        "findings/stats-grad-exposure/index.html",
    ):
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text("<html></html>")
    return site


def _dates(site: Path, family: str) -> dict[str, str | None]:
    text = (site / f"sitemap-{family}.xml").read_text()
    return {
        loc: (mod or None)
        for loc, mod in re.findall(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", text)
    }


# --- Dates ------------------------------------------------------------------------------------------


def test_each_address_carries_only_an_honest_date(tmp_path, monkeypatch):
    site = _site(tmp_path)
    monkeypatch.setattr(bsm, "SITE", site)
    monkeypatch.setattr(bsm, "FAMILY_UPDATED", dict.fromkeys(bsm.FAMILY_UPDATED, ""))
    bsm.main()
    core = _dates(site, "core")
    assert core and all(d is None for d in core.values()), "hand-written pages carry no date"
    for family in ("college", "colleges", "majors", "lists"):
        got = set(_dates(site, family).values())
        assert got == {RELEASE}, f"{family} carries {got}, not the release date"
    findings = _dates(site, "findings")
    assert findings["https://truewise.dev/findings/fvtge-reporting/"] == bsm._iso(UPDATED_ON)
    assert findings["https://truewise.dev/findings/stats-grad-exposure/"] == RELEASE
    # Never the build date (unless a source date happens to be today).
    sources = {RELEASE, bsm._iso(UPDATED_ON)}
    everywhere = "".join(p.read_text() for p in site.glob("sitemap-*.xml"))
    assert set(re.findall(r"<lastmod>([^<]+)</lastmod>", everywhere)) <= sources
    assert "<lastmod>" not in (site / "sitemap.xml").read_text(), "the index itself carries none"


def test_a_family_date_moves_the_family_and_never_hides_a_newer_release(tmp_path, monkeypatch):
    site = _site(tmp_path)
    monkeypatch.setattr(bsm, "SITE", site)
    later = (date.fromisoformat(RELEASE) + timedelta(days=30)).isoformat()
    earlier = (date.fromisoformat(RELEASE) - timedelta(days=30)).isoformat()
    monkeypatch.setattr(
        bsm, "FAMILY_UPDATED", {"college": later, "colleges": earlier, "majors": "", "lists": ""}
    )
    bsm.main()
    assert set(_dates(site, "college").values()) == {later}
    assert set(_dates(site, "colleges").values()) == {RELEASE}, "the release is later: it wins"
    assert set(_dates(site, "majors").values()) == {RELEASE}


def test_a_date_in_the_future_or_not_a_date_stops_the_build(monkeypatch):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setattr(bsm, "FAMILY_UPDATED", {"college": tomorrow})
    with pytest.raises(SystemExit, match="after today"):
        bsm.lastmods()
    monkeypatch.setattr(bsm, "FAMILY_UPDATED", {"college": "last Tuesday"})
    with pytest.raises(SystemExit, match="not a date"):
        bsm.lastmods()


def test_a_data_family_the_builder_does_not_name_still_carries_the_release(tmp_path, monkeypatch):
    # The major-and-degree pages (#23) arrive as a family of their own; they are data pages too.
    site = _site(tmp_path)
    monkeypatch.setattr(bsm, "SITE", site)
    monkeypatch.setattr(bsm, "FAMILY_UPDATED", {})
    bsm.main()
    assert set(_dates(site, "college").values()) == {RELEASE}
    dates = bsm.lastmods()
    assert dates.get("major-degrees", dates["data"]) == RELEASE
    assert dates["core"] is None


def test_the_committed_family_dates_are_valid():
    families = set(getattr(bsm, "FAMILIES", [name for name, _ in bsm.SEGMENTS]))
    for family, when in bsm.FAMILY_UPDATED.items():
        assert family in families and family not in ("core", "findings"), family
        if when:
            assert bsm._iso(when) <= date.today().isoformat()


# --- Fingerprints and the year's cache ---------------------------------------------------------------


def test_scripts_are_stamped_like_stylesheets():
    html = (
        '<script defer src="/components/table.js"></script><script src="components/table.js?v=old">'
    )
    out = va.stamp_sheet(html, "components/table.js", "0123456789")
    assert out.count('components/table.js?v=0123456789"') == 2
    assert 'src="/components/table.js?v=0123456789"' in out, "a script keeps its src attribute"
    assert 'src="components/table.js?v=0123456789"' in out and "href=" not in out
    assert va.stamp_sheet(out, "components/table.js", "0123456789") == out, "idempotent"
    # A stylesheet's stamp never touches a script of the same stem, and a script uses src=.
    assert va.stamp_sheet('<link href="/components.css">', "components/table.js", "x") == (
        '<link href="/components.css">'
    )


def test_the_check_finds_every_reference_without_its_current_hash(tmp_path):
    site = tmp_path / "site"
    (site / "components").mkdir(parents=True)
    (site / "styles.css").write_text("body{}")
    (site / "components" / "table.js").write_text("1")
    s, t = va.sheet_hash("styles.css", site), va.sheet_hash("components/table.js", site)
    (site / "good.html").write_text(
        f'<link href="/styles.css?v={s}"><script src="/components/table.js?v={t}"></script>'
    )
    assert va.stale_references(site) == []
    (site / "bare.html").write_text('<script src="/components/table.js"></script>')
    (site / "old.html").write_text('<link href="styles.css?v=0000000000">')
    (site / "_proto").mkdir()
    (site / "_proto" / "x.html").write_text('<link href="/styles.css">')
    assert va.stale_references(site) == [
        "bare.html: components/table.js",
        "old.html: styles.css?v=0000000000",
    ]


def _cache_rules() -> dict[str, str]:
    text = (ROOT / "site" / "_headers").read_text()
    return {
        pat: re.search(r"Cache-Control:\s*(.+)", body).group(1).strip()
        for pat, body in re.findall(r"^(/\S*)\n((?:  .+\n?)+)", text, re.M)
        if "Cache-Control" in body
    }


def test_only_fingerprinted_files_are_kept_for_a_year():
    rules = _cache_rules()
    year = {p for p, cc in rules.items() if "immutable" in cc}
    for name in va.FINGERPRINTED:
        assert rules.get("/" + name) == "public, max-age=31536000, immutable", name
    # Fonts are named for their face and never change in place; everything else immutable must be
    # fingerprinted, so a change always reaches readers.
    assert year == {"/" + n for n in va.FINGERPRINTED} | {"/fonts/*"}
    for pat in ("/college/*", "/majors/*", "/value-check/data/*"):
        assert "immutable" not in rules[pat], f"{pat} changes in place and must not be kept a year"


def test_the_deploy_checks_the_stamps_after_stamping():
    for path in (ROOT / ".github" / "workflows" / "deploy.yml", ROOT / "preview-build.sh"):
        text = path.read_text()
        stamp = text.index("pipeline.version_assets\n")
        check = text.index("pipeline.version_assets --check")
        assert stamp < check, f"{path.name} must check after stamping"
