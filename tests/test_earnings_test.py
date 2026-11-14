"""The earnings-test explainer: its figures come from the summary, and it never claims ED's result."""

from __future__ import annotations

import json
import re

import pytest

import pipeline.build_earnings_test as et
import pipeline.build_sitemap as bsm

# Deliberately not the real figures: a number typed into the page by hand would not match these.
SUMMARY = {
    "programs_total": 1000,
    "programs_decided": 400,
    "programs_fail_earnings_premium": 40,
    "four_year_only": {"decided": 380, "fails": 30, "fail_rate": 0.0789},
    "cosmetology_1204": {"fails": 9, "decided": 10, "fail_rate": 0.9},
}


def _text(markup: str) -> str:
    markup = re.sub(r"<script.*?</script>|<style.*?</style>", " ", markup, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup))


def test_every_truewise_figure_comes_from_the_summary_with_its_denominator():
    text = _text(et.render_page(SUMMARY))
    assert "Of 1,000 undergraduate programs, 400 can be compared." in text
    assert "In 40 of those (10.0%)" in text
    # The horizon stays beside the figure, and so does the four-year-only count.
    assert "four years after finishing where ED publishes them and one year otherwise" in text
    assert "30 of 380 (7.9%)" in text
    assert "the other 600 programs ED publishes no earnings" in text


def test_a_missing_figure_stops_the_build_rather_than_printing_a_guess():
    broken = {k: v for k, v in SUMMARY.items() if k != "four_year_only"}
    with pytest.raises(KeyError):
        et.render_page(broken)


def test_no_program_has_been_tested_is_in_the_key_box_not_behind_a_control():
    html = et.render_page(SUMMARY)
    box = html.split('<div class="kf"', 1)[1].split("</div>", 1)[0]
    assert "No program has been tested yet." in box
    assert "1 July 2027" in box
    # Nothing that changes the meaning of the page's claim sits only inside an expandable section.
    for block in re.findall(r"<details.*?</details>", html, flags=re.S):
        assert "No program has been tested" not in block


def test_the_comparison_is_called_truewises_and_never_eds_result():
    text = _text(et.render_page(SUMMARY)).replace("&rsquo;", "'")
    assert "It is our calculation. It is not ED's result" in text
    assert "does not say which programs will pass or fail" in text
    assert "the two are not comparable" in text


def test_the_cosmetology_figure_carries_the_tipped_jobs_rule_beside_it():
    html = et.render_page(SUMMARY)
    para = re.search(r'<p class="caveat">.*?</p>', html, flags=re.S).group(0)
    text = _text(para)
    assert "9 of 10 undergraduate cosmetology programs with published earnings (90%)" in text
    assert "not failed in the first rounds" in text


def test_each_section_link_has_its_section():
    html = et.render_page(SUMMARY)
    for anchor, _ in et.NAV_ITEMS:
        assert f'<section id="{anchor}"' in html, f"the section list links to #{anchor}"


def test_the_page_follows_the_writing_rules():
    html = et.render_page(SUMMARY)
    assert "\u2014" not in html, "no em-dashes in Truewise writing"
    assert not re.search(r"\bn/a\b", _text(html), flags=re.I)
    assert "Not affiliated with the U.S. Department of Education" in html
    assert len(et.DESC) <= 155, "a longer description is cut in a search result"


def test_no_publication_date_is_shown_before_there_is_one(monkeypatch):
    monkeypatch.setattr(et, "PUBLISHED_ON", "")
    assert (
        "Published" not in et.render_page(SUMMARY).split('class="dateline"', 1)[1].split("</p>")[0]
    )
    monkeypatch.setattr(et, "PUBLISHED_ON", "20 Nov 2026")
    assert "Published 20 Nov 2026" in et.render_page(SUMMARY)


def test_main_writes_the_page_and_its_card_into_the_site_it_is_given(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    (site / "data" / "value_check_summary.json").write_text(json.dumps(SUMMARY))
    monkeypatch.setattr(et, "SITE", site)
    monkeypatch.setattr(et, "SUMMARY", site / "data" / "value_check_summary.json")
    et.main()
    page = (site / "earnings-test" / "index.html").read_text()
    assert '<link rel="canonical" href="https://truewise.dev/earnings-test/"' in page
    assert (site / "og" / "earnings-test.png").stat().st_size > 0


def test_main_refuses_to_run_without_the_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(et, "SITE", tmp_path)
    monkeypatch.setattr(et, "SUMMARY", tmp_path / "missing.json")
    with pytest.raises(SystemExit):
        et.main()


def test_the_page_is_in_the_sitemap_and_the_layout_check():
    assert "/earnings-test/" in bsm.STATIC
    probe = (et.ROOT / "tests" / "layout_probe.js").read_text()
    assert 'path: "/earnings-test/"' in probe, "a page outside the layout check ships unmeasured"
