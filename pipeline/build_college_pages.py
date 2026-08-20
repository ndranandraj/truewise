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
import re
from collections import defaultdict

import duckdb

from pipeline.build_site import build_model
from pipeline.cip_names import has_plain_name, plain_name, tidy_official
from pipeline.config import ROOT
from pipeline.og_images import BRAND_DEEP, GOOD
from pipeline.og_images import card as render_card

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


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "school"


def money(n) -> str:
    return "n/a" if n is None else "$" + f"{int(round(n)):,}"


def head(title, desc, canonical, extra_ld="", og_image="/og.png") -> str:
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
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="{og}" />
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/styles.css" />
{extra_ld}  <style>
    .pg {{ max-width: 860px; padding: 8px 0 64px; }}
    .crumbs {{ font-size: .85rem; color: var(--ink-faint); margin: 18px 0 6px; }}
    .crumbs a {{ color: var(--ink-soft); text-decoration: none; }}
    .pg h1 {{ font-size: clamp(1.7rem, 4vw, 2.5rem); letter-spacing: -0.03em; margin: 6px 0 6px; }}
    .idline {{ color: var(--ink-soft); font-size: 1.02rem; margin: 0 0 18px; }}
    .offname {{ color: var(--ink-faint); }}
    .progsub {{ color: var(--ink-faint); font-size: .82rem; display: block; margin-top: 2px; }}
    .verdict {{ border-left: 4px solid var(--brand); background: var(--bg-alt); border-radius: 0 12px 12px 0; padding: 16px 20px; margin: 16px 0; font-size: 1.05rem; line-height: 1.6; }}
    .verdict b {{ color: var(--ink); }}
    .gem {{ display: inline-block; background: #fff7e6; color: #8a6d1a; border: 1px solid #f0d999; border-radius: 999px; padding: 2px 10px; font-size: .85rem; font-weight: 700; margin-left: 6px; }}
    .cta-row {{ margin: 18px 0 8px; }}
    .cta-row a.primary {{ display: inline-block; background: var(--brand); color: #fff; font-weight: 700; text-decoration: none; padding: 11px 18px; border-radius: 10px; }}
    h2.sec {{ font-size: 1.2rem; letter-spacing: -0.02em; margin: 30px 0 8px; }}
    .tscroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 8px 0; }}
    table.t {{ width: 100%; border-collapse: collapse; font-size: .93rem; }}
    table.t th, table.t td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    table.t th {{ color: var(--ink-soft); font-weight: 600; }}
    table.t td.num, table.t th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    table.t a {{ color: var(--ink); text-decoration: none; }}
    table.t a:hover {{ color: var(--brand); text-decoration: underline; }}
    .pass {{ color: var(--good); font-weight: 600; }}
    .fail {{ color: var(--bad); font-weight: 600; }}
    /* Diverging "vs a high-school grad" bar: the centre line is the benchmark, green to the
       right means graduates out-earn it, red to the left means they fall short. Bars in a table
       share one scale (the row with the biggest gap fills its half), so lengths are comparable. */
    .prem-cell {{ min-width: 132px; }}
    .prem-val {{ display: block; font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }}
    .prem-val.pos {{ color: var(--good); }}
    .prem-val.neg {{ color: var(--bad); }}
    .pbar {{ position: relative; height: 7px; margin-top: 5px; background: var(--bg-alt); border-radius: 4px; }}
    .pbar::before {{ content: ""; position: absolute; left: 50%; top: -1px; bottom: -1px; width: 1px; background: var(--line); }}
    .pbar i {{ position: absolute; top: 0; height: 100%; min-width: 2px; }}
    .pbar i.pos {{ left: 50%; background: linear-gradient(90deg, #17936a, var(--good)); border-radius: 0 4px 4px 0; }}
    .pbar i.neg {{ right: 50%; background: linear-gradient(270deg, #c23522, var(--bad)); border-radius: 4px 0 0 4px; }}
    @media (prefers-reduced-motion: no-preference) {{ .pbar i {{ transition: width .3s ease; }} }}
    .np td.num {{ font-variant-numeric: tabular-nums; }}
    .src {{ color: var(--ink-faint); font-size: .85rem; margin: 22px 0 0; line-height: 1.5; }}
    .calc {{ border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin: 12px 0 18px; background: var(--bg-alt); max-width: 720px; }}
    .calc-controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: .98rem; }}
    .calc-controls select {{ border: 1px solid var(--line); border-radius: 9px; padding: 7px 10px; font-size: .98rem; background: #fff; color: var(--ink); }}
    .calc-big {{ font-size: 1.12rem; margin: 14px 0 6px; line-height: 1.5; }}
    .calc-note {{ color: var(--ink-soft); font-size: .86rem; line-height: 1.5; margin: 6px 0 0; }}
    .dl {{ margin: 14px 0 4px; }}
    .dl-btn {{ border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 10px; padding: 9px 14px; font-size: .92rem; font-weight: 600; cursor: pointer; }}
    .dl-btn:hover {{ background: var(--bg-alt); }}
    .dl-note {{ color: var(--ink-faint); font-size: .85rem; }}
    .upd {{ border-left: 3px solid var(--line); padding: 2px 0 2px 16px; margin: 20px 0; }}
    .upd h2.sec {{ margin: 4px 0 6px; font-size: 1.1rem; }}
    .upd-meta {{ color: var(--ink-soft); font-size: .92rem; line-height: 1.55; margin: 4px 0; }}
    .upd-src {{ color: var(--ink-faint); font-size: .8rem; margin: 3px 0; word-break: break-all; }}
    .mono {{ font-family: var(--mono); font-size: .82rem; overflow-wrap: anywhere; }}
    .statecols {{ columns: 220px 4; column-gap: 20px; margin: 14px 0; }}
    .statecols a {{ display: block; padding: 5px 0; color: var(--brand); text-decoration: none; }}
    ul.schoollist {{ list-style: none; padding: 0; margin: 12px 0; }}
    ul.schoollist li {{ padding: 10px 0; border-bottom: 1px solid var(--line); }}
    ul.schoollist a {{ color: var(--brand); text-decoration: none; font-weight: 600; }}
    ul.schoollist .meta {{ color: var(--ink-soft); font-size: .9rem; }}
  </style>
</head>
<body>
  <header class="site-header">
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
  </header>
"""


FOOTER = """  <footer class="site-footer">
    <div class="wrap">
      <p><a class="brand" href="/">true<span>wise</span></a> &nbsp; Built on public data &middot; <a href="/colleges/">All colleges</a> &middot; <a href="/compare/">Compare</a> &middot; <a href="/methodology/">Methodology</a> &middot; <a href="/about/">About</a> &middot; <a href="https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction&body=Page%20URL%3A%0AWhat%20looks%20wrong%3A%0AExpected%20value%20and%20source%3A">Report an error</a></p>
    </div>
  </footer>
"""


def _program_rows(programs, threshold):
    """Top programs for a school, decided ones first, by completers."""
    decided = [
        p
        for p in programs
        if p.get("flag") in ("passes_earnings_premium", "fails_earnings_premium")
    ]
    decided.sort(key=lambda p: p.get("completers") or 0, reverse=True)
    shown = decided[:15]
    # One shared scale for all the bars in this table: the largest gap (either direction) fills
    # its half, so a reader can compare row lengths directly. Guard against an all-zero table.
    prems = [
        (p["earnings"] - threshold)
        for p in shown
        if p.get("earnings") is not None and threshold is not None
    ]
    max_abs = max((abs(v) for v in prems), default=0) or 1
    out = []
    for p in shown:
        earn = p.get("earnings")
        prem = (earn - threshold) if (earn is not None and threshold is not None) else None
        prem_cell = "<td class='num'>n/a</td>"
        if prem is not None:
            sign_cls = "pos" if prem >= 0 else "neg"
            prem_txt = ("+$" if prem >= 0 else "-$") + f"{int(round(abs(prem))):,}"
            width = round(abs(prem) / max_abs * 50, 1)
            prem_cell = (
                f"<td class='prem-cell'><span class='prem-val {sign_cls}'>{prem_txt}</span>"
                f"<span class='pbar' aria-hidden='true'><i class='{sign_cls}' "
                f"style='width:{width}%'></i></span></td>"
            )
        verdict = (
            '<span class="pass">clears the bar</span>'
            if p.get("flag") == "passes_earnings_premium"
            else '<span class="fail">falls short</span>'
        )
        payback = p.get("payback")
        if payback is None:
            pay_txt = "n/a"
        elif p.get("flag") != "passes_earnings_premium":
            pay_txt = "none"
        else:
            pay_txt = f"{payback:g} yr" + ("" if payback == 1 else "s")
        # Sample size belongs next to the median. A median over 11 graduates and one over 800
        # otherwise render identically, which is the biggest thing a reader needs to weigh.
        n = p.get("completers")
        n_txt = f"{int(n):,}" if n else "n/a"
        # Lead with the name a person would use; keep the federal label underneath so the row is
        # still traceable to the CIP it came from.
        prog_official = tidy_official(p.get("program"))
        prog_plain = plain_name(p.get("cip"), p.get("program"))
        prog_cell = esc(prog_plain)
        if has_plain_name(p.get("cip")) and prog_official.lower() != prog_plain.lower():
            prog_cell += f'<span class="progsub">{esc(prog_official)}</span>'
        out.append(
            f"<tr><td>{prog_cell}</td><td>{esc(p.get('credential'))}</td>"
            f"<td class='num'>{n_txt}</td>"
            f"<td class='num'>{money(earn)}</td>{prem_cell}"
            f"<td>{verdict}</td><td class='num'>{money(p.get('debt'))}</td>"
            f"<td class='num'>{pay_txt}</td></tr>"
        )
    return out


def _median(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def _calculator(s, np_, brackets, labels, programs) -> str:
    """An income + years calculator built only from this school's real federal figures.

    Every input is published data (net price by income bracket; the school's median debt
    payback in years). The multi-year total is an explicit arithmetic illustration, and the
    page states the assumptions rather than implying a forecast.
    """
    import json as _j

    payback = _median(
        [p.get("payback") for p in programs if p.get("flag") == "passes_earnings_premium"]
    )
    data = {
        "brackets": brackets,
        "avg": np_.get("avg"),
        "payback": payback,
    }
    opts = "".join(
        f'<option value="{i}"{"" if b is not None else " disabled"}>{lab}'
        f"{'' if b is not None else ' (not reported)'}</option>"
        for i, (lab, b) in enumerate(zip(labels, brackets, strict=False))
    )
    return (
        '    <div class="calc">\n'
        f'      <script type="application/json" id="calc-data">{_j.dumps(data)}</script>\n'
        '      <div class="calc-controls">\n'
        '        <label for="calc-income">My family earns</label>\n'
        f'        <select id="calc-income">{opts}<option value="-1">Not sure, show the average</option></select>\n'
        '        <label for="calc-years">and I expect to take</label>\n'
        '        <select id="calc-years">'
        '<option value="2">2 years</option>'
        '<option value="4" selected>4 years</option>'
        '<option value="5">5 years</option>'
        '<option value="6">6 years</option></select>\n'
        "      </div>\n"
        '      <div class="calc-out" id="calc-out"></div>\n'
        "    </div>\n"
        "    <script>\n"
        "    (function () {\n"
        '      var el = document.getElementById("calc-data"); if (!el) return;\n'
        "      var D = JSON.parse(el.textContent);\n"
        '      var inc = document.getElementById("calc-income"), yrs = document.getElementById("calc-years"),\n'
        '          out = document.getElementById("calc-out");\n'
        '      var money = function (n) { return n == null ? "not reported" : "$" + Math.round(n).toLocaleString(); };\n'
        "      function render() {\n"
        "        var i = parseInt(inc.value, 10), y = parseInt(yrs.value, 10);\n"
        "        var per = i < 0 ? D.avg : D.brackets[i];\n"
        "        if (per == null) { out.innerHTML = "
        "\"<p class='calc-note'>Net price is not reported for that income band at this school.</p>\"; return; }\n"
        "        var total = per * y;\n"
        "        var h = '<p class=\"calc-big\">About <b>' + money(per) + '</b> per year, "
        "or <b>' + money(total) + '</b> over ' + y + ' years.</p>';\n"
        "        if (D.payback != null) {\n"
        '          h += \'<p class="calc-note">Graduates of this school\\u2019s programs that clear the '
        "earnings bar typically recoup what they borrowed in about <b>' + D.payback + ' year' + "
        "(D.payback == 1 ? '' : 's') + '</b> of their earnings premium over a typical high-school graduate.</p>';\n"
        "        }\n"
        '        h += \'<p class="calc-note">This is arithmetic on published figures, not a quote or a '
        "prediction: it multiplies the reported net price for that income band by the number of years you "
        "choose. It assumes aid and price stay flat, and it does not include interest, living costs beyond "
        "those already in net price, or your odds of finishing. Net price reflects students who received "
        "federal aid, in the most recent reported year.</p>';\n"
        "        out.innerHTML = h;\n"
        "      }\n"
        '      inc.addEventListener("change", render); yrs.addEventListener("change", render);\n'
        "      render();\n"
        "    })();\n"
        "    </script>\n"
    )


def college_page(s, programs, slug) -> str:
    name = s["name"]
    st = s["state"]
    st_name = STATE_NAMES.get(st, st)
    canonical = f"{BASE}/college/{slug}/"
    decided = s["n_pass"] + s["n_fail"]
    fail, passed = s["n_fail"], s["n_pass"]
    threshold = s.get("threshold")

    # Identity line.
    bits = []
    if s.get("city"):
        bits.append(f"{esc(s['city'])}, {esc(st_name)}")
    else:
        bits.append(esc(st_name))
    if s.get("control"):
        bits.append(esc(s["control"]))
    if s.get("enrollment"):
        bits.append(f"{s['enrollment']:,} undergraduates")
    idline = " &middot; ".join(bits)

    # Headline verdict + meta description (with a real number).
    thr_txt = money(threshold)
    if decided and fail:
        desc = (
            f"At {name}, {fail} of {decided} programs with reported earnings leave graduates "
            f"earning less than a typical {st_name} high-school graduate. See net price by income "
            f"and program-by-program earnings, from federal data."
        )
        verdict = (
            f"Of <b>{decided}</b> programs with reported earnings, <b>{passed}</b> leave graduates "
            f"out-earning a typical {esc(st_name)} high-school graduate (about {thr_txt}/yr) and "
            f"<b>{fail}</b> fall short."
        )
    elif decided:
        desc = (
            f"At {name}, all {decided} programs with reported earnings leave graduates out-earning a "
            f"typical {st_name} high-school graduate. Net price by income and program earnings, from federal data."
        )
        verdict = (
            f"All <b>{decided}</b> programs with reported earnings leave graduates out-earning a typical "
            f"{esc(st_name)} high-school graduate (about {thr_txt}/yr)."
        )
    else:
        desc = (
            f"{name}: net price by income and program data from the U.S. Department of Education."
        )
        verdict = "Earnings data is privacy-suppressed for this school's programs."
    if s.get("n_insufficient"):
        verdict += (
            f" Another <b>{s['n_insufficient']}</b> programs did not have enough data to judge."
        )

    # Survivorship, stated where the judgement is made rather than in a footnote.
    # Every earnings figure above describes students who FINISHED. At a school where most
    # students do not finish, the verdict describes a surviving minority, and the people who
    # left with debt and no credential are invisible in it. We measured this across the data:
    # at every completion level from 0% to 33%, roughly 85-99% of programs still "clear the
    # bar", so the verdict barely moves with completion. That is precisely why the two belong
    # in the same sentence. Below 50% we name the number; above it we still say "graduates".
    comp = s.get("completion")
    if decided:
        if comp is not None and comp < 0.5:
            verdict += (
                f" These figures describe students who finished, and at this school about "
                f"<b>{round(comp * 100)}%</b> of students complete their program, so they do not "
                f"describe the majority who leave without a credential."
            )
        else:
            verdict += " These figures describe students who finished, not those who left early."

    gem = ' <span class="gem">★ Hidden gem</span>' if s.get("hidden_gem") else ""
    title = f"{name}: what families pay and what graduates earn"

    # Structured data.
    addr = (
        f'"address": {{"@type": "PostalAddress", "addressLocality": "{esc(s.get("city") or "")}", "addressRegion": "{esc(st)}", "addressCountry": "US"}},'
        if s.get("city")
        else ""
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"CollegeOrUniversity","name":{_json(name)},{addr}"url":"{canonical}"}}
  </script>
  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Colleges","item":"{BASE}/colleges/"}},
    {{"@type":"ListItem","position":2,"name":{_json(st_name)},"item":"{BASE}/colleges/{st.lower()}/"}},
    {{"@type":"ListItem","position":3,"name":{_json(name)},"item":"{canonical}"}}
  ]}}
  </script>
"""

    # A share card carrying this school's real pass/fail split, so a posted link is not generic.
    if decided and fail:
        card_big, card_color = f"{passed} of {decided} pay off", BRAND_DEEP
    elif decided:
        card_big, card_color = f"All {decided} pay off", GOOD
    else:
        card_big, card_color = None, BRAND_DEEP
    render_card(
        SITE / "og" / "college" / f"{slug}.png",
        "College · does it pay off?",
        name,
        big=card_big,
        big_color=card_color,
        sub=f"Programs whose graduates out-earn a typical {st_name} high-school graduate.",
    )
    parts = [head(title, desc, canonical, ld, og_image=f"/og/college/{slug}.png")]
    parts.append('  <main class="wrap pg">\n')
    parts.append(
        f'    <nav class="crumbs"><a href="/colleges/">Colleges</a> &rsaquo; <a href="/colleges/{st.lower()}/">{esc(st_name)}</a> &rsaquo; {esc(name)}</nav>\n'
    )
    parts.append(f"    <h1>{esc(name)}{gem}</h1>\n")
    parts.append(f'    <p class="idline">{idline}</p>\n')
    parts.append(f'    <div class="verdict">{verdict}</div>\n')
    parts.append(
        f'    <div class="cta-row"><a class="primary" href="/value-check/?school={esc(s["unitid"])}">See the full breakdown &rarr;</a></div>\n'
    )

    # Net price by income, plus a "what would this cost me" calculator.
    np = s.get("net_price")
    if np and (np.get("avg") is not None or any(np.get("brackets") or [])):
        labels = ["Under $30k", "$30k to $48k", "$48k to $75k", "$75k to $110k", "$110k and up"]
        brackets = list(np.get("brackets") or [None] * 5)
        parts.append('    <h2 class="sec">What would this cost you?</h2>\n')
        parts.append(_calculator(s, np, brackets, labels, programs))
        # The table doubles as the no-JS fallback and the full picture.
        parts.append(
            '    <div class="tscroll"><table class="t np"><thead><tr><th>Family income</th><th class="num">Net price per year</th></tr></thead><tbody>\n'
        )
        for lab, b in zip(labels, brackets, strict=False):
            if b is not None:
                parts.append(f'      <tr><td>{lab}</td><td class="num">{money(b)}</td></tr>\n')
        if np.get("avg") is not None:
            parts.append(
                f'      <tr><td><b>All families (average)</b></td><td class="num"><b>{money(np["avg"])}</b></td></tr>\n'
            )
        parts.append("    </tbody></table></div>\n")
        parts.append(
            '    <p class="src">Net price is the yearly cost after grants and scholarships, by family income (College Scorecard). Credit: TuitionTracker.</p>\n'
        )

    # Program earnings table.
    rows = _program_rows(programs, threshold)
    if rows:
        parts.append('    <h2 class="sec">Program earnings vs a high-school graduate</h2>\n')
        parts.append(
            '    <div class="tscroll"><table class="t"><thead><tr><th>Program</th><th>Credential</th>'
            '<th class="num">Recent completers</th><th class="num">Median earnings</th><th>vs a high-school grad</th>'
            '<th>Verdict</th><th class="num">Median debt</th>'
            '<th class="num">Years of premium to repay</th></tr></thead><tbody>\n'
        )
        parts.append("      " + "\n      ".join(rows) + "\n")
        parts.append("    </tbody></table></div>\n")
        if decided > len(rows):
            parts.append(
                f'    <p class="src">Showing the {len(rows)} largest programs by recent completers. '
                f'"Recent completers" is the number who finished the program in the reporting period; it is '
                f"not the size of the cohort behind the earnings figure. See all {decided} on the "
                f'<a href="/value-check/?school={esc(s["unitid"])}">full profile</a>.</p>\n'
            )

    # Loan repayment: do borrowers actually pay it down?
    rep = s.get("repayment") or {}
    if rep.get("default") is not None or rep.get("declining_3yr") is not None:

        def _rate(key):
            v = rep.get(key)
            if v is None:
                return None
            pct = round(v * 100)
            return f"{pct}% or less" if rep.get(key + "_is_max") else f"{pct}%"

        parts.append('    <h2 class="sec">Do borrowers pay the debt down?</h2>\n')
        bits = []
        if _rate("default"):
            bits.append(f"<b>{_rate('default')}</b> had defaulted")
        if _rate("paid_in_full"):
            bits.append(f"<b>{_rate('paid_in_full')}</b> had already paid in full")
        if bits:
            n_txt = f" of the {rep['n']:,} graduates who borrowed," if rep.get("n") else ""
            parts.append(
                f'    <p class="idline">Two years into repayment,{n_txt} {" and ".join(bits)}.</p>\n'
            )
        if _rate("declining_3yr"):
            parts.append(
                f'    <p class="idline"><b>{_rate("declining_3yr")}</b> of all borrowers from this '
                "school were paying their balance down three years in.</p>\n"
            )
        parts.append(
            '    <p class="src">Loan repayment status of students who <b>completed</b> and borrowed '
            "federally, two years after entering repayment (College Scorecard). Where a figure reads "
            '"or less", the Department of Education censored the exact rate because the group was '
            "small, so the true rate is at or below that number; we show the bound rather than guess "
            "or hide it. The three-year figure counts all borrowers, not only completers.</p>\n"
        )

    # Mobility line.
    mob = []
    if s.get("pell") is not None:
        mob.append(f"{round(s['pell'] * 100)}% of students receive Pell grants")
    if s.get("completion") is not None:
        mob.append(f"{round(s['completion'] * 100)}% complete their program")
    if mob:
        parts.append(f'    <p class="src">Access and outcomes: {" &middot; ".join(mob)}.</p>\n')

    parts.append(
        '    <p class="src">Source: U.S. Department of Education College Scorecard, release 2026-06-10 '
        "(the release date; the graduates described finished several years earlier, which is the most "
        "recent cohort ED publishes). Earnings are median earnings of graduates measured up to four years "
        "after completing, compared to the state high-school-graduate earnings threshold. Debt is federal "
        "student loans only, so private and Parent PLUS borrowing is not included and the true total is "
        "higher. Figures describe past graduates and are never a promise. Method: "
        '<a href="/methodology/">methodology</a>. Something look wrong? '
        '<a href="https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction">Report it</a>.</p>\n'
    )
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def _json(s) -> str:
    import json as _j

    return _j.dumps(s if s is not None else "")


def state_index(st, schools_in_state) -> str:
    st_name = STATE_NAMES.get(st, st)
    canonical = f"{BASE}/colleges/{st.lower()}/"
    n = len(schools_in_state)
    total_fail = sum(s["n_fail"] for _, s, _ in schools_in_state)
    title = f"Colleges in {st_name}: what graduates earn vs a high-school grad"
    desc = (
        f"{n} {st_name} colleges by what families pay and whether graduates out-earn a typical "
        f"high-school graduate. Program-level earnings from federal data."
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
    parts.append(f"    <h1>Colleges in {esc(st_name)}</h1>\n")
    parts.append(
        f'    <p class="idline">{n} schools with earnings data, {total_fail} programs statewide leave graduates earning less than a typical high-school graduate.</p>\n'
    )
    # Some federal records share a name within a state (branch campuses, chains like "Maestro
    # College"). Two identical links read like a bug, so where a name repeats we fold the city
    # into the link text itself (and drop it from the meta line to avoid saying it twice).
    name_counts: dict[str, int] = defaultdict(int)
    for _, s, _ in schools_in_state:
        name_counts[s["name"]] += 1
    parts.append('    <ul class="schoollist">\n')
    for slug, s, _ in sorted(schools_in_state, key=lambda x: (x[1]["name"] or "").lower()):
        decided = s["n_pass"] + s["n_fail"]
        summ = f"{decided} programs with earnings data, {s['n_fail']} fall short"
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
    for st in sorted(states_present, key=lambda s: STATE_NAMES.get(s, s)):
        parts.append(
            f'      <a href="/colleges/{st.lower()}/">{esc(STATE_NAMES.get(st, st))}</a>\n'
        )
    parts.append("    </div>\n")
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def qualifying_schools(schools: dict) -> dict:
    """Schools that get a page: at least one earnings verdict (skip all-suppressed schools)."""
    return {u: s for u, s in schools.items() if (s["n_pass"] + s["n_fail"]) >= 1}


def build_slugs(qualified: dict) -> dict[str, str]:
    """Stable, unique college slugs: name; on collision add state, then unitid.

    Shared with build_lists so ranked-list rows link to URLs that actually exist.
    """
    slugs: dict[str, str] = {}
    used: set[str] = set()
    for u, s in sorted(qualified.items(), key=lambda kv: (kv[1]["name"] or "").lower()):
        base = slugify(s["name"])
        cand = base
        if cand in used:
            cand = f"{base}-{s['state'].lower()}"
        if cand in used:
            cand = f"{base}-{u}"
        used.add(cand)
        slugs[u] = cand
    return slugs


def main() -> None:
    con = duckdb.connect()
    schools, by_state, _ = build_model(con)

    qualified = qualifying_schools(schools)
    slugs = build_slugs(qualified)

    col_dir = SITE / "college"
    col_dir.mkdir(parents=True, exist_ok=True)
    states_present: dict[str, list] = defaultdict(list)
    for u, s in qualified.items():
        slug = slugs[u]
        programs = by_state.get(s["state"], {}).get(u, [])
        d = col_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(college_page(s, programs, slug))
        states_present[s["state"]].append((slug, s, u))

    colleges_dir = SITE / "colleges"
    colleges_dir.mkdir(parents=True, exist_ok=True)
    for st, lst in states_present.items():
        d = colleges_dir / st.lower()
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(state_index(st, lst))
    (colleges_dir / "index.html").write_text(
        national_index(states_present.keys(), profiled=len(qualified), searchable=len(schools))
    )

    print(f"college pages: {len(qualified):,}  |  state indexes: {len(states_present)}")
    print(f"wrote -> {col_dir} and {colleges_dir}")
    print("run pipeline.build_sitemap after the page builders to refresh sitemap.xml")


if __name__ == "__main__":
    main()
