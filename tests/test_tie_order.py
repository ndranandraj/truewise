"""Rows with equal figures keep one order, whatever the thread count or the hash seed.

Found 27 October 2026 as files that differed between clean builds under different PYTHONHASHSEED
values, but the seed was not the cause: two builds under ONE seed differed too (10 files, 2 November),
and on one DuckDB thread nothing differed under any seed. An ORDER BY without a unique final key leaves
equal rows in whichever order DuckDB's threads finish, so state lists, the debt list, the STATS fields
and the FVT/GE files could change between deploys with no change in the data. On the debt list that
also changed which fields appeared: three fields tie at 20 programs for the last two places.

So the test across processes varies the thread count as well as the seed, on the committed parquets,
through the real builders. A test that varied only the seed would not exercise the cause.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

import pipeline.build_fvtge as bf
import pipeline.build_k12 as bk
import pipeline.build_lists as bl
import pipeline.build_stats_exposure as bse

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = ROOT / "published"

# (hash seed, DuckDB threads). The same seed appears under different thread counts and the same thread
# count under different seeds. One thread gives a fixed order, and on the old queries that order was
# not the one the parallel runs gave, so this fails every time rather than on a lucky draw.
RUNS = [("0", "1"), ("1", "1"), ("1", "4"), ("2", "8"), ("3", "8"), ("4", "2")]

_RENDER = """
import hashlib, json, pathlib, sys, tempfile
import duckdb

threads = sys.argv[1]
_connect = duckdb.connect


def connect(*args, **kwargs):
    con = _connect(*args, **kwargs)
    con.execute(f"SET threads={threads}")
    return con


duckdb.connect = connect

import pipeline.build_fvtge as bf
import pipeline.build_k12 as bk
import pipeline.build_lists as bl
import pipeline.build_stats_exposure as bse
from pipeline.config import ROOT

published = ROOT / "published"
out = pathlib.Path(tempfile.mkdtemp())
no_card = lambda *args, **kwargs: None
bl.render_card = bse.render_card = bf.render_card = no_card
bl.SITE = out
bl.PARQUET_DIR = bse.PARQUET_DIR = bk.PARQUET_DIR = published
bf.OUT_DIR = out / "fvtge"
bk.OUT_DIR = out / "k12"

pages = {}
con = duckdb.connect()
bl._views(con)
# Only the states with a tie: every state takes this test past a minute across its runs.
con.execute("ALTER VIEW sch RENAME TO sch_all")
con.execute("CREATE VIEW sch AS SELECT * FROM sch_all WHERE st IN ('CT', 'DC', 'LA', 'OR', 'VA')")
for slug, _, page in bl.build_major_lists(con, {}) + bl.build_state_lists(con, {}):
    pages[slug] = page
pages["stats"] = bse.render_page(bse.compute_exposure(duckdb.connect()))
fv = bf._con()
bf.write_outputs(bf.compute(fv), bf.institutions(fv))
bk.main()
for name, page in pages.items():
    (out / f"{name}.html").write_text(page)
print(json.dumps({
    str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(out.rglob("*")) if p.is_file()
}))
"""


def test_builds_agree_across_thread_counts_and_hash_seeds():
    runs = {}
    for seed, threads in RUNS:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", _RENDER, threads],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, out.stderr
        # The last line: the K-12 builder prints its own summary first.
        runs[(seed, threads)] = json.loads(out.stdout.splitlines()[-1])
    first = runs[RUNS[0]]
    assert any("debt-does-not-pay-back" in name for name in first), "the debt list was not built"
    assert any("fastest-debt-payback" in name for name in first), "the payback list was not built"
    assert any(name.startswith("fvtge/") and name.endswith(".csv") for name in first)
    assert "stats.html" in first and "k12/index.json" in first
    assert len({tuple(r) for r in runs.values()}) == 1, "the runs did not write the same files"
    differ = sorted(n for n in first if len({r[n] for r in runs.values()}) > 1)
    assert not differ, f"these outputs depend on the thread count or the hash seed: {differ}"


def _vc(tmp_path, monkeypatch, rows) -> duckdb.DuckDBPyConnection:
    """A value_check parquet from (unitid, name, state, field, flag, earnings) rows, in a list view.

    A row can carry its debt_payback_years as a seventh value; otherwise it is 1.0.
    """
    pq = tmp_path / "parquet"
    pq.mkdir()
    cips: dict[str, str] = {}
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE vc(unitid VARCHAR, inst_name VARCHAR, state VARCHAR, cip_code VARCHAR,
        cip_desc VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, earnings DOUBLE,
        debt_median DOUBLE, debt_payback_years DOUBLE, value_flag VARCHAR)"""
    )
    con.executemany(
        "INSERT INTO vc VALUES (?, ?, ?, ?, ?, '3', 'Bachelor''s Degree', ?, 9000.0, ?, ?)",
        [
            (
                uid,
                name,
                state,
                cips.setdefault(field, f"{len(cips):04d}"),
                field,
                earnings,
                payback[0] if payback else 1.0,
                flag,
            )
            for uid, name, state, field, flag, earnings, *payback in rows
        ],
    )
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bl, "PARQUET_DIR", pq)
    monkeypatch.setattr(bl, "SITE", tmp_path / "site")
    monkeypatch.setattr(bl, "render_card", lambda *args, **kwargs: None)
    view = duckdb.connect()
    bl._views(view)
    return view


