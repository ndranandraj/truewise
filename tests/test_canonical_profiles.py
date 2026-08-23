"""Guard the Stage 4.3b canonical profile generator (staged).

Asserts the full canonical page carries the site chrome and the honesty rules, and that the three
pilot-review fixes (escaping, assessed-first selection, could-be-assessed label) are present.
"""

from __future__ import annotations

from pipeline.build_canonical_profiles import canonical_page
from pipeline.build_profile_pilot import DEFAULT_THRESHOLD


def _rows(n_decided, n_insuf, fail=0):
    rows = []
    for i in range(n_decided):
        rows.append(
            {
                "program": f"Program {i}",
                "credential": "Bachelor's Degree",
                "earnings": 60000 + i,
                "premium": 20000 + i,
                "verdict": "fail" if i < fail else "pass",
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
    assert ">0<" not in html  # never a bare zero


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


def test_threshold_splits_static_and_tail():
    html, tail = canonical_page(META, _rows(200, 289), "x", 36498, DEFAULT_THRESHOLD)
    import json

    assert html.count('<tr class="tw-tr') == DEFAULT_THRESHOLD
    assert f'data-remaining="{489 - DEFAULT_THRESHOLD}"' in html
    assert len(json.loads(tail)["programs"]) == 489 - DEFAULT_THRESHOLD
