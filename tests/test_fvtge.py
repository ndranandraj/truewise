"""The FVT/GE reporting-status finding: what it may claim, and that the page works.

Built from the committed sources in published/, into a temporary directory, so it runs in CI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from pipeline import build_fvtge as bf


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("fvtge")
    site = out / "site"
    orig_out, orig_site = bf.OUT_DIR, bf.SITE
    bf.OUT_DIR, bf.SITE = site / "findings" / bf.SLUG, site
    try:
        con = bf._con()
        s = bf.compute(con)
        inst = bf.institutions(con)
        bf.write_outputs(s, inst)
    finally:
        bf.OUT_DIR, bf.SITE = orig_out, orig_site
    return s, inst, site / "findings" / bf.SLUG


def test_counts_restate_eds_list_exactly(built):
    s, inst, _ = built
    # ED's own Frequencies sheet: 41.68% have missing files, 12.47% miss all seven, of 4,635.
    assert s["total"] == 4635 and len(inst) == 4635
    assert round(100 * s["missing"] / s["total"], 2) == 41.68
    assert round(100 * s["all7"] / s["total"], 2) == 12.47
    assert s["compiled"] == "2026-08-06"
    # 578 have all seven Not Submitted; 722 have no component Submitted at all (the other 144 have some
    # components Not Required). The page once called the 578 "submitted none", which undercounted.
    assert s["none_filed"] == 722 and s["all7"] == 578


def test_the_page_names_both_counts_correctly(built):
    s, _, out = built
    text = re.sub(r"\s+", " ", (out / "index.html").read_text())
    assert f"{s['none_filed']:,}</b> submitted no file at all" in text
    assert f"{s['all7']:,}</b> of those had all seven marked not submitted" in text
    assert "had submitted none" not in text and "None submitted" not in text


def test_the_page_carries_eds_caveats_and_the_date(built):
    _, _, out = built
    html = (out / "index.html").read_text()
    text = re.sub(r"\s+", " ", html)
    assert bf.ED_COMPLETENESS.replace("’", "&#x27;") in text or bf.ED_COMPLETENESS in text
    assert "6 August 2026" in text, "every claim is as of ED's compile date"
    assert "15 January 2027" in text and "1 October 2026" in text
    assert "This is an association, not an explanation." in text
    for word in ("delinquent", "non-compliant", "noncompliant", "hiding", "concealing"):
        assert word not in text.lower(), f"the page must not characterise colleges as {word}"
    assert "—" not in html


def test_the_association_is_standardised_and_every_cell_reported(built):
    s, _, _ = built
    a = s["assoc"]
    raw_missing = a["fail_missing"] / a["n_missing"]
    raw_complete = a["fail_complete"] / a["n_complete"]
    # The adjusted expectation must sit between the two raw rates, or the adjustment is wrong.
    assert raw_complete < a["expected_missing"] < raw_missing
    assert a["unstandardised"] == 0, "every missing-filer program must fall in a comparable cell"
    assert len(s["cells"]) == 9


def test_the_homepage_line_matches_eds_list(built):
    s, _, _ = built
    home = (bf.ROOT / "site" / "index.html").read_text()
    line = re.search(r'<p class="hero-latest">(.*?)</p>', home, re.S)
    assert line, "the homepage should point to the FVT/GE finding"
    text = line.group(1)
    assert f"{s['missing']:,} of {s['total']:,}" in text
    assert "6 August 2026" in text and 'href="/findings/fvtge-reporting/"' in text


def test_downloads_cover_every_college_on_the_list(built):
    s, _, out = built
    rows = json.loads((out / "institutions.json").read_text())
    assert len(rows) == s["total"]
    csv_lines = (out / f"fvtge-reporting-{s['compiled']}.csv").read_text().strip().splitlines()
    assert len(csv_lines) == s["total"] + 1
    assert csv_lines[0].endswith("status_as_of")


def _jsdom(out, tmp_path, steps, fail_first=False):
    """Run the lookup script in jsdom with institutions.json served by a stubbed fetch."""
    root = bf.ROOT
    if shutil.which("node") is None or not (root / "node_modules" / "jsdom").exists():
        pytest.skip("node or jsdom not installed")
    script = tmp_path / "lookup.js"
    script.write_text(
        """
const fs = require("fs");
const { JSDOM } = require(process.argv[2] + "/node_modules/jsdom");
const html = fs.readFileSync(process.argv[3], "utf8");
const data = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
let calls = 0; const failFirst = process.argv[5] === "1";
const dom = new JSDOM(html.replace(/<script[^>]*src=[^>]*><\\/script>/g, ""),
  { runScripts: "dangerously", url: "https://truewise.dev/findings/fvtge-reporting/",
    beforeParse(w) { w.fetch = async () => { calls++;
      if (failFirst && calls === 1) return { ok: false, status: 503, json: async () => null };
      return { ok: true, json: async () => data }; }; } });
