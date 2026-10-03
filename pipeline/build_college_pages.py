"""Generate static, crawlable HTML pages: one per college, one per state, plus a
national index. This is the search-volume engine: a family searching a school's name
lands on a pre-rendered page with the real facts baked into HTML, then can open the
interactive tool for the full breakdown.

Pages written under site/ (generated at deploy, not committed):
  * /college/<slug>/index.html    one per school with at least one earnings verdict
  * /colleges/<state>/index.html  that state's schools, with verdict summaries
  * /colleges/index.html          national A-Z index (the crawl path)
  * /sitemap.xml                  regenerated to include every page above

Reuses build_site.build_model so every page shows the same aggregates as the app.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_college_pages
"""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict

import duckdb

from pipeline.build_site import build_model
from pipeline.config import ROOT
from pipeline.og_images import card as render_card
from pipeline.tokens_gen import BRAND_DEEP, GOOD

SITE = ROOT / "site"
BASE = "https://truewise.dev"

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "PR": "Puerto Rico",
    "GU": "Guam",
    "VI": "U.S. Virgin Islands",
    "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
    "FM": "Micronesia",
    "MH": "Marshall Islands",
    "PW": "Palau",
}

BEACON = (
    "  <!-- Cloudflare Web Analytics: cookieless, aggregate, no personal data. "
    "Token injected at deploy from the CF_BEACON_TOKEN secret. -->\n"
    '  <script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
    'data-cf-beacon=\'{"token": "CF_BEACON_TOKEN"}\'></script>\n'
)


# 461 schools carry the state code "ZZ", which is not a state: they have no city and no state
# earnings benchmark either, so it is the source data's "not reported" bucket. Rendering it as if
# it were a place put "a typical ZZ high-school graduate" into the body copy of 461 live pages and
# titled a hub "Colleges in ZZ". That is the same failure as showing a suppressed value as 0, and
# the honesty rules forbid it: unknown is labelled unknown.
#
# The URL keeps its /colleges/zz/ slug, because published routes are a frozen contract. Only what a
# reader sees changes.
UNKNOWN_STATE_LABEL = "Location not reported"


def profile_meta(s: dict, pmeta: dict, in_institution_file: bool) -> dict:
    """What canonical_page needs to know about a school, from the model and the program pass.

    The shared-OPEID note and the no-benchmark reason both depend on the last three keys. The note
    was written in Phase 1 but an earlier version of this dict dropped them, so it appeared on no
    page (found 27 September 2026)."""
    opeid = pmeta.get("opeid6")
    return {
        "name": s["name"],
        "state": s["state"],
        "control": s.get("control"),
        "city": s.get("city"),
        "shared": int(pmeta.get("shared") or 0),
        "opeid6": opeid if isinstance(opeid, str) and opeid else None,
        "in_institution_file": in_institution_file,
    }


def known_state(st) -> bool:
    return st in STATE_NAMES


def state_label(st) -> str:
    """Human-readable place for a state code, or an honest label when the code is not a state."""
    return STATE_NAMES.get(st, UNKNOWN_STATE_LABEL)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "school"


def money(n) -> str:
    """Money for a reader. The sign goes OUTSIDE the currency symbol.

    "$-2,533" is what naive formatting produces and it reads as a bug rather than a number. It is
    on 38 profiles, because a College Scorecard net price genuinely goes negative when grant aid
    exceeds the published cost of attendance: MIT's lowest income band is one. The figure is real
    and stays, correctly written.
    """
    if n is None:
        return "n/a"
    v = int(round(n))
    return f"-${abs(v):,}" if v < 0 else f"${v:,}"


