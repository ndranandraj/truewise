"""Smoke tests for Iteration 0.

These prove the CI gate works before any real pipeline code exists:
a trivial passing test keeps `main` green, and the repo-shape test fails
loudly if the expected scaffold goes missing.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_truthy():
    """Trivial passing test so CI has something green to run on Iteration 0."""
    assert True


def test_repo_scaffold_present():
    """The core scaffold directories and entry files should exist."""
    for rel in ["pipeline", "site", "docs", "tests", "requirements.txt", "site/index.html"]:
        assert (ROOT / rel).exists(), f"missing expected path: {rel}"
