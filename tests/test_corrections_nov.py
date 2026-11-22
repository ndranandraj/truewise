"""Corrections found during Phase 1 (November 2026).

What these guard:
  * the high-school comparison called the federal test on graduate degree rows (major pages, Careers);
  * a major share card giving a figure with no credential;
  * the methodology's cosmetology figure without the rule's treatment of tipped jobs;
  * the counts the corrections log quotes, recomputed from the data they describe.
"""

from __future__ import annotations

import collections
import hashlib
import re
from pathlib import Path

import duckdb
import pytest

import pipeline.build_majors_pages as bm
from pipeline.build_updates import CORRECTIONS

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
GRAD = {
    "Master's Degree",
    "Doctoral Degree",
    "Graduate/Professional Certificate",
    "First Professional Degree",
    "Post-baccalaureate Certificate",
}


def _cred(credential, short, med):
    return {
        "credential": credential,
        "cred_short": short,
        "med": med,
        "programs": 10,
        "schools": 10,
        "p25": None,
        "p75": None,
        "pass_pct": 50,
        "cip": "5104",
        "cip2": "51",
        "cred": "5",
        "demand": None,
        "family": "Health Professions",
        "name": "Dentistry.",
    }


def test_the_major_page_says_the_line_is_the_federal_one_for_undergraduates_only(
    tmp_path, monkeypatch
):
    cards = []
    monkeypatch.setattr(bm, "SITE", tmp_path / "site")
    monkeypatch.setattr(bm, "render_card", lambda *a, **k: cards.append((a, k)))
    creds = [_cred("Master's Degree", "Master's", 216728.0)]
    page = bm.major_page("5104", "Dentistry.", "Health Professions", creds, "dentistry")
    assert "(the federal earnings-premium test)" not in page
    assert "the line the federal earnings-premium test uses for undergraduate programs" in page
    assert "Truewise&rsquo;s comparison, not the federal test" in page
    # The share card names the credential first, so an ellipsis cannot take it.
    (_, kwargs) = cards[0]
    assert kwargs["sub"].startswith("Master's Degree graduates")
    assert "salary" not in kwargs["sub"]


def test_careers_says_the_same():
    html = (SITE / "careers" / "index.html").read_text()
    assert "(the federal earnings-premium test)" not in html
    assert "the line the federal earnings-premium test uses for undergraduate programs" in html
    assert "Truewise's\n        comparison, not the federal test" in html


def test_the_methodology_cosmetology_figure_carries_the_tipped_jobs_rule():
    html = (SITE / "methodology" / "index.html").read_text()
    item = re.search(r"<li><b>Cosmetology\.</b>(.*?)</li>", html, re.S).group(1)
    assert "96%" in item
    assert "tipped jobs" in re.sub(r"\s+", " ", item)


def test_the_card_caption_puts_the_credential_first():
    for credential in ("Bachelor's Degree", "Undergraduate Certificate or Diploma"):
        assert bm.card_caption(credential).startswith(f"{credential} graduates, ")


JUNE_VC = "bb6e95ca619b625b773afbb9cf7a24284012fbeb8706652349071479fb0bf018"
VC = ROOT / "published" / "value_check.parquet"


@pytest.mark.skipif(
    not VC.exists() or hashlib.sha256(VC.read_bytes()).hexdigest() != JUNE_VC,
    reason="the counts are the 2026-06-10 release's",
)
def test_the_counts_in_the_corrections_reproduce_from_the_june_release(monkeypatch):
    from pipeline import build_careers

    monkeypatch.setattr(build_careers, "PARQUET_DIR", ROOT / "published", raising=False)
    fields = build_careers.build_fields(duckdb.connect())
    by_cip = collections.defaultdict(list)
    for f in fields:
        by_cip[f["cip"]].append(f)
    grad_rows = sum(1 for f in fields if f["credential"] in GRAD)
    with_grad = sum(1 for c in by_cip.values() if any(f["credential"] in GRAD for f in c))
    heads = collections.Counter(bm._headline(c)["cred_short"] for c in by_cip.values())
    assert (len(by_cip), len(fields), grad_rows, with_grad) == (291, 720, 260, 180)
    assert heads == {
        "Bachelor's": 241,
        "Master's": 22,
        "Undergrad cert": 14,
        "Associate's": 8,
        "First prof.": 6,
    }
    text = " ".join(c["body"] for c in CORRECTIONS[:2])
    for figure in ("180 of the 291", "260 of the 720", "241 of the 291", "the other 50"):
        assert figure in text, figure
    for figure in ("master's (22)", "certificate (14)", "associate's (8)", "degree (6)"):
        assert figure in text, figure