# Styles shared by every generated page (profiles, majors, lists, findings, updates, state indexes).
# They used to be inlined by head(), the same 6.8KB in each of 6,500+ pages, so a reader paid for
# them again on every page and no page could share a cached copy. They now ship once as /pg.css,
# written by ensure_pg_css() whenever head() runs and fingerprinted by version_assets like the
# other two sheets. The link sits exactly where the inline block was, after /components.css, so the
# cascade is unchanged.
PG_CSS = """/* One page shell for the whole site. The main element keeps the shared .wrap container, the
   same one the header and the app pages use, and the 860px column sits against its left edge
   rather than centring. So a page title starts where the logo starts on every page, instead of
   jumping 150px sideways between a profile and Careers. The column cap is on the children, and
   the horizontal gutter is the one .wrap already gives: 40px, then 20px on phones. */
.pg { padding-top: 8px; padding-bottom: 64px; }
/* :where() gives the cap zero specificity, so any narrower measure a child sets (source notes,
   prose at var(--measure)) still wins. The first version of this rule overrode them all. */
:where(.pg) > * { max-width: 860px; }
/* Type below is token-only. Every size here used to be an ad-hoc rem value, because
   design/tokens.json had no type block for this file to reach for; it has one now, so a step
   change lands on 6,127 profiles and the homepage together instead of one or the other. */
.crumbs { font-size: var(--t-fine); color: var(--ink-faint); margin: 18px 0 6px; }
.crumbs a { color: var(--ink-soft); text-decoration: underline; text-underline-offset: 0.16em; }
.pg h1 { font-size: var(--t-title); letter-spacing: -0.03em; line-height: 1.08; margin: 6px 0 6px; }
.idline { color: var(--ink-soft); font-size: var(--t-ui); max-width: var(--measure-tight); margin: 0 0 18px; }
.offname { color: var(--ink-faint); }
.progsub { color: var(--ink-faint); font-size: var(--t-fine); display: block; margin-top: 2px; }
/* The verdict is the argument of the page, set in the editorial serif. Like every block on the page
   it runs to the shared 860px edge: capped narrower, it and the calculator each ended at their own
   width and the page's right edge stepped in and out (September 2026 review). */
.verdict { border-left: 4px solid var(--brand); background: var(--bg-alt); border-radius: 0 var(--r-lg) var(--r-lg) 0; padding: 16px 20px; margin: 16px 0; font-family: var(--display); font-size: var(--t-lede); line-height: 1.5; }
.verdict__text { max-width: var(--measure); margin: 0; }
.verdict b { color: var(--ink); }
/* Caution tokens, 4.67 on their own background; the pill also states its meaning in words. */
.gem { display: inline-block; background: var(--caution-bg); color: var(--caution); border: 1px solid var(--caution); border-radius: var(--r-pill); padding: 2px 10px; font-size: var(--t-label); font-weight: 600; margin-left: 6px; }
.cta-row { margin: 18px 0 8px; }
h2.sec { font-size: var(--t-section); letter-spacing: -0.02em; line-height: 1.2; margin: 30px 0 8px; }
.tscroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 8px 0; }
table.t { width: 100%; border-collapse: collapse; font-size: var(--t-ui); }
table.t th, table.t td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
table.t th { color: var(--ink-soft); font-weight: 600; }
table.t td.num, table.t th.num { text-align: right; font-variant-numeric: tabular-nums; }
table.t a { color: var(--ink); text-decoration: none; }
table.t a:hover { color: var(--brand); text-decoration: underline; }
.pass { color: var(--good); font-weight: 600; }
.fail { color: var(--bad); font-weight: 600; }
/* Diverging "vs a high-school grad" bar: the centre line is the benchmark, green to the
   right means graduates out-earn it, red to the left means they fall short. Bars in a table
   share one scale (the row with the biggest gap fills its half), so lengths are comparable. */
.prem-cell { min-width: 132px; }
.prem-val { display: block; font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
.prem-val.pos { color: var(--good); }
.prem-val.neg { color: var(--bad); }
.pbar { position: relative; height: 7px; margin-top: 5px; background: var(--bg-alt); border-radius: var(--r-sm); }
.pbar::before { content: ""; position: absolute; left: 50%; top: -1px; bottom: -1px; width: 1px; background: var(--line); }
.pbar i { position: absolute; top: 0; height: 100%; min-width: 2px; }
/* Solid token fills: bar length is the datum, so the fill carries no extra meaning. */
.pbar i.pos { left: 50%; background: var(--good); border-radius: 0 var(--r-sm) var(--r-sm) 0; }
.pbar i.neg { right: 50%; background: var(--bad); border-radius: var(--r-sm) 0 0 var(--r-sm); }
@media (prefers-reduced-motion: no-preference) { .pbar i { transition: width .3s ease; } }
.np td.num { font-variant-numeric: tabular-nums; }
.src { color: var(--ink-faint); font-size: var(--t-fine); max-width: var(--measure); margin: 22px 0 0; line-height: 1.5; }
.calc { border: 1px solid var(--line); border-radius: var(--r-lg); padding: 16px 18px; margin: 12px 0 18px; background: var(--bg-alt); }
.calc-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: var(--t-ui); }
.calc-controls select { border: 1px solid var(--line); border-radius: var(--r-md); padding: 7px 10px; font-size: var(--t-ui); background: #fff; color: var(--ink); }
/* The payback sentence is prose about a number, not a control label, so it takes the serif. */
.calc-big { font-family: var(--display); font-size: var(--t-sub); max-width: var(--measure); margin: 14px 0 6px; line-height: 1.5; }
.calc-note { color: var(--ink-soft); font-size: var(--t-fine); max-width: var(--measure); line-height: 1.5; margin: 6px 0 0; }
.dl { margin: 14px 0 4px; }
/* Serves a <button> on the profile calculator and an <a download> on the lists, so it
   declares both. 11px of padding on a 15px step at line-height 1.5 is a 46px target,
   past the 44px floor the phone pass asked for. */
.dl-note { color: var(--ink-faint); font-size: var(--t-fine); }
.upd { border-left: 3px solid var(--line); padding: 2px 0 2px 16px; margin: 20px 0; }
.upd h2.sec { margin: 4px 0 6px; font-size: var(--t-sub); }
.upd-meta { color: var(--ink-soft); font-size: var(--t-ui); max-width: var(--measure); line-height: 1.55; margin: 4px 0; }
.upd-src { color: var(--ink-faint); font-size: var(--t-label); margin: 3px 0; word-break: break-all; }
.mono { font-family: var(--mono); font-size: var(--t-fine); overflow-wrap: anywhere; }
.statecols { columns: 220px 4; column-gap: 20px; margin: 14px 0; }
.statecols a { display: block; padding: 5px 0; color: var(--brand); text-decoration: none; }
ul.schoollist { list-style: none; padding: 0; margin: 12px 0; }
ul.schoollist li { padding: 10px 0; border-bottom: 1px solid var(--line); }
ul.schoollist a { color: var(--brand); text-decoration: none; font-weight: 600; }
ul.schoollist .meta { color: var(--ink-soft); font-size: var(--t-ui); }
/* Simple data tables stack into labelled rows on phones (audit V13). The header script copies each
   column heading onto its cells as data-label and adds .stack, so without JS the table keeps its
   horizontal scroll. The first cell is the row's name and reads as a heading. */
@media (max-width: 520px) {
  table.t.stack thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  table.t.stack, table.t.stack tbody, table.t.stack tr { display: block; width: 100%; }
  table.t.stack tr { border-bottom: 1px solid var(--line); padding: 8px 0; }
  table.t.stack td, table.t.stack th { display: flex; justify-content: space-between; gap: 12px; border: 0; padding: 3px 0; text-align: right; }
  table.t.stack td::before, table.t.stack th::before { content: attr(data-label); color: var(--ink-soft); font-weight: 600; text-align: left; }
  table.t.stack tr > :first-child { display: block; text-align: left; font-weight: 600; color: var(--ink); }
  table.t.stack tr > :first-child::before { content: none; }
}
/* Majors range chart: a phone-width drawing below 560px so its text is not scaled to 6px. */
.ladder--narrow { display: none; }
@media (max-width: 560px) { .ladder--wide { display: none; } .ladder--narrow { display: block; } }
"""

