"""The profile's "About the college" and "Colleges to compare" sections (Prototype N, approved
15 November 2026).

About the college prints four facts the federal institution file holds: undergraduate enrollment,
the share of undergraduates with a Pell grant, the completion rate and the college's website. Each
keeps beside it the population and the year it describes, and says "not published" where ED's file
has none.

The completion rate always prints the number of students it rests on. It follows first-time,
full-time students only, and 923 of the 5,058 rates in the 2026-06-10 release rest on fewer than
30 of them (the 157 rates of exactly 100% have a median of 6). Under 30 the page says how far one
student moves the figure.

Colleges to compare lists up to five colleges in the same state, of the same type, awarding mostly
the same credential (ED's classification), nearest in undergraduate enrollment. It is not called
"similar": on the June data 16% of the rows are more than double or less than half the college's
size. The rule is printed, and where it cannot be applied the section says why and links the
state's colleges, so no profile ends without a next step.

The years come from ED's data dictionary and belong to one release each (YEARS below). A release
with no entry stops the build: a year carried over from the previous release would be a guess
printed as a fact.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import NamedTuple

from pipeline.build_college_pages import esc, known_state, state_label
from pipeline.build_site import clean_school_url

SMALL_COHORT = 30  # ED's own line for suppressing pooled rates: one student can swing the figure
MAX_PEERS = 5
REQUIRED_COLUMNS = ("completion_cohort", "completion_basis", "predominant_degree")


class Years(NamedTuple):
    """What each figure describes in one College Scorecard release."""

    enrollment: str  # UGDS: degree-seeking undergraduates, fall census
    pell: str  # PCTPELL: academic year
    four_year: str  # C150_4: the year the cohort started
    less_than_four_year: str  # C150_L4: the year the cohort started


# From ED's data dictionary (CollegeScorecardDataDictionary.xlsx, sheets Institution_Cohort_Map and
# Most_Recent_Inst_Cohort_Map, read 15 November 2026). ED keeps only the current map, so each
# release's years are recorded here when the release is adopted.
#
# 2026-06-10: enrollment is Fall 2024 (file Merged2024_25). Pell and completion had not been
#   refreshed yet, so they are that same file's: AcadYr 2023-24, and the Fall 2018 or 2018-19 cohort
#   (four-year) and Fall 2021 or 2021-22 cohort (less than four-year). Checked against the data:
#   between this release and the next, enrollment is identical for every college and Pell and
#   completion differ for 98% of them.
# 2026-11-02: ED refreshed Pell and completion on 15 October from Merged2025_26: AcadYr 2024-25,
#   and the 2019-20 and 2022-23 cohorts. Enrollment is still Fall 2024.
YEARS: dict[str, Years] = {
    "2026-06-10": Years("fall 2024", "2023-24", "2018-19", "2021-22"),
    "2026-11-02": Years("fall 2024", "2024-25", "2019-20", "2022-23"),
}


def years_for(release: str) -> Years:
    if release not in YEARS:
        raise SystemExit(
            f"profile_basics: no years recorded for College Scorecard release {release}. Read them "
            "from ED's data dictionary (Most_Recent_Inst_Cohort_Map) and add them to YEARS."
        )
    return YEARS[release]


class Basics(NamedTuple):
    """One college's row in the institution file, at ED's precision (the page rounds once)."""

    url: str | None  # a web address a reader can follow, or None
    enrollment: int | None
    pell: float | None
    completion: float | None
    cohort: int | None  # the students the completion rate rests on
    basis: str | None  # "four_year" or "less_than_four_year"
    degree: int | None  # ED: 0 not classified, 1 certificate, 2 associate, 3 bachelor, 4 graduate


def load(con, inst_path: Path) -> dict[str, Basics]:
    """Every college in the institution file. The three newer columns are required: a rate printed
    without the students it rests on is what this section exists to prevent, so a file without
    them stops the build instead of quietly dropping the count."""
    have = {
        r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{inst_path}')").fetchall()
    }
    missing = [c for c in REQUIRED_COLUMNS if c not in have]
    if missing:
        raise SystemExit(
            f"profile_basics: {inst_path.name} has no {', '.join(missing)}. Rebuild the spine "
            "(python -m pipeline.build_spine) and copy institutions.parquet to published/."
        )
    rows = con.execute(
        f"""SELECT unitid, school_url, enrollment, pell_share, completion_rate, completion_cohort,
                   completion_basis, predominant_degree
            FROM read_parquet('{inst_path}')"""
    ).fetchall()
    return {
        u: Basics(
            clean_school_url(url),
            None if enr is None else int(enr),
            pell,
            rate,
            None if cohort is None else int(cohort),
            basis,
            None if degree is None else int(degree),
        )
        for u, url, enr, pell, rate, cohort, basis, degree in rows
    }


def pct(share: float) -> str:
    """A whole percentage, rounded once and half up as Compare does. A share short of all is
    never printed as 100%, and one above none never as 0%."""
    p = math.floor(100 * share + 0.5)
    if p >= 100 and share < 1:
        p = 99
    if p <= 0 and share > 0:
        p = 1
    return f"{p}%"


# --- About the college -------------------------------------------------------------------------

_NORMAL_TIME = {
    "four_year": "for example, six years for a bachelor&rsquo;s degree",
    "less_than_four_year": "for example, three years for a two-year program",
}


def _fact(label: str, figure: str | None, note: str) -> str:
    fig = (
        f'<span class="basics__fig">{figure}</span>'
        if figure is not None
        else '<span class="basics__fig basics__fig--none">not published</span>'
    )
    return (
        f'        <div class="basics__fact"><dt>{label}</dt><dd>{fig}'
        f'<span class="basics__note">{note}</span></dd></div>\n'
    )


def _completion(b: Basics, years: Years) -> str:
    if b.completion is None:
        return _fact(
            "Completion rate",
            None,
            "ED published no completion rate. It follows first-time, full-time students only, "
            "and a college with none to follow has no rate.",
        )
    if not b.cohort or b.basis not in _NORMAL_TIME:
        # The gate (analysis.validate) holds this for every published rate.
        raise ValueError("a completion rate with no cohort size or kind cannot be printed")
    started = getattr(years, b.basis)
    one = b.cohort == 1
    note = (
        f"Of the {b.cohort:,} first-time, full-time student{'' if one else 's'} who started in "
        f"{started}, the share who finished within 150% of the normal time for their program "
        f"({_NORMAL_TIME[b.basis]}). Transfer and part-time students are not counted."
    )
    if b.cohort < SMALL_COHORT:
        step = 100 / b.cohort
        points = f"{round(step)} point{'' if round(step) == 1 else 's'}"
        about = "" if step == round(step) else "about "
        note += (
            f" <b>A small group:</b> with {b.cohort} student{'' if one else 's'}, one student "
            f"moves this figure by {about}{points}."
        )
    return _fact("Completion rate", pct(b.completion), note)


def _website(b: Basics) -> str:
    if not b.url:
        return _fact("Website", None, "ED published no web address for this college.")
    href = b.url if "://" in b.url else "https://" + b.url
    text = b.url.split("://", 1)[-1].rstrip("/")
    text = text[4:] if text.lower().startswith("www.") else text
    return _fact(
        "Website",
        f'<a class="basics__url" href="{esc(href)}" rel="noopener">{esc(text)}</a>',
        "As the college reported it to the Department of Education.",
    )


def about_section(b: Basics | None, years: Years, release: str) -> str:
    """The four facts. b is None for a college ED's institution file does not list."""
    listed = b is not None
    b = b or Basics(None, None, None, None, None, None, None)
    facts = [
        _fact(
            "Undergraduates",
            f"{b.enrollment:,}" if b.enrollment is not None else None,
            f"Degree-seeking undergraduates enrolled in {years.enrollment}."
            if b.enrollment is not None
            else "ED published no undergraduate count for this college.",
        ),
        _fact(
            "Students with a Pell grant",
            pct(b.pell) if b.pell is not None else None,
            f"Of undergraduates in {years.pell}. Pell grants are federal aid for students from "
            "lower-income families."
            if b.pell is not None
            else "ED published no Pell figure for this college.",
        ),
        _completion(b, years),
        _website(b),
    ]
    lead = (
        ""
        if listed
        else '      <p class="basics__lead">ED&rsquo;s institution file does not list this college, '
        "so none of these figures is published.</p>\n"
    )
    return (
        '    <section id="about" aria-labelledby="about-h">\n'
        '      <h2 id="about-h">About the college</h2>\n'
        f"{lead}"
        '      <div class="basics"><dl class="basics__facts">\n'
        f"{''.join(facts)}"
        "      </dl></div>\n"
        '      <p class="tw-source">These describe the college as a whole, not any one program. '
        f"Source: College Scorecard institution file, release {esc(release)}, from the "
        "colleges&rsquo; own reports to IPEDS.</p>\n"
        "    </section>\n"
    )


