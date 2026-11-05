"""Every page and doc names the same Scorecard release as the data.

The release is a constant in pipeline/, and it is also written by hand into pages and docs. Moving
one without the others gives a page quoting one vintage over figures from another.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pipeline.build_package_data import SCORECARD_RELEASE

ROOT = Path(__file__).resolve().parents[1]
CLAIM = re.compile(r"Scorecard[^\n<]{0,60}?(20\d\d-\d\d-\d\d)|release (20\d\d-\d\d-\d\d)")


def _tracked(*globs: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", *globs], cwd=ROOT, capture_output=True, text=True)
    return [ROOT / f for f in out.stdout.split()]


def test_every_page_and_doc_names_the_current_release():
    stale = []
    for path in _tracked("site/*.html", "docs/*.md", "README.md", "DATA_SOURCES.md"):
        for m in CLAIM.finditer(path.read_text()):
            date = m.group(1) or m.group(2)
            if date != SCORECARD_RELEASE:
                stale.append(f"{path.relative_to(ROOT)}: {m.group(0)}")
    assert not stale, f"names an old release, the data is {SCORECARD_RELEASE}: {stale}"
