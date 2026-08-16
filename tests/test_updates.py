"""Test the /updates/ monitor log.

The page exists to make "checked monthly" verifiable, so the tests pin the two properties that
matter: entries come only from real snapshot directories (the page cannot claim a check that did
not happen), and the published SHA-256 is the real checksum of the archived file.
"""

from __future__ import annotations

import hashlib
import re
import re as _re

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


def test_footer_states_the_verified_date_not_a_cadence_promise():
    """The footer used to read "checked monthly", a promise about cadence that silently becomes
    false when a run is missed (an audit found it claiming monthly checks 32 days after the last
    fetch). It must instead state the date of the newest archived check, which can only ever say
    something provable and degrades honestly on its own."""
    home = (bu.SITE / "index.html").read_text()
    assert "checked monthly" not in home, "cadence promise must not return"
    m = _re.search(r'<a href="/updates/">last verified (\d{4}-\d{2}-\d{2})</a>', home)
    assert m, "footer must state the last verified date"
    newest = bu.collect_snapshots()[0]["date"]
    assert m.group(1) == newest, f"footer says {m.group(1)}, newest archived snapshot is {newest}"


def test_stamping_the_verified_date_is_idempotent(tmp_path, monkeypatch):
    """Re-running the builder must replace the date rather than append a second one."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text('<p><a href="/updates/">checked monthly</a></p>')
    monkeypatch.setattr(bu, "SITE", site)
    snaps = [{"date": "2026-07-14"}]
    bu.stamp_last_verified(snaps)
    bu.stamp_last_verified(snaps)
    html = (site / "index.html").read_text()
    assert html.count("last verified") == 1
    assert "last verified 2026-07-14" in html
    # A newer check replaces the older stamp instead of stacking.
    bu.stamp_last_verified([{"date": "2026-09-01"}])
    html = (site / "index.html").read_text()
    assert html.count("last verified") == 1 and "2026-09-01" in html
