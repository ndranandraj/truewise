"""Guard the Stage 4.3 component serving harness.

The canonical profile references /components.css and /components/*.js, which are copied from the
isolated components/ source into the deployed site/. These assert the copier mirrors the source
exactly and covers the assets the profile needs, so a live page cannot reference a missing or stale
asset.
"""

from __future__ import annotations

from pathlib import Path

from pipeline import build_components

ROOT = Path(__file__).resolve().parent.parent


def test_copier_mirrors_source_and_check_passes():
    build_components.build(check=False)
    for src, dst in build_components._pairs():
        assert dst.exists(), f"{dst} not copied"
        assert dst.read_bytes() == src.read_bytes(), f"{dst} differs from its source"
    assert build_components.build(check=True) == 0


def test_harness_covers_the_profile_assets():
    """The canonical profile loads the table + progressive-enhancement JS and the component CSS."""
    dests = {dst.name for _, dst in build_components._pairs()}
    for needed in ("components.css", "table.js", "profile.js"):
        assert needed in dests, f"serving harness is missing {needed}"


def test_deployed_copies_are_gitignored():
    """The copies are build artifacts; the source of truth is components/. They must not be tracked."""
    gitignore = (ROOT / ".gitignore").read_text()
    assert "/site/components.css" in gitignore
    assert "/site/components/" in gitignore
