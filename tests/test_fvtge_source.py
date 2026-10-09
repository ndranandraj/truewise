"""pipeline/build_fvtge_source.py: ED's FVT/GE reporting spreadsheets, read row for row or refused.

Synthetic workbooks in the 8 October layout exercise each refusal rule without ED's files, so these
run in CI. Two further tests use the real releases when they are present locally (data/ is not
committed): August must reproduce published/fvtge_reporting.parquet exactly, and October must agree
with ED's own frequency counts.
"""

from __future__ import annotations

import dataclasses
from collections import Counter

import duckdb
import openpyxl
import pytest

from pipeline import build_fvtge_source as S

ROOT = S.ROOT


def _row(op, name="A College", state="CA", control="Public", prior=None, current=None):
    prior = prior or ["Submitted"] * 7
    current = current or ["Submitted"] * 3
    rel = S.OCT
    d = dict(zip(S.PRIOR, prior, strict=True)) | dict(zip(S.CURRENT, current, strict=True))
    out = {"opeid6": op, "instnm": name, "stabbr": state, "control": control, **d}
    for num, (group, flag, yes, no) in rel.counts.items():
        n = sum(d[c] == "Not Submitted" for c in group)
        out[num], out[flag] = n, (yes if n else no)
    return out


def _book(
    path,
    rows,
    *,
    header=None,
    phrase="compiled on October 5th, 2026",
    freq_edit=None,
    raw_rows=None,
):
    """A workbook in the October layout; the Frequencies sheet is computed from the rows unless edited."""
    cols = header or list(S.OCT.columns)
    wb = openpyxl.Workbook()
    wb.active.title = "Overview"
    wb["Overview"].append(["UPDATE 10/8/2026: a test file."])
    wb.create_sheet("Technical").append([f"Date: These data were {phrase}."])
    data = wb.create_sheet("Data")
    data.append(cols)
    for r in raw_rows if raw_rows is not None else [[d.get(c) for c in cols] for d in rows]:
        data.append(r)
    freq = wb.create_sheet("Frequencies")
    freq.append(["Variable", "Outcome", "Count (N)", "Frequency (%)"])
    freq.append(["opeid6", "Six-digit OPEID code", "N/A", "N/A"])
    for var in [c for c in cols if c not in ("opeid6", "instnm", "stabbr")]:
        counts = Counter(str(d[var]) for d in rows if var in d)
        for i, (outcome, n) in enumerate(sorted(counts.items())):
            freq.append([var if i == 0 else None, outcome, n, round(100 * n / len(rows), 1)])
    if freq_edit:
        freq_edit(freq)
    wb.save(path)


def _release(path):
    return dataclasses.replace(S.OCT, path=path)


ROWS = [
    _row("000001"),
    _row(
        "000002",
        control="Private For-Profit",
        prior=["Not Submitted"] * 7,
        current=["Not Submitted"] * 3,
    ),
    _row(
        "000003",
        prior=["Not Required*"] + ["Submitted"] * 6,
        current=["Update: No Longer Required"] * 3,
    ),
]


def test_a_valid_file_keeps_every_row_and_value_exactly(tmp_path):
    p = tmp_path / "ok.xlsx"
    _book(p, ROWS)
    body = S.read_rows(_release(p), check_sha=False)
    assert [d["opeid6"] for d in body] == ["000001", "000002", "000003"]
    assert body == [{c: d[c] for c in S.OCT.columns} for d in ROWS]
    # ED's statuses are kept verbatim, asterisk and all.
    assert (
        body[2]["total2223"] == "Not Required*"
        and body[2]["program2526"] == "Update: No Longer Required"
    )
    out = tmp_path / "out.parquet"
    S.write(_release(p), body, out)
    got = duckdb.sql(f"SELECT * FROM '{out}' ORDER BY opeid6").fetchall()
    assert len(got) == 3 and got[1][S.OCT.columns.index("num_miss_total")] == 10
    cols = [c[0] for c in duckdb.sql(f"DESCRIBE SELECT * FROM '{out}'").fetchall()]
    assert cols == [*S.OCT.columns, "compiled", "published", "source_url", "source_sha256"]


def test_a_fully_empty_row_is_skipped_but_counted_rows_are_not(tmp_path):
    p = tmp_path / "gap.xlsx"
    raw = [[d.get(c) for c in S.OCT.columns] for d in ROWS]
    raw.insert(1, [None] * len(S.OCT.columns))
    _book(p, ROWS, raw_rows=raw)
    assert len(S.read_rows(_release(p), check_sha=False)) == 3


