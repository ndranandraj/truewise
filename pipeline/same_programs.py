"""The same programs at other colleges in the state, on a profile with no undergraduate verdict
(review of 13 November 2026, Phase 1 "No-verdict profiles"; Prototype O, approved 21 November).

A profile that reads "0 of 1 programs could be assessed" is honest and leaves the reader with
nothing to do. Where ED publishes no earnings for any of a college's undergraduate programs, the
profile opens with what ED does publish for the same programs (same 4-digit field, same
credential) at other colleges in the same state: how many have a verdict, how many of those are
above the high-school line, and the middle of their median earnings.

Rules, each tested:
  * Other colleges only, each program once. Campuses under one federal institution ID (OPEID6)
    share ED's figures, so a program counts once per ID, field and credential, as the headline
    counts it (pipeline/program_unit.py), and campuses under this college's own ID are left out.
    One difference from the headline, because this section is about one state: a program is in
    the state if a campus of it is, judged against that state's line, as that campus's own profile
    judges it. The headline instead counts a program once nationally, in its main campus's state
    (48 programs differ); here that would leave out branch campuses in the state whose main campus
    is elsewhere (62 campus rows in the June 2026 release, on 31 served profiles).
  * Labelled as other colleges in the heading, the first sentence and the column heading. It says
    what those graduates earned, never what this college's graduates earn.
  * Counts, not percentages: "0 of 5" shows how thin a comparison is.
  * Up to MAX_ROWS programs, the most comparisons first; how many more have one is printed, and
    programs with none in the state are named.
  * Served only where its first sentence is true: a state on record, at least one undergraduate
    program (certificate, associate's or bachelor's), and no earnings published for any of the
    college's undergraduate programs (so no verdict either). A college whose earnings ED publishes
    without a state line keeps the profile's "no state benchmark" and gets no section. Graduate-only
    colleges get none: the federal test compares graduate programs with bachelor's degree holders.
  * Where no other college in the state has a verdict for a program, the page says no other
    college "has published earnings that can be compared with the high-school line", not that none
    has published earnings: colleges ED's institution file does not list publish earnings with no
    state line (none beside a program this section names in June 2026; 317 rows on 20 served
    profiles in the November release). The build stops if a campus under this college's own ID has
    a verdict for such a program, because "shared figures" would then be false.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pipeline.build_college_pages import esc, money, state_label
from pipeline.build_profile_pilot import major_slug_for
from pipeline.cip_names import plain_name
from pipeline.program_unit import UNDERGRAD_LEVELS

MAX_ROWS = 10
# The credential words the section uses; the program table beside it shows ED's full labels.
CREDENTIALS = {"1": "certificate", "2": "associate&rsquo;s", "3": "bachelor&rsquo;s"}
# Cosmetology: the federal rule holds programs for tipped jobs out of its first rounds. The note is
# on 12.04 only, as on the homepage and the major pages; the rule's other codes are not transcribed.
TIPPED_CIP4 = frozenset({"1204"})
GRAD_LEVELS = ("4", "5", "6", "7", "8")
_GRAD = ", ".join(f"'{lvl}'" for lvl in GRAD_LEVELS)
_UG = ", ".join(f"'{lvl}'" for lvl in UNDERGRAD_LEVELS)


class Program(NamedTuple):
    name: str  # as the profile's program table names it
    cip: str
    cred: str  # '1', '2' or '3'
    others: int  # the same program at other colleges in the state, with a verdict
    above: int  # of those, above the high-school line
    median: float | None  # the middle of their median earnings
    one_year: int  # of those, verdicts on one-year earnings
    completers: int | None  # this college's recent completers, which settles ties in the order


class Context(NamedTuple):
    state: str
    line: float | None  # the state's high-school line, which the other colleges' verdicts use
    programs: tuple[Program, ...]


def order_key(p: Program):
    """Most comparisons first; then this college's larger programs; then the name, field and
    credential, so the order never depends on how the rows arrived."""
    return (-p.others, -(p.completers or 0), p.name.lower(), p.cip, p.cred)


def load(con, vc_path: Path | str) -> dict[str, Context]:
    """{unitid: Context} for every college the section serves (see the module docstring)."""
    vc = str(vc_path).replace("'", "''")
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{vc}')").fetchall()}
    # A table without OPEID6 (a hand-made fixture) has no shared figures: each campus is its own.
    opeid = "opeid6" if "opeid6" in cols else "NULL::VARCHAR"
    con.execute(
        f"""CREATE OR REPLACE TEMP VIEW sp_p AS
            SELECT *, CAST(unitid AS VARCHAR) AS sp_unitid,
                   coalesce(CAST({opeid} AS VARCHAR), 'unit:' || CAST(unitid AS VARCHAR)) AS sp_grp
            FROM read_parquet('{vc}') WHERE regexp_matches(CAST(unitid AS VARCHAR), '^[0-9]+$')"""
    )
    # The other colleges' programs in each state, each once: campuses under one federal ID share
    # ED's figures, and within one state they share its line, so they share a verdict (checked
    # below). Lowest UNITID first, so the choice is deterministic either way.
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE sp_u AS
            SELECT state, sp_grp, cip_code, credential_level,
                   arg_min(value_flag, sp_unitid) AS value_flag,
                   arg_min(earnings, sp_unitid) AS earnings,
                   arg_min(earnings_horizon, sp_unitid) AS earnings_horizon,
                   count(DISTINCT value_flag) AS n_flags, count(DISTINCT earnings) AS n_earnings
            FROM sp_p
            WHERE state IS NOT NULL AND value_flag != 'insufficient_data'
              AND credential_level IN ({_UG})
            GROUP BY ALL"""
    )
    split = con.execute("SELECT count(*) FROM sp_u WHERE n_flags > 1 OR n_earnings > 1")
    split = split.fetchone()[0]
    if split:
        raise SystemExit(
            f"same_programs: {split} programs under one federal ID have different figures or "
            "verdicts within one state; they cannot be counted once"
        )
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE sp_served AS
            SELECT sp_unitid AS unitid, min(sp_grp) AS grp, min(state) AS st
            FROM sp_p GROUP BY 1
            HAVING min(state) IS NOT NULL
               AND count(*) FILTER (WHERE coalesce(credential_level, '') NOT IN ({_GRAD})
                                    AND (earnings IS NOT NULL
                                         OR value_flag != 'insufficient_data')) = 0"""
    )
    # A college with no undergraduate program has no rows here, so it is not served.
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE sp_mine AS
            SELECT p.sp_unitid AS unitid, p.cip_code AS cip, p.credential_level AS cred,
                   min(p.cip_desc) AS cip_desc, sum(p.completers_count) AS completers
            FROM sp_p p JOIN sp_served s ON s.unitid = p.sp_unitid
            WHERE p.credential_level IN ({_UG})
            GROUP BY ALL"""
    )
    rows = con.execute(
        """SELECT m.unitid, m.cip, m.cred, m.cip_desc, m.completers,
                  count(u.cip_code) AS others,
                  count(u.cip_code) FILTER (WHERE u.value_flag = 'passes_earnings_premium') AS above,
                  median(u.earnings) AS med,
                  count(u.cip_code) FILTER (WHERE u.earnings_horizon = '1yr_after_completion')
                    AS one_year
           FROM sp_mine m JOIN sp_served s USING (unitid)
           LEFT JOIN sp_u u ON u.state = s.st AND u.cip_code = m.cip
                AND u.credential_level = m.cred AND u.sp_grp != s.grp
           GROUP BY ALL"""
    ).fetchall()
    # Where the page says no other college in the state has comparable earnings for a program, no
    # campus in the state other than this college has a verdict for it. Campuses under this
    # college's own ID are left out of the count because they share its figures; one with a verdict
    # where this college has no earnings would contradict that, so the build stops.
    false_none = con.execute(
        """WITH counted AS (
             SELECT m.unitid, m.cip, m.cred, s.st, s.grp,
                    count(u.cip_code) AS others
             FROM sp_mine m JOIN sp_served s USING (unitid)
             LEFT JOIN sp_u u ON u.state = s.st AND u.cip_code = m.cip
                  AND u.credential_level = m.cred AND u.sp_grp != s.grp
             GROUP BY ALL)
           SELECT count(*) FROM counted c JOIN sp_p p ON p.state = c.st AND p.cip_code = c.cip
             AND p.credential_level = c.cred AND p.sp_unitid != c.unitid
             AND p.value_flag != 'insufficient_data'
           WHERE c.others = 0"""
    ).fetchone()[0]
    if false_none:
        raise SystemExit(
            f"same_programs: {false_none} campuses in the same state have a verdict for a program "
            "the section would say no other college can compare; check the shared figures"
        )
    lines = dict(
        con.execute(
            "SELECT state, max(earnings_threshold_state) FROM sp_p WHERE state IS NOT NULL "
            "GROUP BY 1"
        ).fetchall()
    )
    progs: dict[str, list[Program]] = {}
    for u, cip, cred, desc, done, others, above, med, one in rows:
        progs.setdefault(u, []).append(
            Program(
                plain_name(str(cip), desc),
                str(cip),
                str(cred),
                int(others),
                int(above),
                None if med is None else float(med),
                int(one),
                None if done is None else int(done),
            )
        )
    states = dict(con.execute("SELECT unitid, st FROM sp_served").fetchall())
    return {
        u: Context(states[u], lines.get(states[u]), tuple(sorted(ps, key=order_key)))
        for u, ps in progs.items()
    }


