"""Has a federal source published something newer than what the site uses?

The monthly monitor cannot answer this. It runs on a GitHub runner, and both Scorecard hosts refuse
runners, so it only checks that the release we hold is under 400 days old. That passed while ED
published a new Field-of-Study file (15 October 2026) and Institution file (2 November 2026), and
nothing said so. Run this from a machine with open network, on its own or as the start of a refresh:

    python -m pipeline.source_freshness   # exit 1 if a source is newer, 2 if a page cannot be read

It reads two public pages and downloads no data.
"""

from __future__ import annotations

import datetime as dt
import re
import sys

import requests

from pipeline.build_canonical_profiles import SCORECARD_RELEASE
from pipeline.build_fvtge_source import SOURCE_URL as FVTGE_SOURCE_URL
from pipeline.config import BULK_FILES, SCORECARD_DATA_HOME
from pipeline.download import HEADERS

FVTGE_PAGE = (
    "https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-08-11/"
    "guidance-fvt/ge-data-reporting-stats-early-implementation-and-next-steps-publication"
)
EXIT_NEWER, EXIT_UNREADABLE = 1, 2


def scorecard_stamps(page: str) -> dict[str, dt.date]:
    """Each bulk file's date, from the stamp in its link: ..._10152026.zip is 15 October 2026."""
    out = {}
    for logical, needle in BULK_FILES.items():
        m = re.search(rf"{re.escape(needle)}_(\d{{2}})(\d{{2}})(\d{{4}})\.zip", page)
        if m:
            month, day, year = (int(x) for x in m.groups())
            out[logical] = dt.date(year, month, day)
    return out


def scorecard_newer(page: str, release: str) -> list[str]:
    """Lines naming each bulk file newer than `release`. Raises if the page lists none we expect."""
    stamps = scorecard_stamps(page)
    missing = sorted(set(BULK_FILES) - set(stamps))
    if missing:
        raise ValueError(f"no dated link for {missing}: the page layout may have changed")
    held = dt.date.fromisoformat(release)
    return [f"{k}: ED has {v}, the site uses {held}" for k, v in sorted(stamps.items()) if v > held]


def fvtge_lists(page: str) -> list[str]:
    """The reporting-list workbooks the announcement links to, in page order, without repeats."""
    names = re.findall(r'href="[^"]*/([^/"]+\.xlsx)"', page)
    return list(dict.fromkeys(names))


def fvtge_newer(page: str, source_url: str) -> list[str]:
    """Lines naming each listed workbook other than the one the site was built from."""
    current = source_url.rsplit("/", 1)[-1]
    listed = fvtge_lists(page)
    if current not in listed:
        raise ValueError(f"{current} is no longer linked: ED may have replaced it")
    return [
        f"FVT/GE list: ED also links {x}, the site uses {current}" for x in listed if x != current
    ]


def _get(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.text


def main() -> int:
    findings: list[str] = []
    unreadable = False
    for label, url, read in (
        ("College Scorecard", SCORECARD_DATA_HOME, lambda t: scorecard_newer(t, SCORECARD_RELEASE)),
        ("FVT/GE reporting list", FVTGE_PAGE, lambda t: fvtge_newer(t, FVTGE_SOURCE_URL)),
    ):
        try:
            found = read(_get(url))
        except (requests.RequestException, ValueError) as exc:
            print(f"{label}: could not check ({exc})")
            unreadable = True
            continue
        print(f"{label}: " + ("newer data published" if found else "the site is current"))
        findings += found
    for line in findings:
        print(f"  {line}")
    if findings:
        return EXIT_NEWER
    return EXIT_UNREADABLE if unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
