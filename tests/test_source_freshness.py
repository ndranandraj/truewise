"""The freshness check reads ED's pages. These pin how it reads them, with no network."""

from __future__ import annotations

import datetime as dt

import pytest

from pipeline import source_freshness as sf

HOME = """
<a href="https://x/downloads/College_Scorecard_Raw_Data_11022026.zip">All</a>
<a href="https://x/downloads/Most-Recent-Cohorts-Field-of-Study_10152026.zip">FoS</a>
<a href="https://x/downloads/Most-Recent-Cohorts-Institution_11022026.zip">Inst</a>
"""


def test_reads_each_bulk_files_date_from_its_link():
    assert sf.scorecard_stamps(HOME) == {
        "field_of_study": dt.date(2026, 10, 15),
        "institution": dt.date(2026, 11, 2),
    }


def test_names_every_file_newer_than_the_release_the_site_uses():
    found = sf.scorecard_newer(HOME, "2026-06-10")
    assert len(found) == 2 and "field_of_study: ED has 2026-10-15" in found[0]
    assert sf.scorecard_newer(HOME, "2026-11-02") == []
    # Only one file moved.
    assert sf.scorecard_newer(HOME, "2026-10-15") == [
        "institution: ED has 2026-11-02, the site uses 2026-10-15"
    ]


def test_a_page_it_cannot_read_is_an_error_not_a_clean_result():
    """A check must fail when it cannot measure."""
    with pytest.raises(ValueError, match="no dated link"):
        sf.scorecard_newer("<html>site redesign</html>", "2026-06-10")


FVT = """
<a href="/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx">a</a>
<a href="/sites/default/files/2026-10/FVTGEDataReportingOct082026.xlsx">b</a>
<a href="/sites/default/files/2026-10/FVTGEDataReportingOct082026.xlsx">again</a>
"""
USED = "https://fsapartners.ed.gov/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx"


def test_names_reporting_lists_other_than_the_one_the_site_uses():
    assert sf.fvtge_lists(FVT) == [
        "FVTGEDataReportingFinal.xlsx",
        "FVTGEDataReportingOct082026.xlsx",
    ]
    assert sf.fvtge_newer(FVT, USED) == [
        "FVT/GE list: ED also links FVTGEDataReportingOct082026.xlsx, "
        "the site uses FVTGEDataReportingFinal.xlsx"
    ]


def test_a_reporting_list_ed_has_removed_is_an_error():
    with pytest.raises(ValueError, match="no longer linked"):
        sf.fvtge_newer("<a href='x.xlsx'>", USED)