def _label(p: Program) -> str:
    return f"{esc(p.name)} ({CREDENTIALS[p.cred]})"


def section(ctx: Context) -> str:
    name = esc(state_label(ctx.state))
    have = [p for p in ctx.programs if p.others]
    none = [p for p in ctx.programs if not p.others]
    head = (
        '    <section id="elsewhere" aria-labelledby="elsewhere-h">\n'
        f'      <h2 id="elsewhere-h">The same programs at other colleges in {name}</h2>\n'
    )
    if not have:
        linked = any(major_slug_for(p.cip) for p in ctx.programs)
        where = (
            " Where a program has a page for the whole country, its name in "
            '<a href="#programs">Program earnings</a> links to it.'
            if linked
            else ""
        )
        return (
            head + '      <p class="same__lede">ED publishes no earnings for this college&rsquo;s '
            f"undergraduate programs, and no other college in {name} has published earnings for "
            "the same programs that can be compared with the high-school line, so there is "
            f"nothing in the state to set beside them.{where}"
            "</p>\n    </section>\n"
        )
    shown = have[:MAX_ROWS]
    more = (
        f" The {MAX_ROWS} with the most comparisons are shown; {len(have) - MAX_ROWS:,} more of "
        "this college&rsquo;s programs have at least one."
        if len(have) > MAX_ROWS
        else ""
    )
    line = f" ({money(ctx.line)} a year)" if ctx.line is not None else ""
    body = []
    for p in shown:
        tip = ' <span class="same__tip">(tipped jobs)</span>' if p.cip in TIPPED_CIP4 else ""
        med = money(p.median) if p.median is not None else "not published"
        body.append(
            f"        <tr><td>{esc(p.name)}{tip}</td><td>{CREDENTIALS[p.cred]}</td>"
            f'<td class="num"><span class="same__n">{p.above:,} of {p.others:,}</span></td>'
            f'<td class="num">{med}</td></tr>\n'
        )
    gap = ""
    if none:
        listed = ", ".join(_label(p) for p in none[:6])
        rest = f" and {len(none) - 6:,} more" if len(none) > 6 else ""
        whose = (
            "this college&rsquo;s other program"
            if len(none) == 1
            else f"{len(none):,} of this college&rsquo;s programs"
        )
        gap = (
            f'      <p class="same__gap">No other college in {name} has published earnings that '
            f"can be compared with the high-school line for {whose}: {listed}{rest}.</p>\n"
        )
    one = sum(p.one_year for p in shown)
    total = sum(p.others for p in shown)
    horizon = (
        f", with the one-year figure where the four-year one is not published ({one:,} of these "
        f"{total:,})."
        if one
        else "."
    )
    notes = [
        "Each program is counted once, at colleges other than this one: campuses that share one "
        "federal institution ID share ED&rsquo;s figures and count as one, and campuses under "
        f"this college&rsquo;s ID are left out. Each is judged against the {name} line, as on "
        "its own profile. Median earnings is the middle of those programs&rsquo; medians, "
        "measured up to four years after finishing" + horizon
    ]
    if any(p.cip in TIPPED_CIP4 for p in shown):
        notes.append(
            "The federal earnings test holds programs for tipped jobs, cosmetology among them, out "
            'of its first rounds. <a href="/earnings-test/">What the test is</a>.'
        )
    return (
        head + '      <p class="same__lede">ED publishes no earnings for this college&rsquo;s '
        f"undergraduate programs. It does for the same programs at other colleges in {name}. "
        "<b>These are other colleges&rsquo; graduates, not this college&rsquo;s.</b> They show "
        "what graduates of the same program earned elsewhere in the state, not what this "
        f"college&rsquo;s graduates earn.{more}</p>\n"
        '      <div class="tscroll same" tabindex="0" role="region" aria-label="The same programs '
        f'at other colleges in {name}"><table class="t"><thead><tr><th>Program</th>'
        "<th>Credential</th>"
        f'<th class="num">At other colleges: above the high-school line{line}</th>'
        '<th class="num">Their median earnings</th></tr></thead><tbody>\n'
        + "".join(body)
        + "      </tbody></table></div>\n"
        + gap
        + "".join(f'      <p class="tw-source">{n}</p>\n' for n in notes)
        + "    </section>\n"
    )
