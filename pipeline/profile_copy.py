"""A college profile's title and search description (Prototype P, approved 21 November 2026).

Title: the college, then what the page answers, then the place. The place stays because 86 title
values were once shared by 202 pages; it goes last so that a cut title loses the place, not the
words people search for.

Description: the college and place, then the number the summary box leads with (programs above the
high-school line, of those assessed, undergraduate where any are), with the words that qualify it.
Each case lists its wordings longest first, and every wording keeps its qualifiers: "assessed",
"undergraduate" or "graduate", the state's line, and for graduate programs "not the federal test
for them" (the federal rule compares graduate programs with bachelor's degree holders). When a
wording is too long the city goes first, then the state, and for the six longest names the
college's own name, which the title already carries.

Same-named campuses can share every word. choose() gives each of them a wording that adds a fact
setting it apart: its city where the first wording had to drop it, or its count of recent
graduates. Never a wording that merely differs, and never an identifier.
"""

from __future__ import annotations

from collections import Counter

from pipeline import profile_layout as pl
from pipeline.build_college_pages import known_state, state_label
from pipeline.search_copy import DESC_MAX, agree, fitting, n_of


def title(meta: dict) -> str:
    st = meta["state"]
    where = ", ".join(p for p in (meta.get("city"), st) if p) if known_state(st) else ""
    return f"{meta['name']}: graduate earnings and cost" + (f", {where}" if where else "")


def _cores(meta: dict, rows: list[dict]) -> list[str]:
    st = meta["state"]
    located = known_state(st)
    line = (
        f"a typical {state_label(st)} high-school graduate"
        if located
        else "a typical high-school graduate"
    )
    ug = pl.counts([r for r in rows if not r.get("grad")])
    c = pl.counts(rows)
    total = c["total"]
    if ug["decided"]:
        p, d = ug["pass"], ug["decided"]
        progs = n_of(d, "assessed undergraduate program")
        lead = f"{p:,} of {progs} {agree(p, d, 'has', 'have')} "
        hs = f"the {state_label(st)} high-school line" if located else "the high-school line"
        return [
            lead + f"graduates earning more than {line}.",
            lead + f"graduates above {hs}.",
            f"{p:,} of {progs} {agree(p, d, 'is', 'are')} above {hs}.",
        ]
    if c["decided"]:
        # No undergraduate verdict, so every verdict here is a graduate program's.
        p, d = c["pass"], c["decided"]
        progs = n_of(d, "assessed graduate program")
        lead = f"{p:,} of {progs} {agree(p, d, 'has', 'have')} "
        hs = f"the {state_label(st)} high-school line" if located else "the high-school line"
        return [
            lead + f"graduates earning more than {line}, which is not the federal test for "
            "graduate programs.",
            lead + f"graduates earning more than {line}, not the federal test for them.",
            lead + f"graduates above {hs}, not the federal test for them.",
            f"{p:,} of {progs} {agree(p, d, 'is', 'are')} above {hs}, not the federal test for "
            "them.",
        ]
    if c["nobench"]:
        nb = c["nobench"]
        if total == 1:
            which = "its one program"
        elif nb == total:
            which = f"all {total:,} of its programs"
        else:
            which = f"{nb:,} of its {total:,} programs"
        them = "it" if nb == 1 else "them"
        return [
            f"ED publishes earnings for {which}, but no state high-school benchmark to compare "
            f"{them} with.",
            f"ED publishes earnings for {which}, with no state benchmark to compare {them} with.",
            f"earnings for {which}, no state benchmark to compare {them} with.",
        ]
    if c["none"] < total:
        its = "its one program" if total == 1 else f"any of its {total:,} programs"
        bare = "its one program" if total == 1 else f"its {total:,} programs"
        return [
            f"ED publishes no graduate earnings for {its}, so none can be assessed.",
            f"ED publishes no earnings for {its}, so none can be assessed.",
            f"no earnings published for {bare}; none can be assessed.",
        ]
    its = "its one program" if total == 1 else f"its {total:,} programs"
    return [f"ED lists {its} but reports no figures for {'it' if total == 1 else 'them'}."]


def options(meta: dict, rows: list[dict]) -> list[str]:
    """Every wording that fits a search result, best first."""
    name, st = meta["name"], meta["state"]
    located = known_state(st)
    city = meta.get("city")
    at = f"{name}, {city}, {st}" if located and city else (f"{name}, {st}" if located else name)
    at_st = f"{name}, {st}" if located else name
    cores = _cores(meta, rows)
    out = []
    for core in cores:
        out += [f"{at}: {core}", f"{at_st}: {core}", f"{name}: {core}"]
    # A name too long for any of these: the title names the college, so the place and the number
    # carry the description. Never without a place: a bare sentence would name nothing.
    place = ", ".join(x for x in (city, st) if x) if located else ""
    if place:
        out += [f"{place}: {core[0].upper()}{core[1:]}" for core in cores]
    return fitting(*out)


def separating(meta: dict, rows: list[dict]) -> list[str]:
    """Wordings that add a fact telling two same-named campuses apart: the city, where the first
    wording had to drop it, then the count of recent graduates. Never a shorter wording that merely
    differs, and never an identifier."""
    st = meta["state"]
    city = meta.get("city") if known_state(st) else None

    def place(o: str) -> int:  # how much of the place a wording keeps: city, state, neither
        return 0 if city and f"{city}, " in o else (1 if f", {st}: " in o else 2)

    # Most place first, then the longer wording: adding a fact never costs the city.
    pool = sorted(options(meta, rows), key=place)
    # The city adds a fact only where the first wording had to drop it.
    dropped = bool(city) and place(options(meta, rows)[0]) != 0
    with_city = [o for o in pool if place(o) == 0] if dropped else []
    grads = int(sum(r.get("completers") or 0 for r in rows))
    more = f" {n_of(grads, 'recent graduate')}." if grads else ""
    counted = [o + more for o in pool if more and len(o + more) <= DESC_MAX]
    return list(dict.fromkeys(with_city + counted))


def description(meta: dict, rows: list[dict]) -> str:
    """The description for one profile on its own (the live build uses choose(), which also keeps
    same-named campuses apart)."""
    return options(meta, rows)[0]


def choose(pages: dict[str, tuple[list[str], list[str]]]) -> dict[str, str]:
    """{page: description} from {page: (options, separating)}.

    Each page takes its first option. Where two or more pages would share one, each of them takes
    its first separating wording, if that states a fact no other page's does (its city, or its
    count of recent graduates). Pages whose facts are the same keep the shared first option rather
    than take a wording that merely differs: two Royal Learning Institute pages in June 2026. No
    page's choice depends on another's, so the order pages arrive in cannot change the result."""
    first = {k: v[0][0] for k, v in pages.items()}
    count = Counter(first.values())
    sep = {k: v[1][0] for k, v in pages.items() if count[first[k]] > 1 and v[1]}
    sep_count = Counter(sep.values())
    out = {}
    for k in pages:
        s = sep.get(k)
        out[k] = s if s and sep_count[s] == 1 and s not in count else first[k]
    return out
