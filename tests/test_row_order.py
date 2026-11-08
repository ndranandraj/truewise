"""Row order of what a data refresh writes must come from the data, not from how DuckDB ran.

The same raw files gave a different `fos` and `value_check` order on DuckDB 1.5.6 and 2.0.0, and again
on one thread. A small in-order fixture can pass by luck, so these feed shuffled inputs through the
real writers, across thread counts, and compare the rows in file order.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import duckdb
import pytest

import pipeline.build_k12 as bk
import pipeline.build_package_data as bp
import pipeline.build_spine as bs
import pipeline.value_check as vc
from pipeline.monitor_diff import compute_diff, render_markdown
from pipeline.sorted_parquet import PROGRAM_KEY, write_sorted_parquet

FOS_HEADER = (
    "UNITID,OPEID6,INSTNM,CONTROL,CIPCODE,CIPDESC,CREDLEV,CREDDESC,IPEDSCOUNT1,"
    "EARN_MDN_1YR,EARN_MDN_4YR,DEBT_ALL_STGP_EVAL_MDN"
)
INST_HEADER = "UNITID,INSTNM,CITY,STABBR,INSTURL,UGDS,EARN_THR_STATE,EARN_THR_NAT"


def _fos_rows() -> list[str]:
    """Enough rows to span several DuckDB vectors, including what makes the short key repeat.

    ED's file has rows with UNITID "NA" that share a CIP and credential and differ only by OPEID6.
    """
    rows = [
        f"{100000 + u},{u:06d},School {u},Public,{c:04d},Field {c}.,3,Bachelor's Degree,10,"
        f"{30000 + u},{40000 + c},{9000 + u}"
        for u in range(60)
        for c in range(100)
    ]
    rows += [
        f"NA,{900000 + o},Closed {o},Public,0101,Field 101.,3,Bachelor's Degree,10,30000,PS,PS"
        for o in range(40)
    ]
    return rows


def _inst_rows() -> list[str]:
    return [f"{100000 + u},School {u},Town,TX,a.edu,100,35000,36000" for u in range(60)]


def _threads(monkeypatch, n: int) -> None:
    """Every duckdb.connect() in the real writers runs on `n` threads."""
    real = duckdb.connect

    def connect(*args, **kwargs):
        con = real(*args, **kwargs)
        con.execute(f"SET threads={n}")
        return con

    monkeypatch.setattr(duckdb, "connect", connect)


def _file_rows(path: Path) -> list[tuple]:
    return duckdb.sql(f"SELECT * FROM read_parquet('{path}')").fetchall()


def _run_spine(tmp: Path, seed: int, threads: int, monkeypatch) -> Path:
    """Run build_spine and value_check on shuffled CSVs; return the directory they wrote."""
    run = tmp / f"s{seed}t{threads}"
    (run / "raw").mkdir(parents=True)
    rng = random.Random(seed)
    fos, inst = _fos_rows(), _inst_rows()
    rng.shuffle(fos)
    rng.shuffle(inst)
    (run / "raw" / "Most-Recent-Cohorts-Field-of-Study.csv").write_text(
        "\n".join([FOS_HEADER, *fos]) + "\n"
    )
    (run / "raw" / "Most-Recent-Cohorts-Institution.csv").write_text(
        "\n".join([INST_HEADER, *inst]) + "\n"
    )
    with monkeypatch.context() as m:
        for mod in (bs, vc):
            m.setattr(mod, "DB_PATH", run / "tw.duckdb", raising=False)
            m.setattr(mod, "PARQUET_DIR", run / "parquet", raising=False)
        m.setattr(bs, "RAW_DIR", run / "raw")
        m.setattr(vc, "ARCHIVE_DIR", run / "archive")
        _threads(m, threads)
        bs.main()
        vc.main()
    return run


@pytest.fixture(scope="module")
def spine_runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("order")
    with pytest.MonkeyPatch.context() as m:
        return [_run_spine(tmp, seed, threads, m) for seed, threads in ((1, 1), (2, 4), (3, 1))]


def _snapshot(run: Path) -> Path:
    return next((run / "archive").glob("*/value_check_snapshot.parquet"))


@pytest.mark.parametrize(
    "written",
    [
        lambda run: run / "parquet" / "fos.parquet",
        lambda run: run / "parquet" / "value_check.parquet",
        lambda run: run / "parquet" / "institutions.parquet",
        _snapshot,
    ],
    ids=["fos", "value_check", "institutions", "snapshot"],
)
def test_spine_files_keep_one_order_whatever_the_input_order_and_threads(spine_runs, written):
    first, *others = [_file_rows(written(run)) for run in spine_runs]
    assert len(first) >= 60
    for other in others:
        assert other == first


def test_program_files_are_in_key_order(spine_runs):
    rows = duckdb.sql(
        f"SELECT {PROGRAM_KEY} FROM read_parquet('{spine_runs[0] / 'parquet' / 'value_check.parquet'}')"
    ).fetchall()
    assert rows == sorted(rows)
    assert len(set(rows)) == len(rows)
    # The rows the short key cannot tell apart are all there, in OPEID6 order.
    na = [r[1] for r in rows if r[0] == "NA"]
    assert na == [str(900000 + o) for o in range(40)]


def test_package_copy_is_in_key_order(tmp_path, monkeypatch, spine_runs):
    src = spine_runs[0] / "parquet" / "value_check.parquet"
    shuffled = tmp_path / "parquet" / "value_check.parquet"
    shuffled.parent.mkdir()
    duckdb.sql(
        f"COPY (SELECT * FROM read_parquet('{src}') ORDER BY hash(inst_name, cip_code)) TO '{shuffled}'"
    )
    monkeypatch.setattr(bp, "PARQUET_DIR", shuffled.parent)
    monkeypatch.setattr(bp, "PKG_DATA", tmp_path / "pkg")
    monkeypatch.setattr(bp, "ROOT", tmp_path)
    bp.main()
    rows = duckdb.sql(
        f"SELECT {PROGRAM_KEY} FROM read_parquet('{tmp_path / 'pkg' / 'value_check.parquet'}')"
    ).fetchall()
    assert rows == sorted(rows)
    assert all(r[0] != "NA" for r in rows)


def test_a_repeated_key_is_refused_not_written(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('a', 1), ('a', 2)) v(k, x)")
    out = tmp_path / "t.parquet"
    with pytest.raises(SystemExit, match="repeats"):
        write_sorted_parquet(con, "t", "k", out)
    assert not out.exists()


def test_every_parquet_writer_states_an_order():
    """A plain `COPY table TO` is what let these files drift. New writers fail here, not in a refresh."""
    pipeline = Path(__file__).resolve().parents[1] / "pipeline"
    seen = 0
    for py in sorted(pipeline.glob("*.py")):
        for stmt in re.findall(r"COPY\b.*?FORMAT PARQUET", py.read_text(), flags=re.DOTALL):
            seen += 1
            assert "ORDER BY" in stmt, f"{py.name} writes a parquet with no ORDER BY: {stmt[:80]}"
    assert seen >= 3  # the helper, program_unit and build_fvtge_source


K12_UNREPORTED = (
    "charter, magnet, offers_ap, ap_courses, ap_enroll, offers_calc, calc_enroll, offers_physics, "
    "phys_enroll, offers_cs, cs_enroll, offers_chem, chem_enroll, offers_dual, dual_enroll, offers_ib, "
    "ib_enroll, offers_gt, gt_enroll, fte_counselors, fte_police, fte_guards, fte_teachers, "
    "fte_teach_uncert"
).split(", ")


def _k12_parquet(path: Path, keys: list[str]) -> None:
    """A k12.parquet with these combokeys, in this file order, all named the same."""
    nulls = ", ".join(f"NULL::DOUBLE AS {c}" for c in K12_UNREPORTED)
    con = duckdb.connect()
    con.execute(
        f"""COPY (
            SELECT '2023-24' AS crdc_vintage, k AS combokey,
                   if(k::BIGINT % 2 = 0, 'OH', 'TX') AS state,
                   'CENTRAL HIGH SCHOOL' AS name, 'D' AS district, 100.0 AS enroll_total, {nulls}
            FROM (SELECT unnest({keys!r}) AS k)
        ) TO '{path}' (FORMAT PARQUET)"""
    )


def test_k12_json_does_not_depend_on_file_order(tmp_path, monkeypatch):
    """Same-named schools are the only ties, and search shows the first 40 of them."""
    keys = [f"{4800000 + i:012d}" for i in range(50)]
    outputs = []
    for label, order in (("sorted", keys), ("reversed", keys[::-1])):
        pq = tmp_path / label / "parquet"
        pq.mkdir(parents=True)
        _k12_parquet(pq / "k12.parquet", order)
        monkeypatch.setattr(bk, "PARQUET_DIR", pq)
        monkeypatch.setattr(bk, "OUT_DIR", tmp_path / label / "out")
        bk.main()
        out = tmp_path / label / "out"
        outputs.append({p.relative_to(out).as_posix(): p.read_text() for p in out.rglob("*.json")})
    assert outputs[0] == outputs[1]
    index = json.loads(outputs[0]["index.json"])["schools"]
    assert [s["k"] for s in index] == keys


SNAP_COLUMNS = (
    "unitid VARCHAR, opeid6 VARCHAR, cip_code VARCHAR, credential_level VARCHAR, "
    "credential_desc VARCHAR, inst_name VARCHAR, value_flag VARCHAR, earnings DOUBLE"
)


def _diff_rows() -> tuple[list[tuple], list[tuple]]:
    """More than the 50 examples the changelog prints, in each category it prints."""
    old, new = [], []
    for u in range(70):
        name = f"School {u}"
        old.append((str(u + 100), "0101", "3", "BA", name, "passes_earnings_premium", 50000.0))
        new.append((str(u + 100), "0101", "3", "BA", name, "fails_earnings_premium", 20000.0))
        old.append((str(u + 100), "0202", "3", "BA", name, "fails_earnings_premium", 20000.0))
        new.append((str(u + 100), "0202", "3", "BA", name, "passes_earnings_premium", 50000.0))
        old.append((str(u + 100), "0303", "3", "BA", name, "passes_earnings_premium", 50000.0))
        new.append((str(u + 100), "0404", "3", "BA", name, "passes_earnings_premium", 50000.0))
    old = [(r[0], f"{int(r[0]):06d}", *r[1:]) for r in old]
    new = [(r[0], f"{int(r[0]):06d}", *r[1:]) for r in new]
    # UNITID "NA": the same CIP and credential, told apart only by OPEID6. Each has a real revision.
    for o in range(12):
        row = ("NA", f"{o + 900:06d}", "0505", "3", "BA", f"Closed {o}", "insufficient_data")
        old.append((*row, 40000.0 + o * 2000))
        new.append((*row, 41000.0 + o * 2000))
    return old, new


def _changelog(old: list[tuple], new: list[tuple]) -> str:
    con = duckdb.connect()
    for name, rows in (("old", old), ("new", new)):
        con.execute(f"CREATE TABLE {name} ({SNAP_COLUMNS})")
        con.executemany(f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?)", rows)
    return render_markdown(compute_diff(con), "a", "b")


def test_changelog_examples_do_not_depend_on_file_order():
    old, new = _diff_rows()
    first = _changelog(old, new)
    for seed in range(5):
        rng = random.Random(seed)
        o, n = old[:], new[:]
        rng.shuffle(o)
        rng.shuffle(n)
        assert _changelog(o, n) == first
    assert "…and 20 more" in first  # the cut really is in play


def test_changelog_keeps_every_count():
    """Sorting chose which examples print; it must not change what is counted."""
    con = duckdb.connect()
    old, new = _diff_rows()
    for name, rows in (("old", old), ("new", new)):
        con.execute(f"CREATE TABLE {name} ({SNAP_COLUMNS})")
        con.executemany(f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?)", rows)
    d = compute_diff(con)
    assert len(d["newly_failing"]) == 70
    assert len(d["newly_passing"]) == 70
    assert len(d["added"]) == 70
    assert len(d["removed"]) == 70
    assert len(d["earnings_revised"]) == 152
    # Real programs print ahead of the UNITID "NA" rows, which sort after every numeric UNITID.
    assert not d["earnings_revised"][139]["inst_name"].startswith("Closed")
    assert d["earnings_revised"][140]["inst_name"].startswith("Closed")
