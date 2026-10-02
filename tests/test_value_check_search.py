"""The Value Check search view (Stage 3, Prototype D approved 2 October 2026).

Run against the real page and the real school index, built here from the committed parquet, so it
runs in CI where the built site/ data does not exist.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import duckdb
import pytest

from pipeline.config import ROOT

PAGE = ROOT / "site" / "value-check" / "index.html"


@pytest.fixture(scope="module")
def run_page(tmp_path_factory):
    if shutil.which("node") is None or not (ROOT / "node_modules" / "jsdom").exists():
        pytest.skip("node or jsdom not installed")
    from pipeline import build_site as bs

    schools, _, benchmarks = bs.build_model(duckdb.connect())
    tmp = tmp_path_factory.mktemp("vc")
    data = tmp / "schools.json"
    data.write_text(
        json.dumps({"generated": True, "benchmarks": benchmarks, "schools": list(schools.values())})
    )
    script = tmp / "run.js"
    script.write_text(
        """
const fs = require("fs");
const [root, page, data] = process.argv.slice(2);
const { JSDOM } = require(root + "/node_modules/jsdom");
const search = fs.readFileSync(root + "/site/assets/college-search.js", "utf8");
const html = fs.readFileSync(page, "utf8")
  .replace('<script src="/assets/college-search.js"></script>', "<script>" + search + "</script>")
  .replace(/<script[^>]*src=[^>]*><\\/script>/g, "");
const index = JSON.parse(fs.readFileSync(data, "utf8"));
const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://truewise.dev/value-check/",
  beforeParse(w) { w.fetch = async (u) => ({ ok: true, json: async () => (u.includes("schools") ? index : {}) });
    w.scrollTo = () => {}; w.HTMLElement.prototype.scrollIntoView = () => {}; } });
const w = dom.window, d = w.document, wait = (ms) => new Promise((r) => setTimeout(r, ms));
const type = async (v) => { const q = d.getElementById("q"); q.value = v; q.dispatchEvent(new w.Event("input")); await wait(150); };
const card = (name) => { const h = [...d.querySelectorAll("#results h3")].find((x) => x.textContent === name);
  return h ? h.closest("a").querySelector(".mini").textContent.replace(/\\s+/g, " ").trim() : null; };
(async () => {
  await wait(400);
  const out = {
    h1: d.querySelector("h1").textContent, placeholder: d.getElementById("q").placeholder,
    examples: [...d.querySelectorAll(".chip")].map((a) => a.textContent),
    note: (d.querySelector(".examples-note") || {}).textContent,
    locations: [...d.querySelectorAll("#state-sel option")].map((o) => o.textContent),
    required: d.getElementById("state-sel").required, grid: !!d.querySelector(".state-grid"),
  };
  await type("zzqxv");
  const rc = d.getElementById("rescount");
  out.nomatch = { status: rc.textContent, shown: rc.style.display !== "none", live: rc.getAttribute("aria-live"),
    options: d.querySelectorAll("#results li").length, help: d.getElementById("noresults").textContent };
  await type("baylor university"); out.baylor = card("Baylor University");
  await type("albizu university miami"); out.albizu = card("Albizu University-Miami");
  await type("university of california san francisco"); out.ucsf = card("University of California-San Francisco");
  console.log(JSON.stringify(out));
})();
"""
    )
    res = subprocess.run(
        ["node", str(script), str(ROOT), str(PAGE), str(data)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1]), schools


def test_the_search_comes_first_with_a_short_introduction(run_page):
    got, _ = run_page
    assert got["h1"] == "Look up a college"
    assert got["placeholder"] == "e.g. Baylor", "the long loaded placeholder was cut off at 320px"


def test_starting_points_are_labelled_examples(run_page):
    got, _ = run_page
    assert got["examples"] == [
        "Baylor University",
        "University of California-Los Angeles",
        "Ivy Tech Community College",
        "Western Governors University",
        "Howard University",
        "University of Puerto Rico-Mayaguez",
    ]
    assert got["note"] == "Examples, not recommendations."


def test_browse_by_location_lists_every_location_with_no_default_choice(run_page):
    got, _ = run_page
    locs = got["locations"]
    assert locs[0] == "Choose a location" and got["required"] and not got["grid"]
    for place in ("Puerto Rico", "Guam", "Palau", "Marshall Islands", "Micronesia"):
        assert place in locs
    assert locs[-1] == "Location not reported" and len(locs) == 61


def test_a_search_with_no_match_is_announced(run_page):
    got, _ = run_page
    nm = got["nomatch"]
    assert nm["status"] == "No colleges match “zzqxv”." and nm["shown"] and nm["live"] == "polite"
    assert nm["options"] == 0, "the message must not sit inside the results listbox"
    assert "No colleges match" not in nm["help"], "the sentence is not shown twice"


def test_cards_count_what_the_profile_counts(run_page):
    """Baylor's profile leads with 49 of 51 assessed undergraduate programs; its card used to read
    62 pass and 2 fall short across all 183. Every card's undergraduate counts must equal the
    profile's, school by school."""
    got, schools = run_page
    assert got["baylor"] == "Undergraduate programs: 49 clear the bar 2 fall short 32 no verdict"
    # Undergraduate programs, none with a verdict: said, never filled with graduate results.
    assert got["albizu"] == "Undergraduate programs: none of the 6 has a verdict"
    # Graduate-only: labelled as such.
    assert got["ucsf"].startswith(
        "Graduate programs only: 14 above the high-school line 1 below it"
    )

    from pipeline.build_profile_pilot import all_profiles
    from pipeline.profile_layout import counts

    profiles = all_profiles(duckdb.connect())
    for u, s in schools.items():
        ug = [r for r in profiles.get(u, ({}, []))[1] if not r.get("grad")]
        c = counts(ug)
        assert (s["n_ug_pass"], s["n_ug_fail"], s["n_ug_programs"]) == (
            c["pass"],
            c["fail"],
            c["total"],
        ), u
