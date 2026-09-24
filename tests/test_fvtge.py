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
    assert f"{s['none_filed']:,}</b> had submitted no file at all" in text
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_search_finds_a_college_and_links_its_profile(built, tmp_path):
    _, _, out = built
    root = bf.ROOT
    if not (root / "node_modules" / "jsdom").exists():
        pytest.skip("jsdom not installed")
    script = tmp_path / "search.js"
    script.write_text(
        """
const fs = require("fs");
const { JSDOM } = require(process.argv[2] + "/node_modules/jsdom");
const html = fs.readFileSync(process.argv[3], "utf8");
const data = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const dom = new JSDOM(html.replace(/<script[^>]*src=[^>]*><\\/script>/g, ""),
  { runScripts: "dangerously", url: "https://truewise.dev/findings/fvtge-reporting/",
    beforeParse(w) { w.fetch = async () => ({ ok: true, json: async () => data }); } });
const d = dom.window.document;
setTimeout(() => {
  const q = d.getElementById("fv-q");
  q.value = "palomar";
  q.dispatchEvent(new dom.window.Event("input"));
  setTimeout(() => {
    const row = d.querySelector("#fv-rows tr");
    console.log(JSON.stringify({ rows: d.querySelectorAll("#fv-rows tr").length,
      text: row ? row.textContent : "", link: row && row.querySelector("a") ? row.querySelector("a").getAttribute("href") : null,
      status: d.getElementById("fv-status").textContent }));
  }, 400);
}, 50);
"""
    )
    res = subprocess.run(
        ["node", str(script), str(root), str(out / "index.html"), str(out / "institutions.json")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout.strip().splitlines()[-1])
    assert got["rows"] >= 1, got
    assert "Palomar" in got["text"] and "of 7" in got["text"], got
    assert got["link"] and got["link"].startswith("/college/"), got
