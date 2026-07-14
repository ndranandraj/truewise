"""Download the current College Scorecard Field-of-Study bulk file.

Runs where there is open network (your Mac, or GitHub Actions) — NOT in the
restricted build sandbox. It:

  1. reads the Scorecard data home and finds the current "Most Recent ... Field
     of Study" .zip link (date-stamped, changes each release),
  2. downloads it,
  3. saves a DATED raw copy to archive/fvt/<YYYY-MM-DD>/ — this dated copy is
     snapshot #1 of the FVT/GE Monitor (a source ED itself does not preserve),
  4. extracts the CSV(s) into data/raw/ for the loader.

Usage (run from the repo root):
    python -m pipeline.download
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import zipfile
from pathlib import Path

import requests

from pipeline.config import ARCHIVE_DIR, RAW_DIR, SCORECARD_DATA_HOME

FOS_LINK_RE = re.compile(
    r'href="(?P<url>[^"]*Most-Recent-Cohorts-Field-of-Study[^"]*\.zip)"',
    re.IGNORECASE,
)


def find_field_of_study_url() -> str:
    """Parse the current Field-of-Study bulk .zip URL from the data home page."""
    resp = requests.get(SCORECARD_DATA_HOME, timeout=60)
    resp.raise_for_status()
    match = FOS_LINK_RE.search(resp.text)
    if not match:
        raise SystemExit(
            "Could not find the Field-of-Study download link on "
            f"{SCORECARD_DATA_HOME}. The page layout may have changed; update FOS_LINK_RE."
        )
    return match.group("url")


def download(url: str, dest: Path, chunk: int = 1 << 20) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for block in resp.iter_content(chunk_size=chunk):
                fh.write(block)


def main() -> None:
    today = dt.date.today().isoformat()
    url = find_field_of_study_url()
    filename = url.rsplit("/", 1)[-1]

    snapshot_dir = ARCHIVE_DIR / today
    snapshot_zip = snapshot_dir / filename
    print(f"Field-of-Study file: {url}")
    print(f"Saving dated snapshot -> {snapshot_zip}")
    download(url, snapshot_zip)

    # Record provenance alongside the snapshot.
    (snapshot_dir / "SOURCE.txt").write_text(
        f"source_url: {url}\ndownloaded_utc: {dt.datetime.utcnow().isoformat()}Z\n"
    )

    # Extract CSV(s) into data/raw/ for the loader (kept out of git via .gitignore).
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snapshot_zip) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if not members:
            raise SystemExit(f"No CSV found inside {snapshot_zip}")
        for member in members:
            target = RAW_DIR / Path(member).name
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            print(f"Extracted -> {target}")

    print("\nDone. Next: python -m pipeline.build_spine")


if __name__ == "__main__":
    main()
