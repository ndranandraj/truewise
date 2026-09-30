"""The college profile's page sections (design plan Prototype B, approved 27 September 2026).

Ported from design/prototypes/build_profile_proto.py for the profile release. canonical_page in
build_canonical_profiles.py assembles these around the program table:

  summary          the earnings verdict with its coverage in one box, then the average net price
                   for all families (which the calculator never changes)
  cost_section     band-labelled result, inputs as one group, assumptions, method expandable
  program_notes    the notes that change how the table reads, kept visible (R2)
  sources_section  sources and the three no-verdict states defined
  rail             "On this page" and "At a glance", shown from 1200px

The headline counts undergraduate programs, as the site's headline does. Three reasons a program
has no verdict are kept apart throughout: no state benchmark, earnings not published, nothing
reported.
"""

from __future__ import annotations

from pipeline.build_college_pages import esc, known_state, money, state_label

NP_LABELS = ["Under $30k", "$30k to $48k", "$48k to $75k", "$75k to $110k", "$110k and up"]


def _consts():
    from pipeline.build_canonical_profiles import REPORT_URL, SCORECARD_RELEASE

    return REPORT_URL, SCORECARD_RELEASE


def _island(obj) -> str:
    from pipeline.build_profile_pilot import _island_json

    return _island_json(obj)


def counts(rows: list[dict]) -> dict:
    c = dict.fromkeys(("pass", "fail", "nobench", "insufficient", "none"), 0)
    for r in rows:
        c[r["verdict"]] += 1
    c["decided"] = c["pass"] + c["fail"]
    c["total"] = len(rows)
    c["grad_decided"] = sum(1 for r in rows if r.get("grad") and r["verdict"] in ("pass", "fail"))
    c["one_year"] = sum(
        1
        for r in rows
        if r["verdict"] in ("pass", "fail") and r.get("horizon") == "1yr_after_completion"
    )
    return c


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def rest_line(c: dict, n_rest: int) -> str:
    """What the programs without a verdict are, in the three states kept apart."""
    parts = []
    if c["insufficient"]:
        parts.append((c["insufficient"], "no earnings published"))
    if c["nobench"]:
        parts.append((c["nobench"], "earnings but no state benchmark"))
    if c["none"]:
        parts.append((c["none"], "nothing reported"))
    if not parts:
        return ""
    if len(parts) == 1:
        verb = "has" if n_rest == 1 else "have"
        other = "The other one" if n_rest == 1 else f"The other {n_rest:,}"
        return f"{other} {verb} {parts[0][1]}."
    listed = [f"{n:,} with {what}" for n, what in parts]
    return f"The other {n_rest:,}: " + ", ".join(listed[:-1]) + " and " + listed[-1] + "."