@pytest.mark.parametrize(
    ("why", "change", "message"),
    [
        (
            "unknown status",
            lambda rows: rows[0].update(total2223="Submitted (late)"),
            "unknown submission status",
        ),
        ("duplicate OPEID", lambda rows: rows[1].update(opeid6="000001"), "appears twice"),
        ("short OPEID", lambda rows: rows[0].update(opeid6="12345"), "not six characters"),
        ("unknown control", lambda rows: rows[0].update(control="Tribal"), "unknown control"),
        ("count disagrees", lambda rows: rows[1].update(num_miss_prior=6), "num_miss_prior is 6"),
        (
            "flag disagrees",
            lambda rows: rows[0].update(
                yes_missing_current="HAS MISSING FILE(S) FROM CURRENT CYCLE"
            ),
            "yes_missing_current",
        ),
    ],
)
def test_a_bad_row_is_refused(tmp_path, why, change, message):
    rows = [dict(d) for d in ROWS]
    change(rows)
    p = tmp_path / "bad.xlsx"
    _book(p, rows)
    with pytest.raises(SystemExit, match=message):
        S.read_rows(_release(p), check_sha=False)


def test_a_row_with_values_but_no_opeid_is_refused_not_dropped(tmp_path):
    raw = [[d.get(c) for c in S.OCT.columns] for d in ROWS]
    raw[2][0] = None
    p = tmp_path / "noid.xlsx"
    _book(p, ROWS, raw_rows=raw)
    with pytest.raises(SystemExit, match="not six characters"):
        S.read_rows(_release(p), check_sha=False)


def test_a_changed_header_is_refused(tmp_path):
    cols = list(S.OCT.columns)
    cols[-1], cols[-2] = cols[-2], cols[-1]  # ED swapped two columns between August and September
    p = tmp_path / "hdr.xlsx"
    _book(p, ROWS, header=cols)
    with pytest.raises(SystemExit, match="changed the Data sheet's columns"):
        S.read_rows(_release(p), check_sha=False)


def test_a_different_compile_date_is_refused(tmp_path):
    p = tmp_path / "date.xlsx"
    _book(p, ROWS, phrase="compiled on November 2nd, 2026")
    with pytest.raises(SystemExit, match="does not say"):
        S.read_rows(_release(p), check_sha=False)


def test_a_file_that_is_not_the_registered_release_is_refused(tmp_path):
    p = tmp_path / "other.xlsx"
    _book(p, ROWS)
    with pytest.raises(SystemExit, match="SHA-256 differs"):
        S.read_rows(_release(p))


def test_the_frequencies_sheet_must_agree_both_ways(tmp_path):
    def wrong_count(ws):
        for row in ws.iter_rows(min_row=2):
            if row[1].value == "Not Submitted" and isinstance(row[2].value, int):
                row[2].value += 1
                return

    p = tmp_path / "freq.xlsx"
    _book(p, ROWS, freq_edit=wrong_count)
    with pytest.raises(SystemExit, match="Frequencies sheet gives"):
        S.read_rows(_release(p), check_sha=False)

    def drop_value(ws):
        for row in ws.iter_rows(min_row=2):
            # Not a variable's first outcome, so the variable's name stays on the sheet.
            if row[1].value == "Update: No Longer Required" and row[0].value is None:
                for c in row:
                    c.value = None
                return

    p2 = tmp_path / "freq2.xlsx"
    _book(p2, ROWS, freq_edit=drop_value)
    with pytest.raises(SystemExit, match="does not list"):
        S.read_rows(_release(p2), check_sha=False)


def test_only_august_has_a_default_output():
    assert S.AUG.default_out == ROOT / "published" / "fvtge_reporting.parquet"
    assert S.OCT.default_out is None
    with pytest.raises(SystemExit, match="pass --out"):
        S.main(["--release", "2026-10-05"])


@pytest.mark.skipif(not S.AUG.path.exists(), reason="ED's August file is not in data/raw here")
def test_august_reproduces_the_published_file_exactly(tmp_path):
    out = tmp_path / "aug.parquet"
    S.write(S.AUG, S.read_rows(S.AUG), out)
    pub = ROOT / "published" / "fvtge_reporting.parquet"
    a = duckdb.sql(f"SELECT * FROM '{pub}' ORDER BY opeid6").fetchall()
    b = duckdb.sql(f"SELECT * FROM '{out}' ORDER BY opeid6").fetchall()
    assert len(a) == 4635 and a == b


@pytest.mark.skipif(not S.OCT.path.exists(), reason="ED's October file is not in data/raw here")
def test_october_keeps_every_row_and_agrees_with_ed():
    body = S.read_rows(S.OCT)
    # An independent re-read of the Data sheet, without the parser: same OPEIDs, same values.
    rows = list(
        openpyxl.load_workbook(S.OCT.path, read_only=True)["Data"].iter_rows(values_only=True)
    )
    raw = {r[0]: dict(zip(rows[0], r, strict=True)) for r in rows[1:] if r and r[0]}
    assert len(body) == len(raw) == 4674
    assert all(raw[d["opeid6"]] == d for d in body)
    # ED's own Frequencies sheet, stated in the file: the parser has already checked every count;
    # these are the figures the finding uses.
    count = lambda f: sum(1 for d in body if f(d))  # noqa: E731
    assert count(lambda d: d["num_miss_prior"] > 0) == 1396
    assert count(lambda d: d["num_miss_prior"] == 7) == 478
    assert count(lambda d: d["num_miss_current"] > 0) == 1007
    assert count(lambda d: d["num_miss_current"] == 3) == 633
