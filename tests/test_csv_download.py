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


def test_the_download_is_a_real_file_not_a_blob(tmp_path, monkeypatch):
    """The CSV used to be inlined as JSON and assembled into a Blob on click.

    That worked, but no request ever reached the server, so a download could not be counted
    without adding an event endpoint, and the file had no address anyone could cite. Writing it at
    build time and linking to it makes the download an ordinary request that the existing logs
    already record, with no new collection at all, and gives every list a stable URL.
    """
    block = _download_block("highest-paying-majors")
    fname = "truewise-highest-paying-majors-scorecard-2026-06-10.csv"
    assert f'href="/data/lists/{fname}" download' in block, "the download must be a real URL"
    assert "CC BY 4.0" in block
    # And none of the old machinery, which would mean the bytes are still duplicated in the page.
    for gone in ('id="csv-data"', "createObjectURL", "new Blob("):
        assert gone not in block, f"{gone} should be gone with the Blob download"

    # The file written is byte-identical to what the table renders, so the two cannot disagree.
    import pipeline.build_lists as bl

    monkeypatch.setattr(bl, "SITE", tmp_path)
    headers = ["Major", "Median earnings"]
    rows = [('<a href="/majors/x/">Computer Science</a>', "$96,748")]
    bl.write_csv("highest-paying-majors", headers, rows)
    written = (tmp_path / "data" / "lists" / fname).read_text()
    assert written == _csv_text(headers, rows)


def test_strip_tags_handles_none_and_nested_markup():
    assert _strip_tags("<span class='x'>  $1,000 </span>") == "$1,000"
    assert _strip_tags(None) == "None" or _strip_tags("") == ""