def summary(meta: dict, rows: list[dict], bench, net_price) -> str:
    """The earnings verdict with its coverage in one box.

    The headline counts undergraduate programs, as the site's headline does: the federal
    earnings-premium test compares them with high-school graduates, so the figure means what it
    says. Graduate comparisons stay in the table, labelled. A school with verdicts only on
    graduate programs falls back to all programs, with that stated."""
    name = esc(meta["name"])
    st = esc(state_label(meta["state"])) if known_state(meta["state"]) else ""
    line = f"a typical {st} high-school graduate" if st else "a typical high-school graduate"
    bench_txt = f" (about {money(bench)} a year)" if bench is not None else ""
    all_c = counts(rows)
    ug = [r for r in rows if not r.get("grad")]
    ug_c = counts(ug)
    scoped = ug_c["decided"] > 0
    c = ug_c if scoped else all_c
    kind = "undergraduate programs" if scoped else "programs"
    total = c["total"]

    if c["decided"]:
        fig = (
            f'<div class="kf__figure"><span class="kf__num">{c["pass"]:,}</span>'
            f'<span class="kf__of">of {c["decided"]:,} assessed '
            f"{kind if c['decided'] != 1 else kind[:-1]}</span></div>"
        )
        verb = "has" if c["pass"] == 1 else "have"
        text = f"{verb} graduates earning more than {line}{bench_txt}."
        if c["fail"]:
            text += f" {c['fail']:,} fall{'s' if c['fail'] == 1 else ''} short."
        qual = [f"<b>{c['decided']:,} of {total:,} {kind} could be assessed.</b>"]
        rest = rest_line(c, total - c["decided"])
        if rest:
            qual.append(rest)
        if c["one_year"]:
            qual.append(
                f"{plural(c['one_year'], 'verdict')} use{'s' if c['one_year'] == 1 else ''} "
                "1-year earnings, an earlier career stage."
            )
        n_grad = all_c["total"] - ug_c["total"]
        if scoped and n_grad:
            qual.append(f"The {n_grad:,} graduate programs are in the table.")
        if not scoped and all_c["grad_decided"]:
            qual.append(
                "These are graduate programs, compared with the high-school line, which is not "
                "the federal test for them."
            )
    else:
        fig = '<p class="kf__none">No earnings verdict</p>'
        reported = total - c["none"]
        if c["nobench"]:
            why = (
                "ED&rsquo;s data gives none for this school"
                if meta.get("in_institution_file")
                else "ED&rsquo;s current institution file has no record of the school, often a sign "
                "it has closed or merged"
            )
            text = (
                f"ED publishes graduate earnings for {c['nobench']:,} of {name}&rsquo;s "
                f"{total:,} programs, but there is no state high-school benchmark to compare them "
                f"with: {why}."
            )
        elif reported:
            text = (
                f"ED reports {reported:,} of {name}&rsquo;s {total:,} programs, but publishes graduate "
                "earnings for none of them, so none can be compared with the high-school line."
            )
        else:
            text = (
                f"ED lists {total:,} programs for {name} but reports no graduate counts, earnings "
                "or debt for any of them."
            )
        qual = []
        if c["nobench"] or reported:
            qual.append(f"<b>0 of {total:,} programs could be assessed.</b>")
            qual.append(
                rest_line(c, total).replace(f"The other {total:,}", "Of all " + f"{total:,}", 1)
            )
        qual.append(
            "This describes what ED published, not how the school&rsquo;s programs perform."
        )

    if net_price and net_price.get("avg") is not None:
        cost = (
            '<p class="sum__cost"><span class="sum__costlab">Average net price, all families</span>'
            f'<span class="sum__costfig">{money(net_price["avg"])}</span> a year '
            '<a href="#cost">By family income</a></p>'
        )
    else:
        cost = (
            '<p class="sum__cost"><span class="sum__costlab">Average net price, all families</span>'
            '<span class="sum__na">not reported</span></p>'
        )
    return (
        '    <div class="kf sum" role="group" aria-labelledby="sum-label">\n'
        '      <p class="kf__label" id="sum-label">Graduate earnings</p>\n'
        f"      {fig}\n"
        f'      <p class="kf__text">{text}</p>\n'
        f'      <p class="kf__qual">{" ".join(qual)}</p>\n'
        "    </div>\n"
        f"    {cost}\n"
    )


