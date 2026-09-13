"""The offline monitor: does it notice, and does it refuse to claim more than it checked.

The job it replaced failed silently for two months. So the tests that matter here are the ones where
something IS wrong and the monitor has to say so, not the ones where everything is fine.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from pipeline import monitor_check as mc


def _snapshot(root, date: str, release: str = "06102026", *, source=True, parquet=False):
    d = root / date
    d.mkdir(parents=True)
    if source:
        (d / "SOURCE.txt").write_text(
            f"snapshot_date: {date}\n"
            f"downloaded_utc: 2026-01-01T00:00:00Z\n"
            f"field_of_study: https://example.test/Most-Recent-Cohorts-Field-of-Study_{release}.zip\n"
        )
    if parquet:
        (d / "value_check_snapshot.parquet").write_bytes(parquet)
    return d


def test_release_date_comes_from_eds_stamp_not_our_download_date():
    """Age must be measured from the upstream release, not from when someone last fetched it.

    Re-downloading an identical file does not make the data newer. A monitor keyed on download
    recency would have reported health on 2026-09-11 purely because a human re-fetched the same
    June 10 release, which is the precise shape of the failure this job exists to catch.
    """
    assert mc.release_date_from(
        "https://x/Most-Recent-Cohorts-Field-of-Study_06102026.zip"
    ) == dt.date(2026, 6, 10)
    # A snapshot directory named for the download date must not be mistaken for the release.
    assert mc.release_date_from("snapshot_date: 2026-09-11\n") is None
    # An impossible date is not silently coerced into a plausible one.
    assert mc.release_date_from("x_13402026.zip") is None


def test_freshness_uses_the_four_hundred_day_threshold():
    """400 days, because the Scorecard publishes roughly annually. A 45-day threshold would fire
    nearly every month against a source that is current, and a warning that is always on is
    furniture rather than a signal."""
    assert mc.MAX_SOURCE_AGE_DAYS == 400
    snaps = [{"release": dt.date(2026, 6, 10), "dir": "d", "snapshot_parquet": None}]

    ok, age = mc.check_freshness(snaps, dt.date(2027, 6, 10))  # 365 days
    assert ok.ok and age == 365, "a year-old annual release is current, not a finding"

    late, age = mc.check_freshness(snaps, dt.date(2027, 8, 1))  # 417 days
    assert not late.ok and age == 417
    assert "417 days" in late.detail


def test_it_notices_when_the_published_files_stop_matching_their_checksums(tmp_path, monkeypatch):
    """The manifest had no generator, so it silently described the previous release after every
    refresh. That is now the refresh script's job; this is the check that catches it either way."""
    pub = tmp_path / "published"
    pub.mkdir()
    good = pub / "value_check.parquet"
    good.write_bytes(b"real data")
    (pub / "SHA256SUMS.txt").write_text(
        f"{hashlib.sha256(b'real data').hexdigest()}  value_check.parquet\n"
    )
    monkeypatch.setattr(mc, "PUBLISHED", pub)
    monkeypatch.setattr(mc, "SUMS", pub / "SHA256SUMS.txt")

    assert all(f.ok for f in mc.check_published()), "a matching manifest should pass"

    good.write_bytes(b"different data")
    findings = {f.name: f for f in mc.check_published()}
    bad = findings["published files match their recorded checksums"]
    assert not bad.ok and "value_check.parquet" in bad.detail


def test_a_shipped_file_that_is_not_checksummed_is_reported(tmp_path, monkeypatch):
    """An unlisted parquet is unverifiable. Passing over it would mean the monitor's "all verified"
    covered fewer files than the site actually ships."""
    pub = tmp_path / "published"
    pub.mkdir()
    (pub / "a.parquet").write_bytes(b"a")
    (pub / "sneaky.parquet").write_bytes(b"b")
    (pub / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(b'a').hexdigest()}  a.parquet\n")
    monkeypatch.setattr(mc, "PUBLISHED", pub)
    monkeypatch.setattr(mc, "SUMS", pub / "SHA256SUMS.txt")

    f = {x.name: x for x in mc.check_published()}["no published parquet is unlisted"]
    assert not f.ok and "sneaky.parquet" in f.detail


def test_it_notices_when_the_site_claims_a_different_release_than_it_holds(tmp_path, monkeypatch):
    """A site quoting one vintage while the data holds another is the kind of wrong that reads as
    right, because both numbers look authoritative."""
    arc = tmp_path / "archive"
    arc.mkdir()
    _snapshot(arc, "2027-01-01", release="01152027")  # release 2027-01-15
    monkeypatch.setattr(mc, "ARCHIVE_DIR", arc)
    monkeypatch.setattr(mc, "declared_release", lambda: ("2026-06-10", ["fake.py"]))

    f = mc.check_published_matches_archive(mc.read_snapshots())[0]
    assert not f.ok
    assert "2026-06-10" in f.detail and "2027-01-15" in f.detail