# --- Colleges to compare -----------------------------------------------------------------------

_DEGREE = {1: "certificates", 2: "associate&rsquo;s degrees", 3: "bachelor&rsquo;s degrees"}
_TYPE = {
    "Public": "public",
    "Private, nonprofit": "private nonprofit",
    "Private, for-profit": "private for-profit",
}


class Peer(NamedTuple):
    """A college as another college's list shows it."""

    unitid: str
    name: str
    slug: str
    state: str | None
    control: str | None
    degree: int | None
    enrollment: int | None
    above: int  # undergraduate programs above the high-school line, as its own headline counts
    assessed: int  # of this many with a verdict


class PeerIndex:
    """Every college with a profile, grouped by the three things the rule holds equal."""

    def __init__(self, colleges: list[Peer]) -> None:
        self.by_id = {c.unitid: c for c in colleges}
        self.groups: dict[tuple, list[Peer]] = {}
        for c in colleges:
            if self._key(c) is not None and c.enrollment is not None:
                self.groups.setdefault(self._key(c), []).append(c)

    @staticmethod
    def _key(c: Peer) -> tuple | None:
        if not known_state(c.state) or c.control not in _TYPE or c.degree not in _DEGREE:
            return None
        return (c.state, c.control, c.degree)

    def nearest(self, unitid: str) -> tuple[str, list[Peer], int]:
        """(case, colleges shown, colleges that match). One rule for every profile: same state,
        same type, same predominant credential, nearest in undergraduate enrollment. Equal
        distances are settled by name, then federal ID, so two builds give one list."""
        c = self.by_id.get(unitid)
        if c is None or c.degree is None:
            return "unlisted", [], 0
        if c.degree == 4:
            return "graduate", [], 0
        if c.degree not in _DEGREE or c.control not in _TYPE:
            return "unclassified", [], 0
        if not known_state(c.state):
            return "no-state", [], 0
        if c.enrollment is None:
            return "no-size", [], 0
        others = [o for o in self.groups.get(self._key(c), []) if o.unitid != unitid]
        others.sort(key=lambda o: (abs(o.enrollment - c.enrollment), o.name.lower(), o.unitid))
        return ("ok" if others else "none"), others[:MAX_PEERS], len(others)


