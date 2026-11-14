"""Links to the earnings-test explainer (Prototype K2): each says only what is true of its page."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pipeline.profile_layout as pl
from pipeline.build_college_pages import FOOTER

SITE = Path(__file__).resolve().parents[1] / "site"
LINK = '<a href="/earnings-test/">What the test is</a>'


def _row(verdict: str, grad: bool = False) -> dict:
    return {"verdict": verdict, "grad": grad, "horizon": "4yr_after_completion"}


UG_PASS, UG_FAIL, UG_NONE = _row("pass"), _row("fail"), _row("insufficient")
GRAD_PASS, GRAD_NONE = _row("pass", grad=True), _row("none", grad=True)


@pytest.mark.parametrize(
    "rows",
    [[UG_PASS], [UG_FAIL, UG_NONE], [UG_PASS, GRAD_PASS], [UG_FAIL, GRAD_NONE]],
)
def test_an_undergraduate_verdict_is_called_the_tests_comparison_and_truewises_calculation(rows):
    line = pl.rule_line(rows)
    assert "the comparison the federal earnings test makes for undergraduate programs" in line
    assert "not the Department of Education&rsquo;s result" in line


@pytest.mark.parametrize(
    "rows",
    [
        [GRAD_PASS],  # verdicts on graduate programs only
        [UG_NONE, GRAD_PASS],  # undergraduate programs listed, but none could be compared
        [GRAD_NONE],  # a graduate school with no verdict
    ],
)
def test_a_graduate_comparison_is_never_called_the_federal_test(rows):
    line = pl.rule_line(rows)
    assert "compares graduate programs with bachelor&rsquo;s degree holders" in line
    assert "This is the comparison" not in line
    assert "high-school" not in line


@pytest.mark.parametrize("rows", [[UG_NONE], [_row("nobench")], [_row("none"), GRAD_NONE]])
def test_a_profile_with_no_verdict_gets_the_link_without_a_claim_about_its_programs(rows):
    line = pl.rule_line(rows)
    assert "compares an undergraduate program&rsquo;s graduates with high-school graduates" in line
    assert "This is the comparison" not in line
    assert "calculation" not in line


def test_every_variant_has_the_one_link_and_no_em_dash():
    for rows in ([UG_PASS], [GRAD_PASS], [UG_NONE], [GRAD_NONE]):
        line = pl.rule_line(rows)
        assert line.count(LINK) == 1
        assert line.startswith('<p class="sum__rule">') and line.endswith("</p>")
        assert "\u2014" not in line


def test_the_line_sits_under_the_verdict_box_not_inside_it():
    """Inside the box it would read as part of the verdict; after the cost line it would be missed."""
    meta = {"name": "Example College", "state": "TX"}
    html = pl.summary(meta, [UG_PASS, UG_FAIL], 34809, {"avg": 21000})
    box_end = html.index("</div>")
    rule, cost = html.index('<p class="sum__rule">'), html.index('<p class="sum__cost">')
    assert box_end < rule < cost
    assert html.count("/earnings-test/") == 1


def test_value_check_links_the_explainer_under_both_copies_of_its_introduction():
    """The page has a static first view and the script's view of the same search. A link in only one
    of them appears or disappears when the script takes over."""
    page = (SITE / "value-check" / "index.html").read_text(encoding="utf-8")
    pair = re.compile(
        r'<p class="lede">.*?</p>\s*<p class="lede-rule"><a href="/earnings-test/">'
        r"How this relates to the federal earnings test</a></p>",
        re.S,
    )
    assert len(pair.findall(page)) == 2
    assert page.count('<p class="lede">') == 2


def test_the_homepage_band_links_the_explainer_beside_how_we_count():
    home = (SITE / "index.html").read_text(encoding="utf-8")
    cta = re.search(r'<p class="h-band__cta">.*?</p>', home, re.S).group(0)
    assert 'href="/methodology/">How we count</a>' in cta
    assert 'href="/earnings-test/">The federal earnings test</a>' in cta


def test_the_shared_footer_links_the_explainer():
    """The page was in the sitemap only. The footer is on every page, so no page type is left
    without a way to it (test_every_page_uses_the_one_shared_footer keeps the copies the same)."""
    research = re.search(r'<nav class="foot__group" aria-label="Research">.*?</nav>', FOOTER, re.S)
    assert '<a href="/earnings-test/">The federal earnings test</a>' in research.group(0)


def test_the_homepage_cosmetology_figure_says_the_rule_holds_tipped_jobs_out_at_first():
    """The figure sits in the band that names the federal comparison. The rule does not pass or fail
    programs for tipped jobs in its first rounds, which changes what the figure means for a
    cosmetology program, so it stays in the same sentence as the figure."""
    home = (SITE / "index.html").read_text(encoding="utf-8")
    band = re.sub(r"\s+", " ", re.search(r'<p class="h-band__body">.*?</p>', home, re.S).group(0))
    sentence = re.search(r"Cosmetology: \d+% fall short[^.]*\.", band)
    assert sentence, "the homepage band no longer gives the cosmetology figure"
    assert (
        "; the federal rule holds programs for tipped jobs out of its first rounds."
        in sentence.group(0)
    )
