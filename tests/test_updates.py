"""Test the /updates/ monitor log.

The page exists to make "checked monthly" verifiable, so the tests pin the two properties that
matter: entries come only from real snapshot directories (the page cannot claim a check that did
not happen), and the published SHA-256 is the real checksum of the archived file.
"""

from __future__ import annotations

import hashlib
import re

import pipeline.build_updates as bu


def _snapshot(root, date, payload=b"", source=True):
    d = root / "archive" / "fvt" / date
    d.mkdir(parents=True, exist_ok=True)
    if source:
        (d / "SOURCE.txt").write_text(
            f"snapshot_date: {date}\n"
            f"downloaded_utc: {date}T07:00:00Z\n"
            "field_of_study: https://example.gov/fos.zip\n"
            "institution: https://example.gov/inst.zip\n"
        )
    if payload:
        (d / bu.SNAPSHOT).write_bytes(payload)
    return d


def test_entries_come_only_from_real_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, "ARCHIVE", tmp_path / "archive" / "fvt")
    monkeypatch.setattr(bu, "SITE", tmp_path / "site")
    _snapshot(tmp_path, "2026-06-08")
    _snapshot(tmp_path, "2026-07-08")
    bu.main()
    html = (tmp_path / "site" / "updates" / "index.html").read_text()
    assert "2026-07-08" in html and "2026-06-08" in html
    assert "2 snapshots recorded" in html
    # Newest first.
    assert html.index("2026-07-08") < html.index("2026-06-08")
    # Provenance is shown, so a reader can go check the source.
    assert "https://example.gov/fos.zip" in html


def test_published_checksum_is_the_real_one(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, "ARCHIVE", tmp_path / "archive" / "fvt")
    monkeypatch.setattr(bu, "SITE", tmp_path / "site")
    # A real parquet so the row count and checksum are meaningful.
    import duckdb

    d = _snapshot(tmp_path, "2026-07-08")
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT 1 AS a")
    con.execute(f"COPY t TO '{d / bu.SNAPSHOT}' (FORMAT PARQUET)")

    bu.main()
    html = (tmp_path / "site" / "updates" / "index.html").read_text()
    published = re.search(r"SHA-256 ([a-f0-9]{64})", html).group(1)
    actual = hashlib.sha256((d / bu.SNAPSHOT).read_bytes()).hexdigest()
    assert published == actual, "published checksum must match the archived file"
    assert "1 program rows" in html or "1 program row" in html


def test_no_snapshots_says_so_rather_than_implying_a_check(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, "ARCHIVE", tmp_path / "archive" / "fvt")
    monkeypatch.setattr(bu, "SITE", tmp_path / "site")
    bu.main()
    html = (tmp_path / "site" / "updates" / "index.html").read_text()
    assert "No snapshots recorded yet" in html
