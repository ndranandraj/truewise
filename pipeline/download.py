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
import time
import zipfile
from pathlib import Path

import requests

from pipeline.config import ARCHIVE_DIR, BULK_FILES, RAW_DIR, SCORECARD_DATA_HOME

# Identify ourselves honestly. The 2026-09-08 refresh failed with 403 on the data home while the
# page served fine to an ordinary client: the default "python-requests/x.y" agent from a shared CI
# address is a common thing for a public site to refuse. The remedy is to say who we are and how to
# reach us, NOT to impersonate a browser. This is a small, polite, monthly read of a public federal
# dataset that the page itself invites people to download, and a site owner who wants to throttle
# or contact us can now tell exactly which client to look for.
USER_AGENT = (
    "TruewiseDataRefresh/1.0 (+https://truewise.dev; "
    "monthly College Scorecard refresh; https://github.com/ndranandraj/truewise)"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}
RETRIES = 3
BACKOFF_SECONDS = 5


def fetch(url: str, **kw):
    """GET with our identity attached, retried on transient failure.

    A block and an outage look the same at the call site and need different responses from whoever
    reads the log, so a 403 that survives the retries says so in words rather than surfacing a bare
    HTTPError from deep in requests.
    """
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=kw.pop("timeout", 60), **kw)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            last = exc
            status = exc.response.status_code if exc.response is not None else None
            if status == 403:
                raise SystemExit(
                    f"403 Forbidden from {url}.\n"
                    f"The request identified itself as: {USER_AGENT}\n"
                    "The page is public and this is a monthly read, so this is a client block\n"
                    "rather than a missing file. Check whether the host has started refusing this\n"
                    "address or agent; do not work around it by impersonating a browser."
                ) from exc
            if status is not None and status < 500:
                raise  # 404 and friends are real, and retrying will not help
        except requests.RequestException as exc:
            last = exc
        if attempt < RETRIES:
            time.sleep(BACKOFF_SECONDS * attempt)
    raise SystemExit(f"Could not reach {url} after {RETRIES} attempts: {last}")


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
    # The zip lives on a different host from the page, so it can be blocked independently; it goes
    # through the same identified, retried path.
    with fetch(url, stream=True, timeout=600) as resp:
        with open(dest, "wb") as fh:
            for block in resp.iter_content(chunk_size=chunk):
                fh.write(block)


def _is_real_csv(member: str) -> bool:
    """True for a data file, false for the macOS metadata twins zipped alongside it.

    ED's institution zip was built on a Mac, so it carries AppleDouble resource forks: a 226-byte
    `._Most-Recent-Cohorts-Institution.csv` beside the 100 MB real one. Both end in `.csv`, so both
    were extracted, and both then matched `build_spine`'s glob for the institution file.

    Nothing broke, and that is the uncomfortable part. `_find_csv` returns `hits[-1]` from a sorted
    list, and `.` sorts before `M`, so the real file won by an accident of ASCII ordering rather than
    by anything anyone decided. One `[0]` instead of `[-1]`, or a source file whose name sorts
    differently, and the pipeline would have parsed 226 bytes of resource fork as the institution
    table. Filtering here removes the trap rather than relying on the ordering that hides it.
    """
    name = Path(member).name
    return name.lower().endswith(".csv") and not name.startswith("._") and "__MACOSX" not in member


def extract_csvs(zip_path: Path, into: Path) -> list[Path]:
    into.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in (m for m in zf.namelist() if _is_real_csv(m)):
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

    resp = fetch(SCORECARD_DATA_HOME)
    urls = find_bulk_urls(resp.text)

    # Timezone-aware, because utcnow() returns a naive datetime that merely happens to hold UTC, and
    # is deprecated for exactly that reason. The trailing "Z" was already asserting an offset the
    # object did not carry, so the string was right and the value behind it was not.
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()
    provenance = [f"snapshot_date: {today}", f"downloaded_utc: {now}Z"]
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
