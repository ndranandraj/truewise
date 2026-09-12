"""Scan the built site for sentinel values presented to a reader as if they were content.

Written after ZZ. 461 live pages told readers about "a typical ZZ high-school graduate": ZZ is not
a state, it is the source data's not-reported code, and it had been rendered as a place since the
cutover. Two expert reviews and three responsive passes over the same pages all missed it.

The class is broader than one code. Any placeholder that reaches a reader as if it were a fact
breaks the one thing this site sells, so the check is a build step rather than an afternoon's grep.

It reports rather than fails, because some hits are legitimate: the methodology page discusses the
word "null" on purpose, and a sentence may begin with "None of this school's programs...". Triage
the output; anything real gets fixed at its source and, where it is a class, guarded by a test.

Usage:
    python -m pipeline.honesty_scan          # scan site/
    python -m pipeline.honesty_scan --strict # exit 1 on any hit outside the allow list
"""

from __future__ import annotations

import argparse
import collections
import html as H
import re

from pipeline.config import ROOT

SITE = ROOT / "site"

# Text a reader should never see: a placeholder, a sentinel, or a raw code.
PATTERNS = {
    "literal null": re.compile(r"\bnull\b"),
    "literal NaN": re.compile(r"\bNaN\b|\bnan\b"),
    "literal undefined": re.compile(r"\bundefined\b"),
    "n/a": re.compile(r"\bn/a\b", re.I),
    "money sentinel": re.compile(r"\$(?:nan|None|NaN|undefined)|\$-"),
    "empty money": re.compile(r"\$(?![\d])"),
    "raw state code": re.compile(r"\bZZ\b"),
    "bare Unknown": re.compile(r"\bUnknown\b"),
    "empty parenthetical": re.compile(r"\(\s*\)|,\s*,|\bin\s*,"),
}

# Legitimate uses, checked by hand. Each needs a reason, not just a path.
ALLOW = {
    # The methodology page explains what the pipeline does with suppressed values, by name.
    ("literal null", "methodology/index.html"),
    ("n/a", "methodology/index.html"),
}


def visible_text(markup: str) -> str:
    """What a reader actually sees: no script, no style, no tags, entities resolved."""
    markup = re.sub(r"<script.*?</script>|<style.*?</style>", " ", markup, flags=re.S)
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", markup)))


def scan(site=None) -> dict[str, list[tuple[str, str]]]:
    site = site or SITE
    hits: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for path in sorted(site.rglob("*.html")):
        rel = str(path.relative_to(site))
        text = visible_text(path.read_text(errors="replace"))
        for name, rx in PATTERNS.items():
            if (name, rel) in ALLOW:
                continue
            m = rx.search(text)
            if m:
                hits[name].append((rel, text[max(0, m.start() - 60) : m.start() + 60].strip()))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 on any hit")
    args = ap.parse_args()
    if not SITE.exists():
        print("no site/ to scan; build first")
        return
    total = sum(1 for _ in SITE.rglob("*.html"))
    hits = scan()
    print(f"honesty scan: {total:,} built pages")
    found = 0
    for name in PATTERNS:
        pages = hits.get(name, [])
        found += len(pages)
        flag = "  " if not pages else "! "
        print(f"{flag}{name:<22} {len(pages):>6} pages")
        for rel, ctx in pages[:2]:
            print(f"      {rel}\n        ...{ctx}...")
    if not found:
        print("\nno sentinel values reach a reader")
    if args.strict and found:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