def cost_section(meta: dict, rows: list[dict], net_price) -> str:
    _, release = _consts()
    if not net_price or (
        net_price.get("avg") is None
        and not any(b is not None for b in net_price.get("brackets") or [])
    ):
        return (
            '    <section id="cost" aria-labelledby="cost-h">\n'
            '      <h2 id="cost-h">What it would cost</h2>\n'
            '      <p class="cost__empty">ED reports no net price for this school, so there is no cost '
            "figure to show. Its own cost page, or its net price calculator, is the place to check.</p>\n"
            "    </section>\n"
        )
    brackets = list(net_price.get("brackets") or [None] * 5)
    avg = net_price.get("avg")
    ug = [r["credential"] for r in rows if not r.get("grad")]
    common = max(set(ug), key=ug.count) if ug else None
    years = {"Undergraduate Certificate or Diploma": 1, "Associate's Degree": 2}.get(common, 4)
    band_opts = "".join(
        f'<option value="{i}"{"" if b is not None else " disabled"}>'
        f"{lab if b is not None else lab + ' (not reported)'}</option>"
        for i, (lab, b) in enumerate(zip(NP_LABELS, brackets, strict=False))
    )
    avg_opt = (
        '<option value="-1" selected>All families (average)</option>' if avg is not None else ""
    )
    yr_opts = "".join(
        f'<option value="{y}"{" selected" if y == years else ""}>{y} year{"" if y == 1 else "s"}</option>'
        for y in (1, 2, 3, 4, 5, 6)
    )
    first = avg if avg is not None else next(b for b in brackets if b is not None)
    first_lab = (
        "Average for all families"
        if avg is not None
        else f"For families earning {NP_LABELS[brackets.index(first)].lower()}"
    )
    rows_html = "".join(
        f"<tr><td>{lab}</td><td class='num'>{money(b)}</td></tr>"
        for lab, b in zip(NP_LABELS, brackets, strict=False)
        if b is not None
    )
    if avg is not None:
        rows_html += f"<tr><td><b>All families (average)</b></td><td class='num'><b>{money(avg)}</b></td></tr>"
    neg = any(v is not None and v < 0 for v in brackets + [avg])
    neg_note = (
        '<p class="cost__assume">A negative net price means grant aid exceeded the published cost '
        "for that income band: a typical student received more than they paid. It is what ED "
        "reports, not an error.</p>"
        if neg
        else ""
    )
    data = {"brackets": brackets, "avg": avg, "labels": NP_LABELS}
    return f"""    <section id="cost" aria-labelledby="cost-h">
      <h2 id="cost-h">What it would cost</h2>
      <p>Net price is the yearly cost after grants and scholarships, as reported for students who
        received federal aid.</p>
      <div class="cost">
        <fieldset class="cost__inputs"><legend>Work out a total</legend>
          <div class="cost__field"><label for="c-inc">Family income</label><select id="c-inc">{avg_opt}{band_opts}</select></div>
          <div class="cost__field"><label for="c-yrs">Years of study</label><select id="c-yrs">{yr_opts}</select></div>
        </fieldset>
        <div class="cost__out" id="c-out" role="status" aria-live="polite">
          <p class="cost__band" id="c-band">{first_lab}</p>
          <p class="cost__fig"><span class="cost__num" id="c-per">{money(first)}</span> a year</p>
          <p class="cost__total" id="c-total">About {money(first * years)} over {years} year{"" if years == 1 else "s"}, if price and aid stay the same.</p>
        </div>
      </div>
      <p class="cost__assume">This multiplies the reported yearly net price by the years you choose. It
        is not a quote or a prediction: it leaves out interest, price rises and the chance of taking
        longer to finish.</p>
      {neg_note}
      <details class="more"><summary>Net price for every income band</summary>
        <div class="tscroll" tabindex="0" role="region" aria-label="Net price by family income"><table class="t"><thead><tr><th>Family income</th><th class="num">Net price per year</th></tr></thead><tbody>{rows_html}</tbody></table></div>
        <p class="chart-src">College Scorecard, release {release}. Bands with no figure were not reported by the school.</p>
      </details>
      <script type="application/json" id="c-data">{_island(data)}</script>
      <script>
      (function () {{
        var D = JSON.parse(document.getElementById("c-data").textContent);
        var inc = document.getElementById("c-inc"), yrs = document.getElementById("c-yrs");
        var money = function (n) {{ return (n < 0 ? "-$" : "$") + Math.abs(Math.round(n)).toLocaleString(); }};
        function render() {{
          var i = parseInt(inc.value, 10), y = parseInt(yrs.value, 10);
          var per = i < 0 ? D.avg : D.brackets[i];
          var band = i < 0 ? "Average for all families" : "For families earning " + D.labels[i].toLowerCase();
          document.getElementById("c-band").textContent = band;
          document.getElementById("c-per").textContent = money(per);
          document.getElementById("c-total").textContent = "About " + money(per * y) + " over " + y +
            (y === 1 ? " year" : " years") + ", if price and aid stay the same.";
        }}
        inc.addEventListener("change", render); yrs.addEventListener("change", render);
      }})();
      </script>
    </section>
"""


