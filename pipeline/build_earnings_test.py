"""Build /earnings-test/: the federal earnings test for college programs, in plain words.

Truewise measures the comparison the federal rule makes for undergraduate programs, and until this
page the site never named the rule. "Do No Harm", "earnings test" and "lose federal loans" are how
readers and the 2026 coverage refer to it. This page says what the rule is, when it applies, which
programs are held out at first, and how Truewise's own comparison differs from the Department of
Education's test. Prototype K, approved 14 November 2026.

Three rules the page keeps:

* Truewise's comparison is never presented as ED's result. No program has been tested yet, and the
  key box says so, not an expandable section.
* Every Truewise figure comes from site/data/value_check_summary.json (analysis.summary), with its
  denominator and its earnings horizon beside it. Nothing is typed in by hand.
* Statements about the rule were read in the rule itself (91 FR 40136, published 1 July 2026) on
  14 November 2026: the DATES section and executive summary, the regulatory text of sections 668.2,
  668.14(h), 668.16(t), 668.402(c)(3), 668.403, 668.603 and 668.605, and the impact analysis (first
  sanctions in "the award year starting with July 2028"; twenty program codes qualify for the
  tipped-occupation delay; about 93% of cosmetology certificate programs likely to fail; roughly
  61,900 programs subject to the framework and approximately 5 percent estimated to fail). The name
  "Do No Harm" is not in the rule: it is the common name (NPR, 30 June 2026). The figure of about
  3,302 failing programs that the graduate finding carries was not found in the rule's text, where
  its tables are images, so this page states the share the text gives instead.

Run after analysis.summary:
    python -m pipeline.build_earnings_test
"""

from __future__ import annotations

import json

from pipeline.build_college_pages import BASE, BEACON, FOOTER, head
from pipeline.build_package_data import SCORECARD_RELEASE
from pipeline.config import ROOT
from pipeline.og_images import card as render_card

SITE = ROOT / "site"
SLUG = "earnings-test"
SUMMARY = SITE / "data" / "value_check_summary.json"

# Set on the day the page is released. Until then the dateline carries only the date the rule was
# last read, because a publication date that has not happened is not a known value.
PUBLISHED_ON = ""
FACTS_CHECKED = "14 Nov 2026"

FR_URL = (
    "https://www.federalregister.gov/documents/2026/07/01/2026-13286/"
    "accountability-in-higher-education-and-access-through-demand--driven-workforce-pell-student-tuition"
)
NAV_ITEMS = [
    ("test", "The test"),
    ("fails", "If a program fails"),
    ("dates", "Dates"),
    ("held", "Held out at first"),
    ("truewise", "What Truewise shows"),
    ("questions", "Questions"),
    ("sources", "Sources"),
]
TITLE = "The Do No Harm earnings test: which programs could lose federal loans"
DESC = (
    "From July 2027 a college program whose graduates earn less than a federal line in two of "
    "three years loses federal loans. The rule in plain words."
)


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}"


def render_page(s: dict) -> str:
    """The page, from the Value Check summary. Raises KeyError if a figure it states is missing."""
    total = s["programs_total"]
    decided = s["programs_decided"]
    fails = s["programs_fail_earnings_premium"]
    four = s["four_year_only"]
    cos = s["cosmetology_1204"]

    canonical = f"{BASE}/{SLUG}/"
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Truewise","item":"{BASE}/"}},
    {{"@type":"ListItem","position":2,"name":"The federal earnings test","item":"{canonical}"}}
  ]}}
  </script>
