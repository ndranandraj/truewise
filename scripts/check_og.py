#!/usr/bin/env python3
"""Validate that live pages serve a real, correctly sized Open Graph card.

Social scrapers (Facebook, iMessage, LinkedIn, Slack) read the og:image / twitter:image meta
tags, then fetch that image. This checks the whole chain end to end against the live site: the
tag is present and absolute, the image returns 200 as a PNG, and it is exactly 1200x630 (the
size every major scraper crops to). Run it after a deploy to confirm scrapers see the new cards.

Usage:
    python scripts/check_og.py                      # a representative sample across page types
    python scripts/check_og.py URL [URL ...]        # specific pages
    python scripts/check_og.py --base https://staging.example.com   # point at a preview

Exit code is non-zero if any page fails, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import urllib.request
from urllib.error import HTTPError, URLError

TIMEOUT = 20
UA = {"User-Agent": "truewise-og-check/1.0"}

# One live page per card type, so a regression in any one builder is caught.
DEFAULT_PATHS = [
    "/",
    "/majors/registered-nursing-nursing-administration-nursing-research-and-clinical-nursing/",
    "/college/georgia-institute-of-technology/",
    "/lists/highest-paying-majors/",
    "/findings/stats-grad-exposure/",
]

_OG = re.compile(
    r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I
)
_TW = re.compile(
    r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', re.I
)


def _get(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 (trusted, own site)
        return r.status, r.headers.get("Content-Type", ""), r.read()


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def check(url: str) -> list[str]:
    """Return a list of problems for this page; empty means it passed."""
    problems: list[str] = []
    try:
        status, ctype, body = _get(url)
    except (HTTPError, URLError, TimeoutError) as e:
        return [f"page did not load: {e}"]
    if status != 200:
        return [f"page returned HTTP {status}"]

    html = body.decode("utf-8", "replace")
    og = _OG.search(html)
    tw = _TW.search(html)
    if not og:
        problems.append("no og:image tag")
    if not tw:
        problems.append("no twitter:image tag")
    if og and tw and og.group(1) != tw.group(1):
        problems.append("og:image and twitter:image disagree")
    if not og:
        return problems

    img_url = og.group(1)
    if not img_url.startswith("http"):
        problems.append(f"og:image is not absolute: {img_url}")
        return problems
    try:
        istatus, ictype, idata = _get(img_url)
    except (HTTPError, URLError, TimeoutError) as e:
        problems.append(f"og:image did not load: {e}")
        return problems
    if istatus != 200:
        problems.append(f"og:image returned HTTP {istatus}")
    if "image" not in ictype:
        problems.append(f"og:image content-type is {ictype!r}, not an image")
    size = _png_size(idata)
    if size is None:
        problems.append("og:image is not a PNG")
    elif size != (1200, 630):
        problems.append(f"og:image is {size[0]}x{size[1]}, expected 1200x630")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="*", help="full URLs to check (default: a sample set)")
    ap.add_argument("--base", default="https://truewise.dev", help="base URL for the sample set")
    args = ap.parse_args()

    urls = args.urls or [args.base.rstrip("/") + p for p in DEFAULT_PATHS]
    failed = 0
    for url in urls:
        problems = check(url)
        if problems:
            failed += 1
            print(f"FAIL  {url}")
            for p in problems:
                print(f"        - {p}")
        else:
            print(f"ok    {url}")
    print(f"\n{len(urls) - failed}/{len(urls)} pages have a valid 1200x630 OG card.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