_PG_CSS_WRITTEN = False


def ensure_pg_css() -> None:
    """Write site/pg.css once per process, so any builder that calls head() ships the sheet."""
    global _PG_CSS_WRITTEN
    if _PG_CSS_WRITTEN:
        return
    out = SITE / "pg.css"
    if not out.exists() or out.read_text() != PG_CSS:
        out.write_text(PG_CSS)
    _PG_CSS_WRITTEN = True


def head(title, desc, canonical, extra_ld="", og_image="/og.png") -> str:
    ensure_pg_css()
    og = f"{BASE}{og_image}" if og_image.startswith("/") else og_image
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <link rel="canonical" href="{esc(canonical)}" />
  <meta property="og:site_name" content="Truewise US education data" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="{esc(canonical)}" />
  <meta property="og:image" content="{og}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="{og}" />
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="preload" href="/fonts/source-serif-4-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="preload" href="/fonts/ibm-plex-mono-latin-500-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="/styles.css" />
{extra_ld}  <link rel="stylesheet" href="/pg.css" />
</head>
<body>
  <header class="site-header">
    <a class="skip-link" href="#main">Skip to content</a>
    <div class="wrap">
      <div class="brand-group">
        <a class="brand" href="/">true<span>wise</span></a>
        <span class="brand-tagline">Honest US education data</span>
      </div>
      <nav aria-label="Primary">
        <a href="/careers/">Careers</a>
        <a href="/k12/">High schools</a>
        <a href="/#data">Data</a>
        <a href="/methodology/">Methodology</a>
        <a href="/about/">About</a>
        <a class="nav-cta" href="/value-check/">Find a college</a>
        <details class="nav-toggle">
          <summary aria-label="Menu">&#9776;</summary>
          <div class="menu">
            <a href="/careers/">Careers</a>
            <a href="/k12/">High schools</a>
            <a href="/#data">Data</a>
            <a href="/methodology/">Methodology</a>
            <a href="/about/">About</a>
          </div>
        </details>
      </nav>
    </div>
    <script>document.addEventListener("keydown",function(e){{if(e.key!=="Escape")return;var d=document.querySelector(".nav-toggle[open]");if(d){{d.open=false;d.querySelector("summary").focus();}}}});document.addEventListener("click",function(e){{var d=document.querySelector(".nav-toggle[open]");if(d&&!d.contains(e.target))d.open=false;}});document.addEventListener("DOMContentLoaded",function(){{document.querySelectorAll("table.t").forEach(function(t){{var h=[].map.call(t.querySelectorAll("thead th"),function(x){{return x.textContent.trim();}});if(!h.length)return;t.querySelectorAll("tbody tr").forEach(function(r){{[].forEach.call(r.children,function(c,i){{if(h[i])c.setAttribute("data-label",h[i]);}});}});t.classList.add("stack");}});}});</script>
  </header>
  <span id="main" tabindex="-1"></span>
