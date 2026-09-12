"""Guard the UNITID -> canonical slug mapping that drives the Stage 4 URL migration.

The consolidation retires /value-check/?school=<id> in favour of /college/<slug>/. Cloudflare cannot
redirect on a query parameter, so the discovery page resolves the slug client-side from the published
slug-map.json. That only works if every school maps to exactly one collision-free slug, and if a
collided slug cannot be recomputed from the name alone (proving the map is necessary). These test the
assignment rules deterministically, without a data build.

Since the slug registry landed, build_slugs() resolves published institutions from
published/slug_registry.json and only ASSIGNS a slug to genuinely new ones. These cases are all
about that assignment path, so they call assign() with an explicit empty registry: passing fake
institutions through build_slugs() would collide with the 6,127 real slugs the registry reserves,
which is correct production behaviour but tells you nothing about the rules being tested here.
"""

from __future__ import annotations

from pipeline.build_college_pages import slugify
from pipeline.slug_registry import assign


def build_slugs(qualified):
    """The collision rules as applied to institutions that are not yet registered."""
    return assign(qualified, registry={})


def _school(name, state, npass=1, nfail=0):
    return {"name": name, "state": state, "n_pass": npass, "n_fail": nfail}


def test_slugs_are_unique_and_complete():
    qualified = {
        "1": _school("Alpha College", "CA"),
        "2": _school("Beta University", "NY"),
        "3": _school("Gamma Institute", "TX"),
    }
    slugs = build_slugs(qualified)
    assert set(slugs) == set(qualified), "every school must be mapped"
    assert len(set(slugs.values())) == len(slugs), "slugs must be unique"
    assert slugs["1"] == "alpha-college"


def test_same_name_different_state_gets_state_suffix():
    """Two schools with the same name must not collide; the second takes a state suffix, which is why
    the slug cannot be recomputed from the name alone and the map must be published."""
    qualified = {
        "10": _school("Central College", "CA"),
        "11": _school("Central College", "NY"),
    }
    slugs = build_slugs(qualified)
    assert len(set(slugs.values())) == 2, "same-name schools must get distinct slugs"
    assert "central-college" in slugs.values()
    assert any(s.endswith("-ny") or s.endswith("-ca") for s in slugs.values())


def test_third_same_name_same_state_falls_back_to_unitid():
    """The first takes the bare name, the second the state suffix; a third in the same state can use
    neither, so it falls back to the UNITID. All three stay unique."""
    qualified = {
        "100": _school("Beauty Academy", "TX"),
        "101": _school("Beauty Academy", "TX"),
        "102": _school("Beauty Academy", "TX"),
    }
    slugs = build_slugs(qualified)
    assert len(set(slugs.values())) == 3, "three same-name-same-state schools must all differ"
    assert "beauty-academy" in slugs.values()
    assert "beauty-academy-tx" in slugs.values()
    assert any(
        s.endswith("-100") or s.endswith("-101") or s.endswith("-102") for s in slugs.values()
    )
    # The bare-name recomputation would be WRONG for two of the three, proving the map is needed.
    assert sum(s == slugify("Beauty Academy") for s in slugs.values()) == 1


def test_slug_generation_is_deterministic():
    """Same input, same output: the map is stable across builds so URLs do not churn.

    Input ORDER independence is the stronger property and is covered in test_slug_registry.py,
    which is where the real bug lived.
    """
    qualified = {
        "1": _school("Zeta School", "WA"),
        "2": _school("Eta School", "OR"),
    }
    assert build_slugs(qualified) == build_slugs(dict(qualified))
