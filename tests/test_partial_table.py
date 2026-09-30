"""A profile whose table is partial without JavaScript says so, and offers the complete list.

245 profiles ship 150 program rows as HTML and load the rest with JavaScript. Until 29 September
2026 nothing said so: Penn State's page read "184 of 489 programs could be assessed" above 150 rows.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess

import duckdb
import pytest

from pipeline.build_canonical_profiles import PROGRAMS_CSV, canonical_page, programs_csv
from pipeline.build_profile_pilot import all_profiles
from pipeline.config import ROOT

PARQUET = ROOT / "published" / "value_check.parquet"


@pytest.fixture(scope="module")
def profiles():
    return all_profiles(duckdb.connect(), PARQUET)


@pytest.fixture(scope="module")
def partial(profiles):
    return {u: rows for u, (_, rows) in profiles.items() if len(rows) > 150}


def _page(rows):
    meta = {"unitid": "1", "name": "Big State University", "state": "PA", "control": "Public"}
    return canonical_page(meta, rows, "big-state", 36498.0, 150)


def test_the_partial_notice_is_above_the_table_in_the_initial_html(profiles):
    _, rows = profiles["214777"]
    html, tail = _page(rows)
    assert tail
    static = html[html.index('class="tw-profile-static"') :]
    notice = static.index("data-tw-partial")
    assert notice < static.index("<table"), "the notice is read before the rows"
    assert (
        f"Summary figures cover all {len(rows)} programs. This table shows the first 150." in static
    )
    assert f'href="{PROGRAMS_CSV}" download>Download all {len(rows)} programs (CSV)' in static
    # The complete list stays linked after the table enhances, outside the replaced mount.
    after = html[html.index("</table>") :]
    assert after.count(PROGRAMS_CSV) == 1 and "</main>" in after


def test_a_complete_table_carries_no_notice(profiles):
    _, rows = profiles["223232"]
    html, tail = _page(rows[:150])
    assert tail is None and "data-tw-partial" not in html and PROGRAMS_CSV not in html


def test_every_csv_matches_the_complete_dataset(partial):
    con = duckdb.connect()
    out = programs_csv(con, PARQUET, partial)
    assert set(out) == set(partial) and len(out) == 245
    truth = {}
    for u, cip, lvl, e, c, d, flag in con.sql(
        f"SELECT unitid, cip_code, credential_level, earnings, completers_count, debt_median, "
        f"value_flag FROM '{PARQUET}' WHERE unitid IN ({', '.join(repr(u) for u in partial)})"
    ).fetchall():
        truth.setdefault(u, {})[(cip, lvl)] = (e, c, d, flag)
    for u, text in out.items():
        rows = list(csv.DictReader(io.StringIO(text)))
        keys = [(r["cip_code"], r["credential_level"]) for r in rows]
        assert len(rows) == len(partial[u]) == len(truth[u]), u
        assert len(set(keys)) == len(keys) and set(keys) == set(truth[u]), u
        for r in rows:
            e, c, d, flag = truth[u][(r["cip_code"], r["credential_level"])]
            shown = r["status"] in ("pass", "fail", "no_benchmark")
            assert bool(r["earnings_median"]) == shown and bool(r["earnings_window"]) == shown
            if r["status"] == "nothing_reported":
                assert e is None and c is None and d is None and not r["graduates"]
            if r["status"] == "earnings_not_published":
                assert e is None and (c is not None or d is not None)
            if r["status"] in ("pass", "fail"):
                assert flag.startswith("passes" if r["status"] == "pass" else "fails")
    assert "insufficient" not in "".join(out.values())


def test_penn_state_keeps_the_three_states_apart(partial):
    rows = list(
        csv.DictReader(io.StringIO(programs_csv(duckdb.connect(), PARQUET, ["214777"])["214777"]))
    )
    got = {s: sum(1 for r in rows if r["status"] == s) for s in {r["status"] for r in rows}}
    assert got == {"pass": 183, "fail": 1, "earnings_not_published": 221, "nothing_reported": 84}
    assert {r["earnings_window"] for r in rows if r["earnings_median"]} <= {
        "4 years after completion",
        "1 year after completion",
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_notice_is_replaced_only_when_the_table_starts(profiles, tmp_path):
    if not (ROOT / "node_modules" / "jsdom").exists():
        pytest.skip("jsdom not installed")
    _, rows = profiles["214777"]
    html, _ = _page(rows)
    page = tmp_path / "p.html"
    page.write_text(html)
    script = tmp_path / "run.js"
    script.write_text(
        """
const fs = require("fs");
const { JSDOM } = require(process.argv[2] + "/node_modules/jsdom");
const html = fs.readFileSync(process.argv[3], "utf8").replace(/<script[^>]*src=[^>]*><\\/script>/g, "");
function run(load) {
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://truewise.dev/college/x/" });
  const w = dom.window;
  if (load) {
    w.eval(fs.readFileSync(process.argv[2] + "/components/table.js", "utf8"));
    w.eval(fs.readFileSync(process.argv[2] + "/components/profile.js", "utf8"));
  }
  // profile.js enhances on DOMContentLoaded, so read the page after it has fired.
  return new Promise((done) => setTimeout(() => {
    const d = w.document;
    done({ notice: !!d.querySelector("[data-tw-partial]"),
           count: (d.querySelector(".tw-table__count") || {}).textContent || "",
           csv: d.querySelectorAll('a[href="programs.csv"]').length });
  }, 200));
}
Promise.all([run(false), run(true)]).then(([failed, ok]) => console.log(JSON.stringify({ failed, ok })));
"""
    )
    res = subprocess.run(
        ["node", str(script), str(ROOT), str(page)], capture_output=True, text=True, timeout=60
    )
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout.strip().splitlines()[-1])
    assert got["failed"]["notice"] and got["failed"]["csv"] == 2, "script missing: notice stays"
    assert not got["ok"]["notice"], "table running: the notice gives way to the live count"
    assert got["ok"]["count"].startswith(f"Showing 20 of {len(rows)} programs"), got
    assert got["ok"]["csv"] == 1, "the complete list is still linked after enhancement"


def _page_live(rows, threshold):
    meta = {"unitid": "1", "name": "Big State University", "state": "PA", "control": "Public"}
    return canonical_page(meta, rows, "big-state", 36498.0, threshold)


def test_live_profiles_send_every_program_and_link_the_csv(profiles):
    """Option B (30 September 2026): measured acceptable on the largest profile, so every program
    is in the HTML. The 245 largest keep a complete CSV, linked below the table."""
    from pipeline.build_canonical_profiles import CSV_MIN_PROGRAMS, LIVE_STATIC_ROWS

    biggest = max(len(rows) for _, rows in profiles.values())
    assert LIVE_STATIC_ROWS >= biggest
    _, rows = profiles["214777"]
    html, tail = _page_live(rows, LIVE_STATIC_ROWS)
    assert tail is None and html.count('<tr class="tw-tr') == len(rows) == 489
    assert "data-tw-partial" not in html, "nothing is partial, so nothing says it is"
    assert html.count(f'href="{PROGRAMS_CSV}" download') == 1 and len(rows) > CSV_MIN_PROGRAMS
    small, _ = _page_live(profiles["461111"][1], LIVE_STATIC_ROWS)
    assert PROGRAMS_CSV not in small
