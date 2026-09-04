"""The committed UNITID -> slug registry: the authority for every published college URL.

Why this exists
---------------
Slugs used to be derived on the fly from the data. For institutions that share a name (there are
18 such pairs) the algorithm broke the tie on the ORDER the rows arrived in, and the query that
loads them did not order by unitid, so DuckDB was free to return tied rows differently from one
process to the next. Twelve fresh processes produced the live mapping nine times and an alternate
mapping three times, and the alternate moved 36 unitids.

That is a URL contract failing at random. Worse, the deploy has two independent slug consumers,
college pages and lists, running as separate processes, so a single build could publish a page at
one slug and link to it at another.

The fix is not a better tie-break. Sorting ties on unitid is deterministic but assigns the suffix to
the other sibling in 79 cases, so it would silently move 79 live URLs. A published URL is a promise;
the only safe authority is the mapping already in production. So it is frozen here, committed, and
reviewed like any other contract.

The rules
---------
1. A unitid in the registry keeps its slug forever. Nothing derived can override it.
2. Every slug the registry has ever issued stays reserved, including for institutions that have
   dropped out of the data, so a URL can never come to mean a different school.
3. Only genuinely new institutions get a slug, assigned deterministically from (name, unitid) and
   avoiding everything reserved.
4. Adding new institutions is an explicit, reviewable commit: `make slug-registry`.

Usage (from repo root):
    python -m pipeline.slug_registry --check    # exit 1 if a qualified school has no slug
    python -m pipeline.slug_registry            # add new institutions, then commit the diff
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline.config import ROOT

REGISTRY = ROOT / "published" / "slug_registry.json"


def load() -> dict[str, str]:
    """The frozen mapping, unitid (as string) -> slug."""
    if not REGISTRY.exists():
        raise SystemExit(f"no slug registry at {REGISTRY}; run `make slug-registry` to create it")
    return json.loads(REGISTRY.read_text())


def resolve(qualified: dict, registry: dict[str, str] | None = None) -> dict[str, str]:
    """Slugs for the qualified schools, STRICTLY from the registry. Raises on anything unregistered.

    This is the production path: every builder that publishes or links to a college page uses it.
    Failing closed is the point. `assign()` below will happily invent a slug for an unknown school,
    which is right when deliberately extending the registry and wrong during a build, where it
    would publish a page at an address that is in no committed contract and that a later build
    could choose differently. The deploy workflow checks the registry up front, but `make
    college-pages` and a direct `python -m pipeline.build_college_pages` do not, and those are the
    paths behind local previews and manual promotion.
    """
    registry = load() if registry is None else registry
    missing = [u for u in qualified if str(u) not in registry]
    if missing:
        names = [qualified[u].get("name") for u in missing[:5]]
        raise SystemExit(
            f"{len(missing):,} institution(s) have no registered slug (e.g. {names}). "
            "Run `make slug-registry`, review the diff and commit it before building. "
            "Slugs are a published URL contract and are not invented at build time."
        )
    return {u: registry[str(u)] for u in qualified}


def assign(qualified: dict, registry: dict[str, str] | None = None) -> dict[str, str]:
    """Registry first, then a deterministic slug for anything new. For EXTENDING the registry.

    Not for builders: see resolve(). Returns keys of the same type as `qualified`, since callers
    index it with their own unitids.
    """
    from pipeline.build_college_pages import slugify

    registry = load() if registry is None else registry
    # Every slug ever issued is reserved, including for schools no longer in the data.
    reserved = set(registry.values())
    out: dict = {}
    new: list = []
    for u, s in qualified.items():
        slug = registry.get(str(u))
        if slug is None:
            new.append((u, s))
        else:
            out[u] = slug

    # Deterministic for new institutions: name then unitid, so input order cannot matter.
    for u, s in sorted(new, key=lambda kv: ((kv[1]["name"] or "").lower(), str(kv[0]))):
        base = slugify(s["name"])
        cand = base
        if cand in reserved:
            cand = f"{base}-{(s.get('state') or '').lower()}"
        if cand in reserved:
            cand = f"{base}-{u}"
        if cand in reserved:
            # unitid is unique, so this needs the unitid form to have been issued to ANOTHER
            # institution. Writing it anyway would put two unitids on one URL. Refuse instead:
            # a registry that cannot be extended safely is a problem for a person to look at.
            owner = next(k for k, v in registry.items() if v == cand)
            raise SystemExit(
                f"cannot assign a slug to {u} ({s.get('name')!r}): every candidate is taken, and "
                f"{cand!r} already belongs to {owner}. Resolve by hand in {REGISTRY.name}."
            )
        reserved.add(cand)
        out[u] = cand
    return out


def _qualified_schools() -> dict:
    import duckdb

    from pipeline.build_college_pages import qualifying_schools
    from pipeline.build_site import build_model

    schools, _by_state, _bench = build_model(duckdb.connect())
    return qualifying_schools(schools)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report institutions missing from the registry and exit 1; make no changes",
    )
    args = ap.parse_args()

    registry = load() if REGISTRY.exists() else {}
    qualified = _qualified_schools()
    missing = [u for u in qualified if str(u) not in registry]

    if not missing:
        print(f"slug registry: current, {len(registry):,} institutions")
        return
    if args.check:
        names = [qualified[u]["name"] for u in missing[:5]]
        raise SystemExit(
            f"{len(missing):,} institution(s) have no registered slug (e.g. {names}). "
            "Run `make slug-registry` and commit the result."
        )

    assigned = assign(qualified, registry)
    for u in missing:
        registry[str(u)] = assigned[u]
    REGISTRY.write_text(json.dumps(dict(sorted(registry.items())), indent=1) + "\n")
    print(f"slug registry: added {len(missing):,}, now {len(registry):,} institutions")
    print("commit published/slug_registry.json: it is the URL contract")


if __name__ == "__main__":
    sys.exit(main())