def test_a_release_constant_declared_twice_must_agree(monkeypatch):
    """It IS declared twice, in build_package_data and build_canonical_profiles. Two sources of one
    truth is tolerable only while something checks they match."""
    value, sources = mc.declared_release()
    assert value == "2026-06-10", f"unexpected declared release: {value} from {sources}"
    assert len(sources) >= 2, "expected the constant in more than one module; the check guards that"

    monkeypatch.setattr(
        mc, "declared_release", lambda: (None, ["2026-06-10 in a.py", "2027-01-01 in b.py"])
    )
    f = mc.check_published_matches_archive([{"release": dt.date(2026, 6, 10)}])[0]
    assert not f.ok and "disagrees" in f.detail


def test_the_diff_is_not_called_available_until_two_different_snapshots_exist(
    tmp_path, monkeypatch
):
    """Only one snapshot parquet is archived, so the historical diff is not operational and must not
    be described as if it were.

    Two byte-identical snapshots are no better: diffing a file against itself reports "no change",
    which is true, worthless, and indistinguishable from a real comparison.
    """
    arc = tmp_path / "archive"
    arc.mkdir()
    monkeypatch.setattr(mc, "ARCHIVE_DIR", arc)

    _snapshot(arc, "2026-07-14", parquet=b"snapshot one")
    f = mc.check_diff_readiness(mc.read_snapshots())
    assert not f.ok and "needs 2" in f.detail
    assert not f.blocking, "an unavailable diff is a fact to report, not a failure to escalate"

    _snapshot(arc, "2026-09-11", parquet=b"snapshot one")  # identical bytes
    f = mc.check_diff_readiness(mc.read_snapshots())
    assert not f.ok and "distinct" in f.detail

    _snapshot(arc, "2027-01-01", parquet=b"genuinely different")
    assert mc.check_diff_readiness(mc.read_snapshots()).ok


def test_a_snapshot_written_in_the_old_format_does_not_break_the_monitor(tmp_path, monkeypatch):
    """2026-07-13 uses `source_url:` rather than the per-file keys. A format this project itself
    wrote should not make its own monitor fail."""
    arc = tmp_path / "archive"
    arc.mkdir()
    old = arc / "2026-07-13"
    old.mkdir()
    (old / "SOURCE.txt").write_text(
        "source_url: https://x/Most-Recent-Cohorts-Field-of-Study_06102026.zip\n"
        "downloaded_utc: 2026-07-14T06:50:17Z\n"
    )
    monkeypatch.setattr(mc, "ARCHIVE_DIR", arc)
    snaps = mc.read_snapshots()
    assert snaps[0]["release"] == dt.date(2026, 6, 10)
    assert all(f.ok for f in mc.check_archive(snaps))


def test_missing_zips_are_not_a_finding(tmp_path, monkeypatch):
    """The zips are gitignored, so a fresh CI checkout has SOURCE.txt and no archive payload.
    Asserting on them would make the monitor fail for a reason unrelated to the data."""
    arc = tmp_path / "archive"
    arc.mkdir()
    _snapshot(arc, "2026-09-11")  # SOURCE.txt only, exactly what CI sees
    monkeypatch.setattr(mc, "ARCHIVE_DIR", arc)
    assert all(f.ok for f in mc.check_archive(mc.read_snapshots()))


def test_a_snapshot_without_provenance_is_a_finding(tmp_path, monkeypatch):
    arc = tmp_path / "archive"
    arc.mkdir()
    _snapshot(arc, "2026-09-11", source=False)
    monkeypatch.setattr(mc, "ARCHIVE_DIR", arc)
    f = {x.name: x for x in mc.check_archive(mc.read_snapshots())}
    assert not f["every snapshot records its provenance"].ok


@pytest.mark.parametrize("healthy", [True, False])
def test_the_report_says_plainly_whether_a_person_is_needed(healthy):
    findings = [mc.Finding("a check", healthy, "detail here")]
    summary = {
        "healthy": healthy,
        "newest_release": "2026-06-10",
        "source_age_days": 95,
        "threshold_days": 400,
    }
    body = mc.markdown(findings, summary)
    if healthy:
        assert "intact" in body and "needs a person" not in body
    else:
        assert "needs a person" in body
        # And it must point at the manual path, since the job itself cannot fetch.
        assert "make refresh" in body
