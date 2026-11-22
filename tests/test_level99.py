"""Profile headlines count certificates, associate's and bachelor's only (correction, November 2026).

What these guard:
  * a non-credential program (CREDLEV 99: teacher certification, preparatory coursework) counted in
    a profile's undergraduate headline, which the national headline never counts;
  * the search card, the share image or the search description counting differently from the page;
  * a summary that hides where the non-credential programs went;
  * the counts the corrections log quotes, recomputed from the data.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

import pipeline.build_site as bs
import pipeline.profile_layout as pl
from pipeline.build_updates import CORRECTIONS

ROOT = Path(__file__).resolve().parent.parent


def _r(verdict, level):
    return {
        "verdict": verdict,
        "grad": level in ("4", "5", "6", "7", "8"),
        "undergrad": level in ("1", "2", "3"),
        "noncredential": level == "99",
        "horizon": "4yr_after_completion",
        "program": "X",
        "credential": "Y",
        "earnings": 50000,
        "premium": 10000,
        "debt": None,
        "payback": None,
        "completers": 10,
    }


def test_the_headline_counts_certificates_associates_and_bachelors_only():
    rows = [_r("pass", "1"), _r("fail", "99"), _r("pass", "5")]
    scope, scoped = pl.headline_rows(rows)
    assert scoped and pl.counts(scope)["pass"] == 1 and pl.counts(scope)["decided"] == 1


def test_with_no_undergraduate_verdict_the_headline_never_falls_back_to_non_credential_programs():
    rows = [_r("pass", "99"), _r("pass", "99"), _r("pass", "5"), _r("insufficient", "3")]
    scope, scoped = pl.headline_rows(rows)
    assert not scoped
    assert pl.counts(scope)["decided"] == 1, "graduate verdicts only, the non-credential ones apart"
    assert "graduate programs with bachelor" in pl.rule_line(rows)


def test_a_profile_whose_only_verdicts_are_non_credential_stops_the_build():
    with pytest.raises(SystemExit, match="only verdicts are non-credential"):
        pl.headline_rows([_r("pass", "99"), _r("insufficient", "1")])


def test_the_summary_counts_without_them_and_says_where_they_are():
    meta = {"name": "Salina Area Technical College", "state": "KS", "city": "Salina"}
    rows = [_r("pass", "1"), _r("fail", "99")] + [_r("insufficient", "99")] * 3
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pl.summary(meta, rows, 34887, None)))
    assert "1 of 1 assessed undergraduate program" in text
    assert (
        "The 4 non-credential programs (teacher certification, preparatory coursework) are in the "
        "table, outside this count." in text
    )
    one = re.sub(r"<[^>]+>", " ", pl.summary(meta, [_r("pass", "1"), _r("fail", "99")], 1, None))
    assert "The 1 non-credential program (teacher certification, preparatory coursework) is in" in (
        re.sub(r"\s+", " ", one)
    )


def test_the_search_data_counts_the_same_way():
    assert [bs._level(c) for c in ("1", "2", "3", "4", "8", "99", None, "")] == [
        "ug",
        "ug",
        "ug",
        "grad",
        "grad",
        "nc",
        "nc",
        "nc",
    ]
    card = (ROOT / "site" / "value-check" / "index.html").read_text()
    assert 's.n_nc_programs ? "No undergraduate programs:" : "Graduate programs only:"' in card
    assert "${s.n_insuff_nc} non-credential" in card


def test_the_share_image_and_the_description_use_the_same_scope():
    for path in ("pipeline/build_college_pages.py", "pipeline/build_canonical_profiles.py"):
        src = (ROOT / path).read_text()
        assert "headline_rows(rows)" in src, path
        assert 'not r.get("grad")]' not in src, f"{path} still scopes by 'not graduate'"


JUNE_VC = "bb6e95ca619b625b773afbb9cf7a24284012fbeb8706652349071479fb0bf018"
VC = ROOT / "published" / "value_check.parquet"


@pytest.mark.skipif(
    not VC.exists() or hashlib.sha256(VC.read_bytes()).hexdigest() != JUNE_VC,
    reason="the counts are the 2026-06-10 release's",
)
def test_the_counts_in_the_correction_reproduce_from_the_june_release(monkeypatch):
    import duckdb

    from pipeline.build_college_pages import qualifying_schools
    from pipeline.build_profile_pilot import all_profiles

    # The committed data, so this runs on a clean checkout (CI has no data/parquet).
    monkeypatch.setattr(bs, "PARQUET_DIR", ROOT / "published")
    con = duckdb.connect()
    schools, _, _ = bs.build_model(con)
    profiles = all_profiles(con)
    changed = share = moved = 0
    for u, s in qualifying_schools(schools).items():
        rows = profiles.get(u, ({}, []))[1]
        old = pl.counts([r for r in rows if not r.get("grad")])
        if not old["decided"]:
            continue
        scope, scoped = pl.headline_rows(rows)
        new = pl.counts(scope)
        if scoped and (new["pass"], new["decided"]) == (old["pass"], old["decided"]):
            continue
        changed += 1
        if not scoped:
            moved += 1
            assert s["name"] == "Alliant International University-San Diego"
            # Its graduate verdicts alone, never its non-credential ones.
            assert (new["pass"], new["decided"]) == (14, 14)
        elif old["pass"] * new["decided"] != new["pass"] * old["decided"]:
            share += 1
        if s["name"] == "Salina Area Technical College":
            meta = {"name": s["name"], "state": s["state"], "city": s.get("city")}
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pl.summary(meta, rows, 1, None)))
            assert "1 of 1 assessed undergraduate program" in text
            assert "The 4 non-credential programs" in text
        # The search card counts what the page counts.
        ug = pl.undergrad(rows)
        assert (s["n_ug_pass"], s["n_ug_programs"]) == (pl.counts(ug)["pass"], len(ug))
    assert (changed, share, moved) == (95, 57, 1)
    body = CORRECTIONS[0]["body"]
    for figure in ("On 95", "94 now count", "share on 57", "One, whose"):
        assert figure in body, figure