def _csv_rows(tmp_path, slug) -> list[list[str]]:
    with (tmp_path / "site" / "data" / "lists" / bl.csv_filename(slug)).open(newline="") as f:
        return list(csv.reader(f))[1:]


def _csv_names(tmp_path, slug) -> list[str]:
    return [row[1] for row in _csv_rows(tmp_path, slug)]


def _programs(counts) -> list[tuple]:
    """Rows for fields with this many programs below the line, each program at its own school."""
    return [
        (f"{f}{i:03d}", "S", "TX", field, "fails_earnings_premium", 20000.0)
        for f, (field, n) in enumerate(counts, 1)
        for i in range(n)
    ]


def _paybacks(fields) -> list[tuple]:
    """Rows from {field: debt_payback_years of each program}, each program at its own school."""
    return [
        (f"{f}{i:03d}", "S", "TX", field, "passes_earnings_premium", 60000.0, years)
        for f, (field, figures) in enumerate(fields.items(), 1)
        for i, years in enumerate(figures)
    ]


def test_the_debt_list_settles_ties_by_name_and_keeps_a_tie_at_the_cut(tmp_path, monkeypatch):
    # Four fields with 10 programs below the line, one with 12, listed out of order. A cut at two rows
    # lands inside the tie, so a hard limit would drop three of them for how their names sort.
    counts = (
        ("Zoology", 10),
        ("art History", 10),
        ("Biology", 10),
        ("Cosmetology", 12),
        ("Welding", 10),
    )
    view = _vc(tmp_path, monkeypatch, _programs(counts))
    monkeypatch.setattr(bl, "TOP_N", 2)
    pages = {slug: page for slug, _, page in bl.build_major_lists(view, {})}
    slug = "programs-where-debt-does-not-pay-back"
    # "art History" sorts with the a's: alphabetical ignores case, as a reader expects.
    assert _csv_names(tmp_path, slug) == [
        "Cosmetology",
        "art History",
        "Biology",
        "Welding",
        "Zoology",
    ]
    assert "Fields with the same count are listed alphabetically." in pages[slug]
    assert "A tie at the cut-off is kept, so this list can run past 2 rows." in pages[slug]


def test_a_cut_clear_of_any_tie_still_holds(tmp_path, monkeypatch):
    view = _vc(
        tmp_path, monkeypatch, _programs((("Biology", 12), ("Cosmetology", 11), ("Welding", 10)))
    )
    monkeypatch.setattr(bl, "TOP_N", 2)
    bl.build_major_lists(view, {})
    assert _csv_names(tmp_path, "programs-where-debt-does-not-pay-back") == [
        "Biology",
        "Cosmetology",
    ]


def test_the_payback_list_keeps_a_tie_at_the_figure_it_shows(tmp_path, monkeypatch):
    # 23 fields show 0.5 years for the last two of 25 places on the June 2026 release. A hard limit left
    # 21 out for how their names sort, among them Registered Nursing (835 programs).
    # debt_payback_years is rounded to one decimal per program, so a median can only fall between two
    # programs, as Forestry's does here at 0.45. That is not a finer figure: it shows as 0.5 and ties.
    fields = {
        "Zoology": [0.5] * 10,
        "art History": [0.5] * 10,
        "Forestry": [0.4] * 5 + [0.5] * 5,
        "Cosmetology": [0.3] * 10,
        "Welding": [0.6] * 10,
    }
    view = _vc(tmp_path, monkeypatch, _paybacks(fields))
    monkeypatch.setattr(bl, "TOP_N", 2)
    pages = {slug: page for slug, _, page in bl.build_major_lists(view, {})}
    slug = "fastest-debt-payback-majors"
    assert [(row[1], row[2]) for row in _csv_rows(tmp_path, slug)] == [
        ("Cosmetology", "0.3 yrs"),
        ("art History", "0.5 yrs"),
        ("Forestry", "0.5 yrs"),
        ("Zoology", "0.5 yrs"),
    ]
    assert "Fields with the same figure are listed alphabetically." in pages[slug]
    assert "A tie at the cut-off is kept, so this list can run past 2 rows." in pages[slug]