def compare_section(unitid: str, index: PeerIndex, years: Years) -> str:
    c = index.by_id[unitid]
    case, shown, total = index.nearest(unitid)
    st = state_label(c.state)
    # A college whose state ED did not report gets the national list.
    browse = (
        f'<a href="/colleges/{c.state.lower()}/">Browse all colleges in {esc(st)}</a>'
        if known_state(c.state)
        else '<a href="/colleges/">Browse colleges by state</a>'
    )
    kind = _TYPE.get(c.control or "", "")
    head = (
        '    <section id="compare" aria-labelledby="compare-h">\n'
        '      <h2 id="compare-h">Colleges to compare</h2>\n'
    )
    if case != "ok":
        why = {
            "unlisted": "ED&rsquo;s institution file does not list this college, so colleges of "
            "the same kind cannot be picked.",
            "unclassified": "ED does not classify this college&rsquo;s type or the credential it "
            "mainly awards, so colleges of the same kind cannot be picked.",
            "graduate": "This college awards graduate degrees only, so it has no undergraduate "
            "enrollment to match on.",
            "no-state": "ED does not report this college&rsquo;s state, so colleges in the same "
            "state cannot be picked.",
            "no-size": "This college&rsquo;s enrollment is not published, so colleges close to "
            "it in size cannot be picked.",
            "none": f"No other {kind} college in {esc(st)} awards mostly "
            f"{_DEGREE.get(c.degree, '')} and has its enrollment published.",
        }[case]
        return head + f'      <p class="peers__rule">{why} {browse}.</p>\n    </section>\n'
    degree = _DEGREE[c.degree]
    if total > MAX_PEERS:
        rule = (
            f"The {MAX_PEERS} closest in size to {esc(c.name)} among the {total:,} other {kind} "
            f"colleges in {esc(st)} that award mostly {degree}."
        )
    elif total == 1:
        rule = f"The one other {kind} college in {esc(st)} that awards mostly {degree}."
    else:
        rule = (
            f"The {total} other {kind} colleges in {esc(st)} that award mostly {degree}, closest "
            "in size first."
        )
    body = []
    for o in shown:
        count = f"{o.above:,} of {o.assessed:,} assessed" if o.assessed else "not assessed"
        body.append(
            f'        <tr><td><a href="/college/{o.slug}/">{esc(o.name)}</a></td>'
            f'<td class="num">{o.enrollment:,}</td>'
            f'<td class="num"><span class="peers__n">{count}</span></td>'
            f'<td class="num"><a href="/compare/?schools={c.unitid},{o.unitid}" '
            f'aria-label="Compare {esc(c.name)} with {esc(o.name)}">Compare</a></td></tr>\n'
        )
    return (
        head
        + f'      <p class="peers__rule">{rule} <b>Same state, same type, nearest in size.</b> '
        "A place to start a comparison, not a judgment of quality.</p>\n"
        '      <div class="tscroll peers" tabindex="0" role="region" '
        'aria-label="Colleges to compare"><table class="t"><thead><tr><th>College</th>'
        '<th class="num">Undergraduates</th>'
        '<th class="num">Undergraduate programs above the high-school line</th>'
        '<th class="num">Side by side</th></tr></thead><tbody>\n'
        + "".join(body)
        + "      </tbody></table></div>\n"
        '      <p class="tw-source">Type and main credential are ED&rsquo;s classification. '
        f"Enrollment is degree-seeking undergraduates, {years.enrollment}. {browse}.</p>\n"
        "    </section>\n"
    )
