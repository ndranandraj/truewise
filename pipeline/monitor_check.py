"""FVT/GE Monitor: offline integrity and freshness check.

What this replaces, and why.

The monthly job used to download ED's bulk files, rebuild, and commit. It cannot: a GitHub runner
gets 403 from both `collegescorecard.ed.gov` and `ed-public-download.scorecard.network`, measured
rather than assumed by `pipeline.reachability_probe` on 2026-09-13. The block is not about identity,
since an agent naming the project, the site and the repository is refused exactly as the default
`python-requests` one was, and the same code from a home network succeeds. Both responses came from
CloudFront, which establishes that both hosts sit behind that CDN and both refuse the runner. It does
NOT establish a single shared distribution or one shared policy; they may be separate distributions
configured similarly. The operational conclusion holds either way and the architecture is not known.

So the job stops pretending to refresh and does what its name says. It monitors. Every month it
checks what is committed, without any network at all, and reports:

  * the archive is structurally sound and each snapshot names a resolvable upstream release
  * every published parquet exists, is non-empty, and matches its recorded SHA256
  * the release the published data CLAIMS matches the newest release actually archived
  * the data-quality gate still passes over the published Value Check table
  * how old the upstream release is, measured from ED's release date, not from the day someone
    last downloaded the same files again

That last distinction matters. Re-downloading an unchanged file does not make the data newer, and a
monitor that measured download recency would have reported health on 2026-09-11 purely because a
human re-fetched the identical June 10 release. Age comes from the release date encoded in the
source filename (`..._MMDDYYYY.zip`), which is ED's own stamp.

The threshold is 400 days because the Scorecard publishes roughly annually. A 45-day threshold would
fire nearly every month against a source that is current, which is how a warning becomes furniture.

Exit codes:
    0  healthy: integrity intact and the source is within the threshold
    1  needs attention: an integrity failure, or the source is older than the threshold
    2  the check could not run (a missing prerequisite rather than a finding)

Usage:
    python -m pipeline.monitor_check
    python -m pipeline.monitor_check --json report.json --markdown report.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

from pipeline.config import ARCHIVE_DIR, ROOT

PUBLISHED = ROOT / "published"
SUMS = PUBLISHED / "SHA256SUMS.txt"

# Roughly annual source, so a year plus slack. See the module docstring.
MAX_SOURCE_AGE_DAYS = 400

# ED stamps the release into the filename as MMDDYYYY: Most-Recent-Cohorts-...-Study_06102026.zip
RELEASE_IN_NAME = re.compile(r"_(\d{2})(\d{2})(\d{4})\.zip", re.IGNORECASE)


class Finding:
    """One check's outcome. `ok` False means the monitor should speak up."""

    def __init__(self, name: str, ok: bool, detail: str, blocking: bool = True):
        self.name, self.ok, self.detail, self.blocking = name, ok, detail, blocking

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "blocking": self.blocking}


def release_date_from(text: str) -> dt.date | None:
    """ED's release date, read from a bulk filename. None when no filename in `text` carries one."""
    m = RELEASE_IN_NAME.search(text)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def read_snapshots() -> list[dict]:
    """Every archived snapshot, newest first.

    Tolerates two SOURCE.txt shapes: the current one with per-file keys, and the original
    `source_url:` single-file form used on 2026-07-13. A format the project itself wrote should not
    make its own monitor fail.
    """
    out: list[dict] = []
    if not ARCHIVE_DIR.exists():
        return out
    for d in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        src = d / "SOURCE.txt"
        entry = {
            "dir": d.name,
            "path": d,
            "has_source": src.exists(),
            "release": None,
            "urls": [],
            "snapshot_parquet": (d / "value_check_snapshot.parquet"),
        }
        if src.exists():
            text = src.read_text()
            entry["urls"] = re.findall(r"https?://\S+\.zip", text)
            entry["release"] = release_date_from(text)
        out.append(entry)
    return out