def test_the_committed_payback_list_leaves_out_no_field_at_the_figure_it_ends_on(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bl, "PARQUET_DIR", PUBLISHED)
    monkeypatch.setattr(bl, "SITE", tmp_path / "site")
    monkeypatch.setattr(bl, "render_card", lambda *args, **kwargs: None)
    view = duckdb.connect()
    bl._views(view)
    bl.build_major_lists(view, {})
    eligible = view.sql(
        f"""SELECT rtrim(cip_desc,'. ') AS field, round(median(debt_payback_years),1) AS pb, count(*)
        FROM pu WHERE credential_level='3' AND debt_payback_years IS NOT NULL
        GROUP BY field HAVING count(*) >= {bl.MIN_PROGRAMS}"""
    ).fetchall()
    # The rule, restated without SQL: the figure at the last of TOP_N places decides, and every field
    # at or below it is in, by figure and then name ignoring case.
    last_figure = sorted(pb for _, pb, _ in eligible)[bl.TOP_N - 1]
    expected = sorted(
        (pb, field.lower(), field, n) for field, pb, n in eligible if pb <= last_figure
    )
    assert [tuple(row[1:]) for row in _csv_rows(tmp_path, "fastest-debt-payback-majors")] == [
        (field, f"{pb:g} yrs", f"{n:,}") for pb, _, field, n in expected
    ]


def test_a_state_list_settles_ties_by_name_ignoring_case_then_unitid(tmp_path, monkeypatch):
    passes = "passes_earnings_premium"
    schools = [
        ("105", "Southern University Law Center", 50000.0),
        ("104", "Southern University and A & M College", 50000.0),
        # The same name twice: the unitid decides.
        ("102", "Empire Beauty School", 50000.0),
        ("101", "Empire Beauty School", 50000.0),
        # Higher median earnings outrank any name.
        ("103", "Zeta College", 60000.0),
    ]
    view = _vc(
        tmp_path,
        monkeypatch,
        [(uid, name, "CT", "Biology", passes, pay) for uid, name, pay in schools],
    )
    monkeypatch.setattr(bl, "MIN_SCHOOL_PROGRAMS", 1)
    links = {uid: f"school-{uid}" for uid, _, _ in schools}
    pages = {slug: page for slug, _, page in bl.build_state_lists(view, links)}
    slug = "best-value-colleges-ct"
    assert _csv_names(tmp_path, slug) == [
        "Zeta College",
        "Empire Beauty School",
        "Empire Beauty School",
        "Southern University and A & M College",
        "Southern University Law Center",
    ]
    assert (
        "Schools with the same share are ordered by median earnings, then by name." in pages[slug]
    )
    # The two Empire rows read the same in the CSV, so their links show the order.
    assert pages[slug].index("/college/school-101/") < pages[slug].index("/college/school-102/")


def test_the_committed_data_is_in_the_stated_order(monkeypatch):
    # Order among ties on the real files. The K-12 order held between processes before this fix,
    # because its parquet has one row group, so only this checks it: a DuckDB version could flip it.
    inst = bf.institutions(bf._con())
    keys = [(i["state"], i["name"], i["opeid6"]) for i in inst]
    assert keys == sorted(keys), "FVT/GE rows are not in state, name, OPEID order"

    monkeypatch.setattr(bse, "PARQUET_DIR", PUBLISHED)
    s = bse.compute_exposure(duckdb.connect())
    fields = [(-below, field.lower(), field) for field, below, _ in s["top_fields"]]
    assert fields == sorted(fields), "STATS fields are not in count, then name order"
    creds = [(-with_earn, cred) for cred, with_earn, _ in s["by_cred"]]
    assert creds == sorted(creds), "STATS credentials are not in count, then name order"


def test_same_named_schools_keep_one_order_in_the_k12_index(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "PARQUET_DIR", PUBLISHED)
    monkeypatch.setattr(bk, "OUT_DIR", tmp_path / "k12")
    bk.main()
    schools = json.loads((tmp_path / "k12" / "index.json").read_text())["schools"]
    keys = [(s["n"], s["k"]) for s in schools]
    assert keys == sorted(keys), "K-12 index rows are not in name, then COMBOKEY order"
