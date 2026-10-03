"""Guard the Stage 4.3b canonical profile generator (staged).

Asserts the full canonical page carries the site chrome and the honesty rules, and that the three
pilot-review fixes (escaping, assessed-first selection, could-be-assessed label) are present.
"""

from __future__ import annotations

from pipeline.build_canonical_profiles import canonical_page
from pipeline.build_profile_pilot import DEFAULT_THRESHOLD, _row_from


def _rows(n_decided, n_insuf, fail=0, one_year=0):
    """one_year: the first `one_year` decided rows carry the 1-year horizon; the rest are 4-year.
    Insufficient rows carry horizon None, matching production (their earnings are never displayed)."""
    rows = []
    for i in range(n_decided):
        rows.append(
            {
                "program": f"Program {i}",
                "credential": "Bachelor's Degree",
                "earnings": 60000 + i,
                "premium": 20000 + i,
                "verdict": "fail" if i < fail else "pass",
                "horizon": "1yr_after_completion" if i < one_year else "4yr_after_completion",
                "debt": 20000,
                "payback": 1.5,
                "completers": 100 - i,
            }
        )
    for i in range(n_insuf):
        rows.append(
            {
                "program": f"Suppressed {i}",
                "credential": "Certificate",
                "earnings": None,
                "premium": None,
                "verdict": "insufficient",
                "horizon": None,
                "debt": None,
                "payback": None,
                "completers": 5,
            }
        )
    return rows


META = {"name": "Example University", "state": "PA", "control": "Public"}


def test_page_has_full_chrome_and_canonical():
    html, _ = canonical_page(META, _rows(3, 1), "example-university", 36498, DEFAULT_THRESHOLD)
    for needed in (
        "<!DOCTYPE html>",
        'rel="canonical" href="https://truewise.dev/college/example-university/"',
        "/components.css",
        "BreadcrumbList",
        "site-footer",
        "/components/table.js",
        "/components/profile.js",
    ):
        assert needed in html, f"canonical page missing {needed}"


def test_coverage_and_benchmark_are_honest():
    html, _ = canonical_page(META, _rows(3, 2, fail=1), "x", 36498, DEFAULT_THRESHOLD)
    assert "<b>3 of 5</b> programs could be assessed" in html
    assert "have earnings data" not in html
    assert (
        "($36,498 a year)" in html
    )  # the benchmark dollar value is stated (was missing in the pilot)
    assert "release 2026-06-10" in html  # dated source line


def test_no_verdict_school_is_truthful_not_blank():
    html, tail = canonical_page(META, _rows(0, 4), "x", 36498, DEFAULT_THRESHOLD)
    assert "No earnings verdict" in html
    assert "earnings not published" in html and "insufficient data" not in html
    # Suppressed earnings/premium/debt never render as 0; they say why the value is missing.
    for cell in ("Median earnings", "vs a high-school grad", "Median debt"):
        assert f'data-label="{cell}">0<' not in html


def test_zero_completers_is_a_real_count_but_suppressed_earnings_are_not():
    """The data distinguishes completers_count = 0 (a genuine zero) from NULL (missing). A real 0
    renders as 0; a suppressed earnings value renders as "not published". This is the unknown != 0
    rule applied per field."""
    rows = _rows(0, 1)
    rows[0]["completers"] = 0  # nobody completed recently: a real zero
    rows[0]["earnings"] = None  # earnings suppressed
    html, _ = canonical_page(META, rows, "x", 36498, DEFAULT_THRESHOLD)
    assert 'data-label="Recent completers">0<' in html  # real zero shown as 0
    assert 'data-label="Median earnings"><span class="tw-td__insuf">not published' in html


def test_names_and_island_are_safe():
    meta = {"name": "A & B <College>", "state": "PA", "control": "Public"}
    rows = _rows(1, 0)
    rows[0]["program"] = "Fish & Chips </script><script>"
    html, _ = canonical_page(meta, rows, "x", 36498, DEFAULT_THRESHOLD)
    assert "A &amp; B" in html and "<College>" not in html
    assert "Fish &amp; Chips" in html
    island = html.split('class="tw-profile-data">')[1].split("</script>")[0]
    assert "</script>" not in island and "\\u003c/script>" in island