def check_archive(snapshots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    if not snapshots:
        return [Finding("archive present", False, f"no snapshot directories under {ARCHIVE_DIR}")]

    bad = [s["dir"] for s in snapshots if not s["has_source"]]
    findings.append(
        Finding(
            "every snapshot records its provenance",
            not bad,
            "all snapshots carry SOURCE.txt" if not bad else f"missing SOURCE.txt: {bad}",
        )
    )

    unresolved = [s["dir"] for s in snapshots if s["has_source"] and s["release"] is None]
    findings.append(
        Finding(
            "every snapshot names a resolvable release",
            not unresolved,
            "all snapshots name a dated bulk file"
            if not unresolved
            else f"no _MMDDYYYY.zip in SOURCE.txt for: {unresolved}",
        )
    )
    # The zips themselves are gitignored, so their absence in a fresh checkout is expected and is
    # deliberately NOT a finding. Asserting on them would make the monitor fail in CI for a reason
    # that has nothing to do with the data.
    return findings


def check_published() -> list[Finding]:
    findings: list[Finding] = []
    if not SUMS.exists():
        return [Finding("checksum manifest present", False, f"{SUMS} is missing")]

    recorded: dict[str, str] = {}
    for line in SUMS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        recorded[name.strip()] = digest.strip()

    missing, mismatched, empty = [], [], []
    for name, want in recorded.items():
        f = PUBLISHED / name
        if not f.exists():
            missing.append(name)
            continue
        if f.stat().st_size == 0:
            empty.append(name)
            continue
        got = hashlib.sha256(f.read_bytes()).hexdigest()
        if got != want:
            mismatched.append(f"{name}: recorded {want[:12]}, found {got[:12]}")

    findings.append(
        Finding(
            "published files present and non-empty",
            not missing and not empty,
            f"{len(recorded)} files listed, all present"
            if not missing and not empty
            else f"missing={missing} empty={empty}",
        )
    )
    findings.append(
        Finding(
            "published files match their recorded checksums",
            not mismatched,
            f"{len(recorded) - len(missing) - len(empty)} verified"
            if not mismatched
            else "; ".join(mismatched),
        )
    )

    # Anything shipped but unlisted is unverifiable, which is worth saying rather than passing over.
    unlisted = sorted(p.name for p in PUBLISHED.glob("*.parquet") if p.name not in recorded)
    findings.append(
        Finding(
            "no published parquet is unlisted",
            not unlisted,
            "every parquet is covered by the manifest"
            if not unlisted
            else f"shipped but not checksummed: {unlisted}",
        )
    )
    return findings


def declared_release() -> tuple[str | None, list[str]]:
    """The release the built site claims, and where that claim is made.

    Returns (value, sources). More than one distinct value means the code disagrees with itself,
    which is its own finding: the constant is currently declared in two modules.
    """
    found: dict[str, list[str]] = {}
    for py in sorted((ROOT / "pipeline").glob("*.py")):
        m = re.search(r'^SCORECARD_RELEASE\s*=\s*"([\d-]+)"', py.read_text(), re.M)
        if m:
            found.setdefault(m.group(1), []).append(py.name)
    if not found:
        return None, []
    if len(found) > 1:
        return None, [f"{v} in {', '.join(names)}" for v, names in found.items()]
    value = next(iter(found))
    return value, found[value]


def check_published_matches_archive(snapshots: list[dict]) -> list[Finding]:
    """The newest published data must claim the newest release we actually hold.

    This is the check that would have caught a refresh that downloaded a new release, rebuilt
    nothing, and left the site quoting the old one.
    """
    value, sources = declared_release()
    if value is None:
        return [
            Finding(
                "the declared release is unambiguous",
                False,
                f"SCORECARD_RELEASE disagrees across modules: {sources}"
                if sources
                else "SCORECARD_RELEASE not found in pipeline/",
            )
        ]

    dated = [s for s in snapshots if s["release"]]
    if not dated:
        return [
            Finding("published matches archive", False, "no archived snapshot names a release date")
        ]
    newest = max(s["release"] for s in dated)
    ok = value == newest.isoformat()
    return [
        Finding(
            "published data claims the newest archived release",
            ok,
            f"both {value}" + f" (declared in {', '.join(sources)})"
            if ok
            else f"site says {value}, newest archived source is {newest.isoformat()}",
        )
    ]


def check_freshness(snapshots: list[dict], today: dt.date) -> tuple[Finding, int | None]:
    dated = [s for s in snapshots if s["release"]]
    if not dated:
        return Finding("source age", False, "no archived snapshot names a release date"), None
    newest = max(s["release"] for s in dated)
    age = (today - newest).days
    ok = age <= MAX_SOURCE_AGE_DAYS
    return (
        Finding(
            "upstream release is within the freshness threshold",
            ok,
            f"released {newest.isoformat()}, {age} days ago, threshold {MAX_SOURCE_AGE_DAYS}",
        ),
        age,
    )


def check_diff_readiness(snapshots: list[dict]) -> Finding:
    """Diffing needs two snapshots that are genuinely different, not two that merely exist.

    Only one `value_check_snapshot.parquet` is archived today, so the historical diff is not
    operational and should not be described as if it were. Two byte-identical snapshots would be no
    better: a diff of a file against itself is a report that nothing changed, which is true and
    worthless, and it would read exactly like a real comparison.
    """
    present = [s for s in snapshots if s["snapshot_parquet"].exists()]
    if len(present) < 2:
        return Finding(
            "historical diff is available",
            False,
            f"{len(present)} archived snapshot parquet(s); a diff needs 2. "
            "The diff is NOT operational until a second complete snapshot exists",
            blocking=False,
        )
    digests = {hashlib.sha256(s["snapshot_parquet"].read_bytes()).hexdigest() for s in present}
    if len(digests) < 2:
        return Finding(
            "historical diff is available",
            False,
            f"{len(present)} snapshots but only {len(digests)} distinct; "
            "diffing identical files would report 'no change' without having compared anything",
            blocking=False,
        )
    return Finding(
        "historical diff is available",
        True,
        f"{len(present)} snapshots, {len(digests)} distinct",
        blocking=False,
    )


def check_data_quality() -> Finding:
    """Run the existing gate over the published table, in-process, with no network."""
    try:
        import duckdb

        from analysis import validate as v
    except ImportError as exc:
        return Finding("data-quality gate", False, f"could not import the gate: {exc}")

    path = PUBLISHED / "value_check.parquet"
    if not path.exists():
        return Finding("data-quality gate", False, f"{path} is missing")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW vc AS SELECT * FROM read_parquet('{path}')")
    failed = []
    for name, fn in v.CHECKS.items():
        try:
            ok, detail = fn(con)
        except Exception as exc:  # a check that errors is a failure, not a pass
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        if not ok:
            failed.append(f"{name}: {detail}")
    return Finding(
        "data-quality gate",
        not failed,
        f"{len(v.CHECKS)} checks passed" if not failed else "; ".join(failed),
    )


def run(today: dt.date | None = None) -> tuple[list[Finding], dict]:
    today = today or dt.date.today()
    snapshots = read_snapshots()
    findings: list[Finding] = []
    findings += check_archive(snapshots)
    findings += check_published()
    findings += check_published_matches_archive(snapshots)
    fresh, age = check_freshness(snapshots, today)
    findings.append(fresh)
    findings.append(check_data_quality())
    findings.append(check_diff_readiness(snapshots))

    dated = [s["release"] for s in snapshots if s["release"]]
    summary = {
        "checked_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshots": len(snapshots),
        "newest_release": max(dated).isoformat() if dated else None,
        "source_age_days": age,
        "threshold_days": MAX_SOURCE_AGE_DAYS,
        "healthy": all(f.ok for f in findings if f.blocking),
        "findings": [f.as_dict() for f in findings],
    }
    return findings, summary


def markdown(findings: list[Finding], summary: dict) -> str:
    lines = []
    if summary["healthy"]:
        lines.append("The committed data is intact and the upstream release is current.")
    else:
        lines.append("**The monthly check found something that needs a person.**")
    lines.append("")
    lines.append(
        f"Newest archived release: **{summary['newest_release']}**, "
        f"{summary['source_age_days']} days old, threshold {summary['threshold_days']}."
    )
    lines.append("")
    lines.append("| Check | Result | Detail |")
    lines.append("|---|---|---|")
    for f in findings:
        mark = "ok" if f.ok else ("**FAIL**" if f.blocking else "not yet")
        lines.append(f"| {f.name} | {mark} | {f.detail} |")
    lines.append("")
    if not summary["healthy"]:
        lines.append(
            "This job does not download anything. A GitHub runner is refused by both Scorecard "
            "hosts, measured by `pipeline.reachability_probe`, so refreshing the data is a manual "
            "step: run `make refresh` on a machine with open network, review what it prints, and "
            "commit. This issue closes itself when the next check passes."
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, help="write the machine-readable report here")
    ap.add_argument("--markdown", type=Path, help="write the issue body here")
    args = ap.parse_args()

    try:
        findings, summary = run()
    except Exception as exc:  # a broken check is not a finding about the data
        print(f"the monitor could not run: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)

    width = max(len(f.name) for f in findings)
    for f in findings:
        mark = "ok  " if f.ok else ("FAIL" if f.blocking else "todo")
        print(f"[{mark}] {f.name:<{width}}  {f.detail}")
    print()
    print("healthy" if summary["healthy"] else "NEEDS ATTENTION")

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown(findings, summary) + "\n")

    sys.exit(0 if summary["healthy"] else 1)


if __name__ == "__main__":
    main()