"""


# The one footer. Every generated page uses this constant and every hand-written page carries the
# same markup, checked by test_every_page_uses_the_one_shared_footer. There were eight variants, and
# the 6,500+ generated pages carried the shortest: no All majors, Lists, Findings or Updates, and
# no "Not affiliated with the U.S. Department of Education", which a site built entirely on the
# Department's data most needs to say. Grouped, with the approved wording, since the homepage
# release (design plan, 30 September 2026); the portfolio context lives on About.
FOOTER = """  <footer class="site-footer">
    <div class="wrap foot">
      <div class="foot__who">
        <p><a class="brand" href="/">true<span>wise</span></a></p>
        <p>Built and maintained by <a href="/about/">Anandraj</a>. Independent, open education data. Not affiliated with the U.S. Department of Education.</p>
        <p><a href="/methodology/">Methodology</a> &middot; <a href="https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction&body=Page%20URL%3A%0AWhat%20looks%20wrong%3A%0AExpected%20value%20and%20source%3A">Report an error</a></p>
      </div>
      <nav class="foot__group" aria-label="Explore"><h2>Explore</h2><ul><li><a href="/value-check/">Find a college</a></li><li><a href="/colleges/">Colleges by state</a></li><li><a href="/compare/">Compare</a></li><li><a href="/careers/">Careers</a></li><li><a href="/majors/">Majors</a></li><li><a href="/k12/">High schools</a></li></ul></nav>
      <nav class="foot__group" aria-label="Research"><h2>Research</h2><ul><li><a href="/findings/">Findings</a></li><li><a href="/lists/">Lists</a></li><li><a href="/updates/">Updates and corrections</a></li><li><a href="/data/value_check.parquet">Download the data</a></li><li><a href="https://github.com/ndranandraj/truewise">Source on GitHub</a></li></ul></nav>
    </div>
  </footer>