"""
    page_head = head(TITLE, DESC, canonical, ld, og_image=f"/og/{SLUG}.png").replace(
        "</head>", '  <link rel="stylesheet" href="/article.css" />\n</head>', 1
    )
    chips = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in NAV_ITEMS)
    published = f"<span>Published {PUBLISHED_ON}</span>" if PUBLISHED_ON else ""

    body = f"""  <main class="wrap art has-rail et">
    <aside class="rail" aria-label="On this page"><div class="rail__inner"><h2>On this page</h2><ul>{chips}</ul></div></aside>
    <nav class="crumbs"><a href="/">Truewise</a> &rsaquo; The federal earnings test</nav>
    <p class="et-eyebrow">Also called the &ldquo;Do No Harm&rdquo; test</p>
    <h1>The federal earnings test for college programs, explained</h1>
    <p class="dateline">{published}<span>Rule last read {FACTS_CHECKED}</span></p>

    <div class="kf" role="group" aria-labelledby="kf-label">
      <p class="kf__label" id="kf-label">In short</p>
      <p class="kf__lead">A college program loses federal student loans if its graduates&rsquo; typical
        earnings fall below a federal comparison line in two of any three years in a row.</p>
      <p class="kf__qual"><b>No program has been tested yet.</b> The rule takes effect on 1 July 2027.
        The Department of Education (ED) expects to calculate the first results in 2027, and the
        earliest a program could lose loans is the award year that starts in July 2028.</p>
      <p class="kf__more"><span>Law: Working Families Tax Cuts Act, section 84001</span>
        <span>Rule: 91 FR 40136, 1 July 2026</span></p>
    </div>

    <nav class="sectnav" aria-label="Sections">
      <p class="sectnav__label" id="sn-l">{len(NAV_ITEMS)} sections</p>
      <div class="sectnav__scroll"><ul aria-labelledby="sn-l">{chips}</ul></div>
    </nav>

    <section id="test" class="why" aria-labelledby="test-h">
      <h2 id="test-h">The test</h2>
      <p>It asks one question of each program: do its graduates typically earn more than people who
        stopped one step earlier?</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="What is compared with what"><table class="t"><thead><tr><th>Program</th><th>Graduates&rsquo; earnings</th><th>Compared with</th></tr></thead><tbody>
        <tr><td>Undergraduate certificate, associate&rsquo;s or bachelor&rsquo;s</td><td>The median in the fourth tax year after finishing</td><td>Working adults aged 25 to 34 whose highest credential is a high-school diploma</td></tr>
        <tr><td>Master&rsquo;s, doctoral or professional</td><td>The same</td><td>Working adults aged 25 to 34 whose highest credential is a bachelor&rsquo;s degree</td></tr>
      </tbody></table></div>
      <p>A program fails when its graduates&rsquo; median is below the line. The line is the one for
        the college&rsquo;s state. When fewer than half of the college&rsquo;s students come from that
        state, the national figure is used.</p>
      <details class="more"><summary>Details that change the result</summary><ul>
        <li><b>A median is the middle graduate.</b> A program can fail while many of its graduates earn
          more than the line, and pass while many earn less.</li>
        <li><b>Whose earnings.</b> Graduates who were working that year. Some are left out, among them
          people enrolled in another program and people who went on to a higher credential.</li>
        <li><b>Graduate programs get the lowest of several lines:</b> bachelor&rsquo;s holders in the
          state, in the same field, and nationally. Where ED does not have the Census figures it
          needs, the line is set at $1, which no program falls below.</li>
        <li><b>Small programs.</b> With fewer than 30 graduates in a year, ED adds earlier years, then
          every program in the same field and at the same level, until it reaches 30. A program still
          short of 30 gets no result.</li>
      </ul></details>
    </section>

    <section id="fails" aria-labelledby="fails-h">
      <h2 id="fails-h">If a program fails</h2>
      <ol class="et-steps">
        <li><b>A failing year brings a warning.</b> The college must tell current students within 30
          days of ED&rsquo;s notice. Someone thinking of enrolling must be shown the warning and
          acknowledge it before they can enroll.</li>
        <li><b>Two failing years in any three in a row end federal loans for that program.</b> ED names
          it a &ldquo;low-earning outcome program&rdquo;, and its students cannot take out federal Direct
          Loans for at least two years.</li>
        <li><b>A college can appeal within 30 days,</b> on the grounds that ED made an error in its
          calculation.</li>
      </ol>
      <p>The test itself ends Direct Loans for a program, not Pell Grants. A separate requirement
        applies to a college as a whole when more than half of its aided students, or more than half
        of its federal aid dollars, are in low-earning programs.</p>
    </section>

    <section id="dates" aria-labelledby="dates-h">
      <h2 id="dates-h">Dates</h2>
      <ul class="et-timeline">
        <li><b class="et-when">4 July 2025</b><span>The Working Families Tax Cuts Act becomes law (Public Law 119-21). Section 84001 sets the earnings test.</span></li>
        <li><b class="et-when">20 April 2026</b><span>ED publishes its proposed rule.</span></li>
        <li><b class="et-when">1 July 2026</b><span>ED publishes the final rule.</span></li>
        <li><b class="et-when">1 October 2026</b><span>Colleges&rsquo; reporting deadline for 2026. <a href="/findings/fvtge-reporting/">Which colleges had not filed earlier files</a>.</span></li>
        <li><b class="et-when">2027</b><span>First results expected.</span></li>
        <li><b class="et-when">1 July 2027</b><span>The rule takes effect.</span></li>
        <li><b class="et-when">From July 2028</b><span>The earliest award year in which a program could lose Direct Loans, after failing twice.</span></li>
      </ul>
    </section>

    <section id="held" aria-labelledby="held-h">
      <h2 id="held-h">Held out at first: programs for tipped jobs</h2>
      <p>Programs that prepare students for jobs where at least half of workers receive tips are not
        passed or failed in the first rounds: not in any year for which ED is looking at earnings from
        tax year 2025 or earlier. The jobs are those on the Treasury&rsquo;s list for the tax deduction
        on tips.</p>
      <p>The rule counts twenty program codes that qualify. The American Association of
        Cosmetology Schools says they include cosmetology, barbering and massage therapy.</p>
      <p class="caveat">This bears on one of Truewise&rsquo;s own figures. On published Scorecard
        earnings, {cos["fails"]:,} of {cos["decided"]:,} undergraduate cosmetology programs with published
        earnings ({100 * cos["fail_rate"]:.0f}%) fall below the high-school line. Under the final rule
        those programs are not failed in the first rounds.</p>
      <p>ED&rsquo;s own analysis in the rule says about 93% of cosmetology certificate programs are
        likely to fail the test. It uses different data from Truewise&rsquo;s figure, so the two are
        not the same measurement.</p>
    </section>

    <section id="truewise" aria-labelledby="truewise-h">
      <h2 id="truewise-h">What Truewise shows, and what it does not</h2>
      <p>Truewise makes the undergraduate comparison today, from earnings ED has already published in
        the College Scorecard. It is our calculation. It is not ED&rsquo;s result, and it does not say
        which programs will pass or fail.</p>
      <p>Of {total:,} undergraduate programs, {decided:,} can be compared. In {fails:,} of those
        ({_pct(fails, decided)}%) graduates earn less than a typical high-school graduate in their state.
        Earnings are four years after finishing where ED publishes them and one year otherwise; on
        four-year figures alone it is {four["fails"]:,} of {four["decided"]:,}
        ({100 * four["fail_rate"]:.1f}%). For most of the other {total - decided:,} programs ED
        publishes no earnings.</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="The federal test and Truewise compared"><table class="t"><thead><tr><th></th><th>The federal test</th><th>Truewise today</th></tr></thead><tbody>
        <tr><td><b>Earnings</b></td><td>Fourth tax year after finishing, for the group ED tests</td><td>College Scorecard, release {SCORECARD_RELEASE}: four years after finishing where published, otherwise one year, marked</td></tr>
        <tr><td><b>Line</b></td><td>ED&rsquo;s line for the test year, state or national</td><td>The state high-school line in the Scorecard file</td></tr>
        <tr><td><b>Graduate programs</b></td><td>A bachelor&rsquo;s line, the lowest of several</td><td>Shown against the high-school line and labelled</td></tr>
        <tr><td><b>Small programs</b></td><td>Combined with earlier years and similar programs</td><td>Shown as &ldquo;not published&rdquo;</td></tr>
        <tr><td><b>Programs for tipped jobs</b></td><td>Not passed or failed at first</td><td>Compared like any other program</td></tr>
        <tr><td><b>Result</b></td><td>Pass or fail each year; loans end after two fails in three years</td><td>One comparison on one data release; no official status</td></tr>
      </tbody></table></div>
      <p>ED&rsquo;s own analysis in the final rule covers roughly 61,900 programs, undergraduate and
        graduate together, and estimates that about 5% of them would fail. That figure and
        Truewise&rsquo;s use different data and different rules, so the two are not comparable.</p>
      <p class="et-next"><a class="btn" href="/value-check/">Look up a college</a>
        <a class="btn btn--secondary" href="/findings/stats-grad-exposure/">Graduate programs under the rule</a>
        <a class="btn btn--secondary" href="/methodology/">How Truewise counts</a></p>
    </section>

    <section id="questions" class="et-q" aria-labelledby="questions-h">
      <h2 id="questions-h">Questions</h2>
      <h3>Is there an official list of failing programs?</h3>
      <p>Not yet. ED has not published results under this rule. Any list available now, Truewise&rsquo;s
        comparison included, is someone&rsquo;s calculation on earlier data.</p>
      <h3>Does failing mean every graduate earns less than a high-school graduate?</h3>
      <p>No. The test compares two medians. It says the middle graduate of the program earned less than
        the middle person in the comparison group, and nothing about any one graduate.</p>
      <h3>If my program fails, do my loans stop straight away?</h3>
      <p>Not after one failing year, which brings a warning. Loans end for a program after two failing
        years in three. The rule also lets ED allow a program to keep lending while it closes, for no
        longer than three years or the program&rsquo;s normal length, whichever is shorter. A
        college&rsquo;s financial aid office can say what applies to a particular student.</p>
      <h3>Does it cover Pell Grants or private loans?</h3>
      <p>The test is about federal Direct Loans. Private loans are outside it.</p>
      <h3>Why &ldquo;Do No Harm&rdquo;?</h3>
      <p>It is the common name, not the rule&rsquo;s title. The idea is that a program should leave its
        graduates no worse off than people without the credential. The rule calls the measure the
        earnings premium.</p>
    </section>

    <section id="sources" aria-labelledby="sources-h">
      <h2 id="sources-h">Sources</h2>
      <ul class="srcs">
        <li>The rule: <a href="{FR_URL}">Federal Register, 1 July 2026, 91 FR 40136</a>, &ldquo;Student
          Tuition and Transparency System (STATS) and Earnings Accountability&rdquo;, sections 668.2,
          668.402, 668.403, 668.603 and 668.605</li>
        <li>The law: Working Families Tax Cuts Act, Public Law 119-21, section 84001</li>
        <li>Truewise&rsquo;s figures: College Scorecard, release {SCORECARD_RELEASE};
          <a href="/methodology/">methodology</a></li>
        <li>Not affiliated with the U.S. Department of Education. This page describes a federal rule
          and is not legal or financial advice.</li>
      </ul>
    </section>
  </main>
"""
    return page_head + body + FOOTER + BEACON + "</body>\n</html>\n"


def main() -> None:
    if not SUMMARY.exists():
        raise SystemExit(f"{SUMMARY} is missing: run analysis.summary first.")
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    render_card(
        SITE / "og" / f"{SLUG}.png",
        "Explainer · federal earnings test",
        "Which college programs could lose federal loans?",
        big=None,
        sub="No program has been tested yet. The rule takes effect on 1 July 2027.",
    )
    out = SITE / SLUG
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_page(s), encoding="utf-8")
    print(f"earnings test explainer -> {out / 'index.html'}")


if __name__ == "__main__":
    main()
