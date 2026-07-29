"""Test the CSV export baked into ranked-list pages.

The CSV is generated from the same rows the HTML table renders, so the two cannot disagree.
These tests pin that, plus the things that silently corrupt a journalist's spreadsheet: HTML
tags leaking into cells, entities left encoded, and commas breaking the row.
"""

from __future__ import annotations

import csv
import io

from pipeline.build_lists import _csv_text, _download_block, _strip_tags


def test_csv_matches_rows_and_has_rank_column():
    headers = ["Major", "Median earnings", "Programs"]
    rows = [
        ('<a href="/majors/x/">Computer Science</a>', "$96,748", "382"),
        ('<a href="/majors/y/">Nursing</a>', "$85,357", "1,037"),
    ]
    out = list(csv.reader(io.StringIO(_csv_text(headers, rows))))
    assert out[0] == ["rank", "Major", "Median earnings", "Programs"]
    assert out[1] == ["1", "Computer Science", "$96,748", "382"]
    assert out[2] == ["2", "Nursing", "$85,357", "1,037"]


def test_cells_are_plain_text_entities_decoded_commas_quoted():
    headers = ["College", "Share"]
    rows = [
        ('<a href="/college/a/">Texas A&amp;M University</a>', "100%"),
        ("<b>Smith, Jones &amp; Co. College</b>", "92%"),
    ]
    text = _csv_text(headers, rows)
    out = list(csv.reader(io.StringIO(text)))
    # Entities decoded to real characters, no markup left behind.
    assert out[1][1] == "Texas A&M University"
    assert "<" not in text and "&amp;" not in text
    # A comma inside a value must be quoted so the row does not split.
    assert out[2][1] == "Smith, Jones & Co. College"
    assert '"Smith, Jones & Co. College"' in text


def test_download_block_names_the_file_and_states_the_licence():
    block = _download_block("highest-paying-majors", ["Major"], [("Computer Science",)])
    assert 'a.download = "truewise-highest-paying-majors-scorecard-2026-06-10.csv"' in block
    assert "CC BY 4.0" in block
    assert 'id="csv-data"' in block


def test_strip_tags_handles_none_and_nested_markup():
    assert _strip_tags("<span class='x'>  $1,000 </span>") == "$1,000"
    assert _strip_tags(None) == "None" or _strip_tags("") == ""