def program_notes(meta: dict, c: dict) -> str:
    """Notes that change how the table reads. Visible, never in an expandable section (R2)."""
    notes = []
    if c["one_year"]:
        notes.append(
            "Earnings are measured four years after graduating where ED publishes them. Where it "
            'does not, the one-year figure is shown and marked <span class="tw-oneyr">1-year '
            "earnings</span>. The two are different career stages and should not be compared as if "
            "measured at the same time."
        )
    if c["grad_decided"]:
        notes.append(
            "Graduate programs are compared with the same high-school line and marked <b>above</b> "
            "or <b>below HS line</b>. The federal rule compares them with bachelor&rsquo;s-degree "
            'holders instead; see <a href="/findings/stats-grad-exposure/">the graduate finding</a>.'
        )
    if meta.get("shared"):
        k = meta["shared"]
        notes.append(
            f"{plural(k, 'program')} {'is' if k == 1 else 'are'} reported by ED once for every campus "
            f"under one federal ID (OPEID {esc(meta.get('opeid6') or '')}), so the same earnings and "
            "debt appear on each of those campuses&rsquo; pages. Truewise&rsquo;s totals count such "
            "a program once."
        )
    return "".join(f'      <p class="note">{n}</p>\n' for n in notes)


def program_intro(bench, of_state: str) -> tuple[str, str]:
    """(introduction, caption). Without a benchmark nothing is compared, so neither may say
    "against a typical <state> high-school graduate" (review, 27 September)."""
    if bench is not None:
        return (
            f"Median earnings of each program&rsquo;s graduates against a typical {esc(of_state)}"
            f"high-school graduate ({money(bench)} a year).",
            f"Programs by earnings versus a typical {of_state}high-school graduate.",
        )
    return (
        "Median earnings of each program&rsquo;s graduates, where ED publishes them. There is "
        "no state high-school benchmark for this school, so no verdict is possible.",
        "Programs and their published earnings. No benchmark, so no verdicts.",
    )


def sources_section(meta: dict, bench) -> str:
    report_url, release = _consts()
    return f"""    <section id="sources" aria-labelledby="sources-h">
      <h2 id="sources-h">Sources and definitions</h2>
      <ul class="srcs">
        <li>U.S. Department of Education, College Scorecard, release {release}. Earnings are
          medians for graduates who received federal aid. Debt is federal loans only.</li>
        <li>{"The high-school line is ED&rsquo;s state benchmark, " + money(bench) + " a year." if bench is not None else "ED gives no state high-school benchmark for this school."}</li>
        <li><b>Earnings not published</b>: ED reports the program but no earnings figure, usually
          because too few graduates were measured. <b>Nothing reported</b>: ED lists the program with
          no figures at all. Neither is a judgement of the program.</li>
        <li><b>Debt as years of gain</b> is median federal debt divided by how much more graduates
          earn per year than a typical high-school graduate. It is not a repayment time.</li>
      </ul>
      <p class="src-links"><a href="/compare/">Compare with another college</a> &middot; <a href="{report_url}">Report an error</a> &middot; <a href="/methodology/">Methodology</a></p>
    </section>
"""


NAV = [("cost", "Cost"), ("programs", "Programs"), ("sources", "Sources")]


def rail(meta: dict, c: dict, net_price) -> str:
    where = ", ".join(p for p in (meta.get("city"), state_label(meta["state"])) if p)
    facts = [("Location", where)]
    if meta.get("control"):
        facts.append(("Type", meta["control"]))
    facts.append(("All programs with a verdict", f"{c['decided']:,} of {c['total']:,}"))
    avg = (net_price or {}).get("avg")
    facts.append(
        (
            "Average net price, all families",
            f"{money(avg)} a year" if avg is not None else "not reported",
        )
    )
    facts.append(("Data", f"College Scorecard, {_consts()[1]}"))
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in facts)
    links = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in NAV)
    return (
        f'    <aside class="rail" aria-label="{esc(meta["name"])} at a glance"><div class="rail__inner">'
        f"<h2>On this page</h2><ul>{links}</ul>"
        f'<h2 class="rail__h2">At a glance</h2><dl>{dl}</dl></div></aside>\n'
    )