"""


def _median(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def render_og_card(s, slug, rows=None) -> None:
    """Write this school's Open Graph share card, one per school, for the canonical profile (which
    references the card but does not render it).

    Given the profile's rows, the card counts what the profile's headline counts: undergraduate
    programs with a verdict (profile release, 30 September 2026), so a shared card never states a
    figure the page does not."""
    name = s["name"]
    st_name = state_label(s["state"])
    passed, fail = s["n_pass"], s["n_fail"]
    kind = "Programs"
    if rows is not None:
        ug = [r for r in rows if not r.get("grad")]
        if any(r["verdict"] in ("pass", "fail") for r in ug):
            rows, kind = ug, "Undergraduate programs"
        passed = sum(1 for r in rows if r["verdict"] == "pass")
        fail = sum(1 for r in rows if r["verdict"] == "fail")
    decided = passed + fail
    if decided and fail:
        card_big, card_color = f"{passed} of {decided} clear the bar", BRAND_DEEP
    elif decided:
        card_big, card_color = f"All {decided} clear the bar", GOOD
    else:
        card_big, card_color = None, BRAND_DEEP
    render_card(
        SITE / "og" / "college" / f"{slug}.png",
        "College · graduate earnings vs a high-school grad",
        name,
        big=card_big,
        big_color=card_color,
        sub=f"{kind} whose graduates out-earn a typical {st_name} high-school graduate.",
    )


def _json(s) -> str:
    import json as _j

    return _j.dumps(s if s is not None else "")


def state_index(st, schools_in_state) -> str:
    st_name = state_label(st)
    canonical = f"{BASE}/colleges/{st.lower()}/"
    n = len(schools_in_state)
    total_fail = sum(s["n_fail"] for _, s, _ in schools_in_state)
    title = (
        f"Colleges in {st_name}: what graduates earn vs a high-school grad"
        if known_state(st)
        else "Colleges with no reported location: what graduates earn"
    )
    desc = (
        f"{n} {st_name} colleges by what families pay and whether graduates out-earn a "
        "typical high-school graduate. Program-level earnings from federal data."
        if known_state(st)
        else f"{n} colleges whose state is not reported in the federal data, by what "
        "families pay and what graduates earn."
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Colleges","item":"{BASE}/colleges/"}},
    {{"@type":"ListItem","position":2,"name":{_json(st_name)},"item":"{canonical}"}}
  ]}}
  </script>
"""
    parts = [head(title, desc, canonical, ld)]
    parts.append('  <main class="wrap pg">\n')
    parts.append(
        '    <nav class="crumbs"><a href="/colleges/">Colleges</a> &rsaquo; '
        + esc(st_name)
        + "</nav>\n"
    )
    # "Colleges in Location not reported" is not a sentence; the unlocated hub gets its own.
    heading = (
        f"Colleges in {esc(st_name)}" if known_state(st) else "Colleges with no reported location"
    )
    parts.append(f"    <h1>{heading}</h1>\n")
    # For the unlocated hub, "0 programs statewide fall short" would read as a clean bill of
    # health when the truth is that none could be assessed: those schools have no state benchmark,
    # so no program CAN fall short. Saying nothing was measured is the honest line, and "statewide"
    # is not a word that applies to a group with no state.
    # Counts are per campus page, so a program ED reports for several campuses appears on each.
    total_dec = sum(s["n_pass"] + s["n_fail"] for _, s, _ in schools_in_state)
    if not known_state(st):
        lede = None
    elif total_dec:
        lede = (
            f"{n} school{'' if n == 1 else 's'}. Across their pages, {total_dec:,} programs have an "
            f"earnings verdict and {total_fail:,} fall short of a typical {esc(st_name)} "
            "high-school graduate."
        )
    else:
        lede = (
            f"{n} school{'' if n == 1 else 's'}. None of their programs can be judged here: the "
            f"federal data has no high-school earnings benchmark for {esc(st_name)}, so programs "
            "are listed without a verdict."
        )
    lede = (
        lede
        if known_state(st)
        else f"{n} schools whose state the federal data does not report. Without a state, there is "
        "no state high-school-graduate benchmark to compare against, so their programs are listed "
        "but not judged."
    )
    parts.append(f'    <p class="idline">{lede}</p>\n')
    # Some federal records share a name within a state (branch campuses, chains like "Maestro
    # College"). Two identical links read like a bug, so where a name repeats we fold the city
    # into the link text itself (and drop it from the meta line to avoid saying it twice).
    name_counts: dict[str, int] = defaultdict(int)
    for _, s, _ in schools_in_state:
        name_counts[s["name"]] += 1
    parts.append('    <ul class="schoollist">\n')
    for slug, s, _ in sorted(schools_in_state, key=lambda x: (x[1]["name"] or "").lower()):
        decided = s["n_pass"] + s["n_fail"]
        summ = (
            f"{decided} programs with earnings data, {s['n_fail']} fall short"
            if decided
            else "no programs with enough data for an earnings verdict yet"
        )
        dup_city = name_counts[s["name"]] > 1 and s.get("city")
        label = esc(s["name"]) + (f" ({esc(s['city'])})" if dup_city else "")
        city = "" if dup_city else (f"{esc(s['city'])} &middot; " if s.get("city") else "")
        parts.append(
            f'      <li><a href="/college/{slug}/">{label}</a><div class="meta">{city}{summ}</div></li>\n'
        )
    parts.append("    </ul>\n")
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def national_index(states_present, profiled=None, searchable=None) -> str:
    canonical = f"{BASE}/colleges/"
    title = "All US colleges: what families pay and what graduates earn"
    desc = (
        "Browse every US college by state to see net price by income and whether each program's "
        "graduates out-earn a typical high-school graduate. Built on public federal data."
    )
    parts = [head(title, desc, canonical)]
    parts.append('  <main class="wrap pg">\n')
    parts.append('    <nav class="crumbs">Colleges</nav>\n')
    parts.append("    <h1>All US colleges</h1>\n")
    parts.append(
        '    <p class="idline">Pick a state, or <a href="/value-check/">search for a school by name</a>. Every page shows net price by income and whether graduates out-earn a typical high-school graduate.</p>\n'
    )
    # Explain the coverage gap up front: the directory profiles schools with at least one program
    # we can judge on earnings; the rest are searchable but privacy-suppressed, so they have no
    # full page. Counts are passed in from the model so they cannot drift from the data.
    if profiled and searchable and searchable > profiled:
        parts.append(
            f'    <p class="src">We profile the <b>{profiled:,}</b> colleges that have at least one '
            f"program we can judge on earnings. Another <b>{searchable - profiled:,}</b> are searchable "
            f"but have no full profile because all of their programs are privacy-suppressed by the "
            f"Department of Education for small cohorts.</p>\n"
        )
    parts.append('    <div class="statecols">\n')
    # Unrecognised codes sort last under their honest label rather than alphabetically as "ZZ".
    for st in sorted(states_present, key=lambda s: (not known_state(s), state_label(s))):
        parts.append(f'      <a href="/colleges/{st.lower()}/">{esc(state_label(st))}</a>\n')
    parts.append("    </div>\n")
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def qualifying_schools(schools: dict) -> dict:
    """Schools that get a /college/ profile. Widened at the Stage 5 cutover from verdict-only to ANY
    school with at least one program, so the ~1,178 all-insufficient schools also get a truthful
    no-verdict profile. This keeps every searchable school addressable and the retired ?school=<id>
    redirect never dead-ends. The value-check rankings/lists still exclude no-verdict schools in SQL,
    so this only affects which schools get a page and a slug."""
    return {
        u: s
        for u, s in schools.items()
        if (s["n_pass"] + s["n_fail"] + s.get("n_insufficient", 0)) >= 1
    }


