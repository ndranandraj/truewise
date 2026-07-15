"""Download the current College Scorecard bulk files (Field-of-Study + Institution).

Runs where there is open network (your Mac, or GitHub Actions), NOT in the
restricted build sandbox. For each file it:

  1. finds the current date-stamped .zip link on the Scorecard data home,
  2. downloads it,
  3. saves a DATED raw copy to archive/fvt/<YYYY-MM-DD>/, these dated copies are
     snapshot #1 of the FVT/GE Monitor (a source ED itself does not preserve),
  4. extracts the CSV into data/raw/ for the loader.

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

from pipeline.config import ARCHIVE_DIR, BULK_FILES, RAW_DIR, SCORECARD_DATA_HOME


def find_bulk_urls(page_html: str) -> dict[str, str]:
    """Resolve each configured bulk file to its current .zip URL from the data home."""
    urls: dict[str, str] = {}
    for name, needle in BULK_FILES.items():
        pattern = re.compile(rf'href="(?P<url>[^"]*{re.escape(needle)}[^"]*\.zip)"', re.IGNORECASE)
        match = pattern.search(page_html)
        if not match:
            raise SystemExit(
                f"Could not find the '{name}' download link ({needle}) on "
                f"{SCORECARD_DATA_HOME}. The page layout may have changed."
            )
        urls[name] = match.group("url")
    return urls


def download(url: str, dest: Path, chunk: int = 1 << 20) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for block in resp.iter_content(chunk_size=chunk):
                fh.write(block)


def extract_csvs(zip_path: Path, into: Path) -> list[Path]:
    into.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in (m for m in zf.namelist() if m.lower().endswith(".csv")):
            target = into / Path(member).name
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    if not out:
        raise SystemExit(f"No CSV found inside {zip_path}")
    return out


def main() -> None:
    today = dt.date.today().isoformat()
    snapshot_dir = ARCHIVE_DIR / today

    resp = requests.get(SCORECARD_DATA_HOME, timeout=60)
    resp.raise_for_status()
    urls = find_bulk_urls(resp.text)

    provenance = [f"snapshot_date: {today}", f"downloaded_utc: {dt.datetime.utcnow().isoformat()}Z"]
    for name, url in urls.items():
        filename = url.rsplit("/", 1)[-1]
        zip_path = snapshot_dir / filename
        print(f"[{name}] {url}\n  -> {zip_path}")
        download(url, zip_path)
        for csv in extract_csvs(zip_path, RAW_DIR):
            print(f"  extracted -> {csv}")
        provenance.append(f"{name}: {url}")

    (snapshot_dir / "SOURCE.txt").write_text("\n".join(provenance) + "\n")
    print("\nDone. Next: python -m pipeline.build_spine")


if __name__ == "__main__":
    main()
