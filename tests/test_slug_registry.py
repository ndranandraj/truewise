"""The URL contract: a published college slug must never move.

Slugs were derived from the data, and same-name institutions were separated by the order rows
arrived in. The loading query did not order by unitid, so DuckDB could return tied rows differently
per process: twelve fresh runs gave the live mapping nine times and an alternate three times, moving
36 unitids across 18 pairs. Because the deploy has two independent slug consumers, college pages
and lists, running as separate processes, one deploy could publish a page at one slug and link to
it at another.

published/slug_registry.json now freezes the mapping. These tests hold that contract: shuffling the
input cannot change an existing URL, a retired slug is never handed to another institution, and CI
fails when a qualified school has no registered slug.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from pipeline.slug_registry import REGISTRY, assign, resolve

ROOT = Path(__file__).resolve().parent.parent


def _schools(n: int = 60) -> dict:
    """A fake cohort with deliberate name collisions, including a three-way tie."""
    out = {}
    for i in range(n):
        out[str(100000 + i)] = {
            "name": f"College {i % 12}",  # 12 distinct names over n schools -> many ties
            "state": ["CA", "NY", "TX", "WI"][i % 4],
            "n_pass": 1,
            "n_fail": 0,
        }
    return out


def test_shuffled_input_cannot_change_an_existing_url():
    """The property that was broken. Order of the input dict must be irrelevant."""
    schools = _schools()
    registry = {u: f"registered-{u}" for u in list(schools)[:40]}  # most already published
    baseline = assign(schools, registry)
    rng = random.Random(20260903)
    for _ in range(25):
        items = list(schools.items())
        rng.shuffle(items)
        assert assign(dict(items), registry) == baseline, (
            "slug assignment changed when the input order changed"
        )


def test_registered_slugs_are_returned_verbatim():
    schools = _schools(10)
    registry = {u: f"frozen-{u}" for u in schools}
    assert assign(schools, registry) == registry


def test_a_retired_slug_is_never_reused_by_another_institution():
    """A school can drop out of the data. Its slug stays reserved, so the URL cannot silently come
    to mean a different institution."""
    schools = {"999001": {"name": "Ghost College", "state": "CA", "n_pass": 1, "n_fail": 0}}
    registry = {"111111": "ghost-college"}  # retired: not in the data any more
    got = assign(schools, registry)
    assert got["999001"] != "ghost-college", "a retired institution's slug was handed to another"


def test_new_institutions_get_deterministic_slugs():
    schools = _schools(8)
    a = assign(schools, {})
    b = assign(dict(reversed(list(schools.items()))), {})
    assert a == b, "new institutions must not depend on input order either"
    assert len(set(a.values())) == len(a), "slugs must be unique"


def test_the_registry_covers_every_published_college():
    """CI guard. A qualified school with no registered slug means the registry needs updating and
    committing, which is a deliberate act rather than a silent derivation."""
    if not REGISTRY.exists():
        pytest.skip("no registry in this working copy")
    registry = json.loads(REGISTRY.read_text())
    assert len(registry) == len(set(registry.values())), "two institutions share a slug"

    slug_map = ROOT / "site" / "college" / "slug-map.json"
    if not slug_map.exists():
        pytest.skip("no built college tree in this working copy")
    published = json.loads(slug_map.read_text())
    drifted = {
        u: (s, registry.get(str(u))) for u, s in published.items() if registry.get(str(u)) != s
    }
    assert not drifted, f"published slugs disagree with the registry: {list(drifted.items())[:5]}"


def test_build_slugs_goes_through_the_registry():
    """Every slug consumer routes here, so the registry cannot be bypassed by one of them."""
    src = (ROOT / "pipeline" / "build_college_pages.py").read_text()
    body = src.split("def build_slugs(", 1)[1].split("\ndef ", 1)[0]
    assert "slug_registry" in body, "build_slugs must resolve slugs through the registry"
    assert "resolve" in body, "builders must use the STRICT resolver, not assign()"


def test_builders_fail_closed_on_an_unregistered_institution():
    """The deploy workflow checks the registry up front, but `make college-pages` and a direct
    module run do not, and those are the paths behind local previews and manual promotion. A build
    must refuse rather than invent a URL that is in no committed contract."""
    from pipeline.build_college_pages import build_slugs

    unknown = {
        "99999999": {"name": "Unregistered College", "state": "CA", "n_pass": 1, "n_fail": 0}
    }
    with pytest.raises(SystemExit, match="no registered slug"):
        build_slugs(unknown)
    # resolve() is strict; assign() is deliberately permissive, since extending is its job.
    assert resolve({}, {}) == {}
    assert assign(unknown, {})["99999999"] == "unregistered-college"


def test_assign_refuses_when_even_the_unitid_fallback_is_taken():
    """base, base-state and base-unitid are the whole ladder. The unitid form was added without
    rechecking, so a registry that had already issued it got a second institution on the same URL.
    unitid is unique, so this only happens when that slug belongs to someone else: refuse."""
    registry = {
        "111111": "beauty-academy",
        "222222": "beauty-academy-tx",
        "333333": "beauty-academy-900001",  # already owns the fallback for 900001
    }
    schools = {"900001": {"name": "Beauty Academy", "state": "TX", "n_pass": 1, "n_fail": 0}}
    with pytest.raises(SystemExit, match="already belongs to 333333"):
        assign(schools, registry)