def test_affordability_calculator_renders_from_net_price():
    """B10: given net price, the profile shows the income x years calculator, its result labelled
    with the band, and a no-JS table of every band with the average row."""
    np = {"avg": 15000, "brackets": [8000, 9000, 12000, 18000, 22000]}
    html, _ = canonical_page(META, _rows(3, 0), "x", 36498, DEFAULT_THRESHOLD, net_price=np)
    assert "What it would cost" in html
    assert 'id="c-data"' in html and 'id="c-inc"' in html and 'id="c-yrs"' in html
    assert '<p class="cost__band" id="c-band">Average for all families</p>' in html
    assert "Net price per year" in html  # no-JS fallback table
    assert "All families (average)" in html and "$15,000" in html
    # The summary's figure is labelled for all families, and the calculator never changes it.
    assert "Average net price, all families" in html


def test_no_net_price_omits_the_calculator():
    """A school with no reported net price shows no calculator, not an empty or broken one."""
    html, _ = canonical_page(META, _rows(3, 0), "x", 36498, DEFAULT_THRESHOLD, net_price=None)
    assert 'id="c-data"' not in html and "ED reports no net price for this school" in html


def test_one_year_label_and_notice_on_mixed_window():
    """A page mixing 1-year and 4-year earnings marks only its 1-year rows and carries the comparison
    warning, replacing the old contradictory 'several years out' source wording."""
    html, _ = canonical_page(META, _rows(4, 1, one_year=2), "x", 36498, DEFAULT_THRESHOLD)
    # Two 1-year rows -> two inline labels, plus one label inside the notice sentence = 3 spans.
    assert html.count('<span class="tw-oneyr">1-year earnings</span>') == 3
    assert "should not be compared as if measured at the same time" in html
    assert "several years out" not in html
    assert "measured four years after graduating where ED publishes them" in html


def test_window_notice_sits_outside_the_enhanced_mount():
    """Progressive enhancement replaces .tw-profile-static's innerHTML wholesale, so the comparison
    notice must be emitted OUTSIDE that mount or it disappears once JavaScript runs (the release-2
    preview bug). Assert the notice is positioned before the mount opens."""
    html, _ = canonical_page(META, _rows(4, 1, one_year=2), "x", 36498, DEFAULT_THRESHOLD)
    assert "should not be compared" in html
    assert html.index("should not be compared") < html.index('class="tw-profile-static"'), (
        "the notice must sit outside .tw-profile-static so it survives JS enhancement"
    )


def test_one_year_only_profile_still_gets_labels_and_notice():
    html, _ = canonical_page(META, _rows(3, 0, one_year=3), "x", 36498, DEFAULT_THRESHOLD)
    assert "should not be compared as if measured at the same time" in html
    assert html.count('<span class="tw-oneyr">1-year earnings</span>') == 3 + 1  # rows + notice


def test_four_year_only_profile_has_no_window_label_or_notice():
    html, _ = canonical_page(META, _rows(4, 1, one_year=0), "x", 36498, DEFAULT_THRESHOLD)
    assert "tw-oneyr" not in html
    assert "should not be compared" not in html


def test_insufficient_row_never_triggers_a_window_label():
    """Guard the 2,700-row hazard: an insufficient program can carry a horizon in the parquet while its
    earnings are hidden. _row_from must drop that horizon so it never labels a figure the page does not
    show, and the page must show no notice when every 1-year horizon belongs to a suppressed row."""
    rec = {
        "value_flag": "insufficient_data",
        "cip_code": "5201",
        "cip_desc": "Business.",
        "credential_desc": "Certificate",
        "earnings": None,
        "earnings_premium_state": None,
        "debt_median": None,
        "debt_payback_years": None,
        "completers_count": 5,
        "earnings_horizon": "1yr_after_completion",  # present in data, but earnings are suppressed
    }
    assert _row_from(rec)["horizon"] is None
    html, _ = canonical_page(META, [_row_from(rec)], "x", 36498, DEFAULT_THRESHOLD)
    assert "tw-oneyr" not in html and "should not be compared" not in html