const w = dom.window, d = w.document, q = d.getElementById("lk-q");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const snap = () => ({ status: d.getElementById("lk-status").textContent,
  rows: d.querySelectorAll("#lk-rows li").length,
  first: d.querySelector("#lk-rows li") ? d.querySelector("#lk-rows li").textContent : "",
  link: d.querySelector("#lk-rows li a") ? d.querySelector("#lk-rows li a").getAttribute("href") : null,
  focus: d.activeElement ? d.activeElement.id : null, calls });
const type = (v) => { q.value = v; q.dispatchEvent(new w.Event("input")); };
(async () => {
  const out = { before: snap() };
  q.focus(); q.dispatchEvent(new w.Event("focus")); await wait(50);
  out.afterFocus = snap();
  if (failFirst) { d.getElementById("lk-retry").focus(); d.getElementById("lk-retry").click(); await wait(50);
    out.afterRetry = snap(); }
  type("palomar"); await wait(20); out.palomar = snap();
  type("zzqx"); await wait(20); out.none = snap();
  console.log(JSON.stringify(out));
})();
"""
    )
    res = subprocess.run(
        [
            "node",
            str(script),
            str(root),
            str(out / "index.html"),
            str(out / "institutions.json"),
            "1" if fail_first else "0",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_the_lookup_finds_a_college_and_says_what_truewise_assesses(built, tmp_path):
    _, _, out = built
    got = _jsdom(out, tmp_path, None)
    assert got["before"]["calls"] == 0, "the list loads on first use, not with the page"
    assert got["palomar"]["rows"] >= 1 and "Palomar" in got["palomar"]["first"], got
    assert "of 7" in got["palomar"]["first"], got
    assert "Truewise earnings verdicts:" in got["palomar"]["first"], got
    assert got["palomar"]["link"] and got["palomar"]["link"].startswith("/college/"), got


def test_no_result_is_announced_in_the_status_region(built, tmp_path):
    _, _, out = built
    got = _jsdom(out, tmp_path, None)
    assert got["none"]["rows"] == 0
    assert "No college on ED" in got["none"]["status"] and "zzqx" in got["none"]["status"], got


def test_a_failed_load_offers_retry_and_returns_focus_to_the_search(built, tmp_path):
    _, _, out = built
    got = _jsdom(out, tmp_path, None, fail_first=True)
    assert "did not load" in got["afterFocus"]["status"], got
    assert got["afterRetry"]["focus"] == "lk-q", got
    assert got["palomar"]["rows"] >= 1, got


def test_the_key_finding_keeps_its_qualifier_beside_the_figure(built):
    """R1: the qualifier that changes the figure's meaning is inside the key-finding box."""
    s, _, out = built
    html = (out / "index.html").read_text()
    box = html[html.index('<div class="kf"') : html.index('<nav class="sectnav"')]
    text = re.sub(r"\s+", " ", box)
    assert f'<span class="kf__num">{s["missing"]:,}</span>' in text
    assert f"of {s['total']:,} colleges" in text and "6 August 2026" in text
    assert "does not mean &ldquo;complete&rdquo;" in text
    assert "Files rejected with errors count as not submitted." in text
    assert "Filings after 6 August are not reflected." in text
    # Read as "received files count as not submitted" in review; this wording must not come back.
    assert "counts any file received" not in text


def test_locations_are_named_and_foreign_is_not_a_sector(built):
    s, _, out = built
    html = (out / "index.html").read_text()
    sector = html[html.index('id="sector"') : html.index('id="files"')]
    assert "Foreign" not in sector[: sector.index("</ul>")], (
        "the chart shows the three sectors only"
    )
    assert "ED lists foreign institutions separately" in sector
    places = html[html.index('id="places"') : html.index('id="earnings"')]
    assert "eight states and territories" in places
    assert f"All {len(s['states'])} locations in ED&rsquo;s list" in places
    for code in ("PR", "MH", "FM", "PW", "FC"):
        assert f"<td>{code}</td>" not in places, f"{code} must be shown by name"
    assert "Marshall Islands" in places and "Puerto Rico" in places


def test_only_finding_pages_load_the_article_sheet(built):
    _, _, out = built
    assert 'href="/article.css"' in (out / "index.html").read_text()
    for page in ("index.html", "methodology/index.html", "value-check/index.html"):
        assert "article.css" not in (bf.ROOT / "site" / page).read_text(), page
    from pipeline import version_assets

    assert "article.css" in version_assets.SHEETS
    assert "/article.css\n  Cache-Control" in (bf.ROOT / "site" / "_headers").read_text()
