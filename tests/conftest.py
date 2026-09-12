"""Shared test fixtures.

The one thing here exists because slug resolution is deliberately STRICT in builders: an
institution with no entry in published/slug_registry.json raises rather than being handed an
invented URL. That is the point of the registry, and it is what protects `make college-pages` and
manual promotion, which do not get the deploy workflow's up-front check.

Tests that drive a whole build against synthetic parquet create institutions that are, correctly,
not in the real registry. They are not testing the URL contract; they are testing ranking, cost
calculation and page structure. So they register their own fixtures first, which is the test
equivalent of running `make slug-registry` before a build.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def register_fixture_slugs(monkeypatch):
    """Return a callable that registers whatever schools the fixture parquet contains.

    Call it AFTER the parquet is written and PARQUET_DIR is patched, and BEFORE the build runs.
    Slugs are derived exactly as `assign()` would for genuinely new institutions, so the URLs a
    test asserts on are the same ones the old derive-on-the-fly behaviour produced.
    """

    def _register():
        import duckdb

        from pipeline import slug_registry
        from pipeline.build_college_pages import qualifying_schools
        from pipeline.build_site import build_model

        schools, _by_state, _bench = build_model(duckdb.connect())
        derived = slug_registry.assign(qualifying_schools(schools), {})
        monkeypatch.setattr(slug_registry, "load", lambda: {str(u): s for u, s in derived.items()})

    return _register