def test_island_and_tail_carry_horizon_identically():
    """Static island rows and progressive-tail rows must both carry horizon, so a 1-year row loaded as
    tail row 151 is labelled exactly like static row 1."""
    import json

    html, tail = canonical_page(META, _rows(200, 0, one_year=160), "x", 36498, DEFAULT_THRESHOLD)
    island = json.loads(html.split('class="tw-profile-data">')[1].split("</script>")[0])
    programs = json.loads(tail)["programs"]
    assert all("horizon" in r for r in island["rows"]), "island rows dropped horizon"
    assert all("horizon" in r for r in programs), "tail rows dropped horizon"
    # 160 one-year rows sit assessed-first; 150 in the static island, 10 in the tail.
    assert sum(r["horizon"] == "1yr_after_completion" for r in island["rows"]) == 150
    assert sum(r["horizon"] == "1yr_after_completion" for r in programs) == 10


def test_threshold_splits_static_and_tail():
    html, tail = canonical_page(META, _rows(200, 289), "x", 36498, DEFAULT_THRESHOLD)
    import json

    assert html.count('<tr class="tw-tr') == DEFAULT_THRESHOLD
    assert f'data-remaining="{489 - DEFAULT_THRESHOLD}"' in html
    assert len(json.loads(tail)["programs"]) == 489 - DEFAULT_THRESHOLD


def test_rail_ends_before_programs_so_the_table_can_use_the_full_column():
    """Profile layout, October 2026. The rail was positioned over the whole page, which capped the
    program table at 860px: tables that needed a little more scrolled and cut off their last column
    while the space beside them stayed empty. The rail and everything above Programs now share
    .prof__top, closed before Programs, and the rail is still first in source order."""
    import re

    html, _ = canonical_page(META, _rows(3, 1, one_year=1), "x", 36498, DEFAULT_THRESHOLD)
    main = html.split('<main class="wrap art prof">', 1)[1].split("</main>", 1)[0]
    top_start = main.index('<div class="prof__top">')
    rail = main.index('<aside class="rail"')
    inner = main.index('<div class="prof__main">')
    progs = main.index('<section id="programs"')
    assert top_start < rail < inner < progs, "the rail must lead the upper block, ahead of the page"
    upper = main[top_start:progs]
    # Everything the reader meets before Programs sits in the upper block; Programs does not.
    for part in (
        '<nav class="crumbs"',
        "<h1>",
        'class="kf sum"',
        '<nav class="sectnav"',
        'id="cost"',
    ):
        assert part in upper, f"{part} left the upper block"
    assert upper.count("<div") - upper.count("</div") == 0, (
        "the upper block is not closed before Programs"
    )
    assert "has-rail" not in html, "the rail is no longer positioned over the whole page"
    assert len(re.findall(r'<aside class="rail"', html)) == 1


def test_profile_css_gives_programs_the_full_column_and_keeps_prose_measures():
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "site" / "profile.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert re.search(r"\.prof > \.prof__top,\s*\.prof > \.progs \{ max-width: none; \}", css), (
        "Programs must not be capped at the old 860px edge"
    )
    assert ".progs { max-width: 860px" not in css
    # Prose keeps its measure, at zero specificity so a child's own narrower measure still wins.
    for sel in (":where(.prof__main) > *", ":where(.progs) > h2", ":where(.progs) > p"):
        assert sel in css, f"{sel} lost its 760px measure"
    narrow = css.split("@media (max-width: 1199px)", 1)[1].split("}", 2)
    assert "display: contents" in narrow[0] + narrow[1], (
        "below 1200px the wrappers must not box the page, or the phone section nav stops sticking"
    )
    wide = css.split("@media (min-width: 1200px)", 1)[1]
    assert "grid-template-columns: minmax(0, 860px) 240px" in wide
    assert re.search(r"\.prof__top > \.rail \{[^}]*position: static", wide)
    # The column floors exist only where there is room for them.
    assert ".tw-td--program { min-width: 14em; }" in wide
    assert ".tw-td--program { min-width" not in css.split("@media (min-width: 1200px)", 1)[0]
