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
    assert "$36,498/yr" in html  # the benchmark dollar value is stated (was missing in the pilot)
    assert "release 2026-06-10" in html  # dated source line


def test_no_verdict_school_is_truthful_not_blank():
    html, tail = canonical_page(META, _rows(0, 4), "x", 36498, DEFAULT_THRESHOLD)
    assert (
        "no programs have enough data" in html.lower()
        or "enough data for an earnings verdict" in html
    )
    assert "insufficient data" in html
    # Suppressed earnings/premium/debt never render as 0; they say insufficient data.
    for cell in ("Median earnings", "vs a high-school grad", "Median debt"):
        assert f'data-label="{cell}">0<' not in html


def test_zero_completers_is_a_real_count_but_suppressed_earnings_are_not():
    """The data distinguishes completers_count = 0 (a genuine zero) from NULL (missing). A real 0
    renders as 0; a suppressed earnings value renders as insufficient data. This is the unknown != 0
    rule applied per field."""
    rows = _rows(0, 1)
    rows[0]["completers"] = 0  # nobody completed recently: a real zero
    rows[0]["earnings"] = None  # earnings suppressed
    html, _ = canonical_page(META, rows, "x", 36498, DEFAULT_THRESHOLD)
    assert 'data-label="Recent completers">0<' in html  # real zero shown as 0
    assert 'data-label="Median earnings"><span class="tw-td__insuf">insufficient data' in html


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
    """B10: given net price, the profile shows the income x years calculator and a no-JS fallback
    table with the average row."""
    np = {"avg": 15000, "brackets": [8000, 9000, 12000, 18000, 22000]}
    html, _ = canonical_page(META, _rows(3, 0), "x", 36498, DEFAULT_THRESHOLD, net_price=np)
    assert "What would this cost you?" in html
    assert 'id="calc-data"' in html and "calc-income" in html
    assert "Net price per year" in html  # no-JS fallback table
    assert "All families (average)" in html and "$15,000" in html


def test_no_net_price_omits_the_calculator():
    """A school with no reported net price shows no calculator, not an empty or broken one."""
    html, _ = canonical_page(META, _rows(3, 0), "x", 36498, DEFAULT_THRESHOLD, net_price=None)
    assert "What would this cost you?" not in html


def test_one_year_label_and_notice_on_mixed_window():
    """A page mixing 1-year and 4-year earnings marks only its 1-year rows and carries the comparison
    warning, replacing the old contradictory 'several years out' source wording."""
    html, _ = canonical_page(META, _rows(4, 1, one_year=2), "x", 36498, DEFAULT_THRESHOLD)
    # Two 1-year rows -> two inline labels, plus one label inside the notice sentence = 3 spans.
    assert html.count('<span class="tw-oneyr">1-year earnings</span>') == 3
    assert "should not be compared as if measured at the same time" in html
    assert "several years out" not in html
    assert "measured four years after completion where available" in html


def test_one_year_only_profile_still_gets_labels_and_notice():
    html, _ = canonical_page(META, _rows(3, 0, one_year=3), "x", 36498, DEFAULT_THRESHOLD)
    assert "should not be compared as if measured at the same time" in html
    assert html.count('<span class="tw-oneyr">1-year earnings</span>') == 3 + 1  # rows + notice


def test_four_year_only_profile_has_no_window_label_or_notice():
    html, _ = canonical_page(META, _rows(4, 1, one_year=0), "x", 36498, DEFAULT_THRESHOLD)
    assert "tw-oneyr" not in html
    assert "should not be compared" not in html
    assert "Earnings are medians measured four years after completion," in html


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