def build_slugs(qualified: dict) -> dict[str, str]:
    """College slugs, from the committed registry. Shared by every builder that links to a profile.

    This used to derive slugs from the data on each call, breaking name ties on the order rows
    arrived in. For the 18 same-name pairs that made the result depend on DuckDB's row order, which
    varies between processes: twelve fresh runs produced the live mapping nine times and an
    alternate mapping (36 unitids moved) three times. Since college pages, lists and canonical
    profiles each call this in a SEPARATE process, one deploy could publish a page at one slug and
    link to it at another.

    published/slug_registry.json now holds the mapping, so a published URL cannot move. See that
    module for why a deterministic tie-break was not enough on its own.

    Resolution is STRICT: an unregistered institution raises rather than being given an invented
    slug. Run `make slug-registry` and commit the diff to publish a new college.
    """
    from pipeline.slug_registry import resolve

    return resolve(qualified)


def main() -> None:
    # Stage 5 cutover: /college/<slug>/ is now the FULL canonical profile (delivery model: static core
    # + JSON island + progressive tail), rendered by canonical_page. Lazy import breaks the cycle with
    # build_canonical_profiles, which imports chrome helpers from here.
    from pipeline.build_canonical_profiles import CSV_MIN_PROGRAMS, LIVE_STATIC_ROWS, canonical_page
    from pipeline.build_profile_pilot import all_profiles

    con = duckdb.connect()
    schools, by_state, _ = build_model(con)

    qualified = qualifying_schools(schools)
    slugs = build_slugs(qualified)
    profiles = all_profiles(con)  # one-pass {unitid: (meta, rows)} from the parquet
    inst_path = ROOT / "published" / "institutions.parquet"
    in_file = (
        {r[0] for r in con.sql(f"SELECT unitid FROM '{inst_path}'").fetchall()}
        if inst_path.exists()
        else set()
    )

    col_dir = SITE / "college"
    col_dir.mkdir(parents=True, exist_ok=True)
    partial: dict = {}  # profiles that get programs.csv
    states_present: dict[str, list] = defaultdict(list)
    for u, s in qualified.items():
        slug = slugs[u]
        pmeta, rows = profiles.get(u, ({}, []))
        meta = profile_meta(s, pmeta, u in in_file)
        html, tail_json = canonical_page(
            meta, rows, slug, s.get("threshold"), LIVE_STATIC_ROWS, s.get("net_price")
        )
        d = col_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
        if tail_json:
            (d / "programs-tail.json").write_text(tail_json)
        if tail_json or len(rows) > CSV_MIN_PROGRAMS:
            partial[u] = d
        render_og_card(s, slug, rows)
        states_present[s["state"]].append((slug, s, u))

    # The complete program list as CSV for every profile with more than 150 programs (245 schools).
    # Not all 6,127: the static-asset host caps a deploy's file count, and one file per school would
    # bring the site close to it. Smaller schools' tables are short enough to read or copy whole.
    from pipeline import build_site as _bs
    from pipeline.build_canonical_profiles import PROGRAMS_CSV, programs_csv

    for u, text in programs_csv(con, _bs.PARQUET_DIR / "value_check.parquet", partial).items():
        (partial[u] / PROGRAMS_CSV).write_text(text)

    colleges_dir = SITE / "colleges"
    colleges_dir.mkdir(parents=True, exist_ok=True)
    for st, lst in states_present.items():
        d = colleges_dir / st.lower()
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(state_index(st, lst))
    (colleges_dir / "index.html").write_text(
        national_index(states_present.keys(), profiled=len(qualified), searchable=len(schools))
    )

    # Publish the UNITID -> canonical slug map. The Stage 4 consolidation retires
    # /value-check/?school=<id> in favour of /college/<slug>/; because Cloudflare cannot redirect on a
    # query parameter, the discovery page resolves ?school=<id> to its slug CLIENT-SIDE from this map
    # (slugs are collision-adjusted, so the slug cannot be recomputed from the name alone). Every
    # school with a /college/ page appears here exactly once; the redirect is wired at the Stage 5
    # cutover, not before.
    (col_dir / "slug-map.json").write_text(
        json.dumps({u: slugs[u] for u in qualified}, separators=(",", ":"))
    )

    print(f"college pages: {len(qualified):,}  |  state indexes: {len(states_present)}")
    print(f"wrote -> {col_dir} and {colleges_dir} (+ slug-map.json)")
    print("run pipeline.build_sitemap after the page builders to refresh sitemap.xml")


if __name__ == "__main__":
    main()
