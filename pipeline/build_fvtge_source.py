"""Turn one of ED's FVT/GE reporting-status spreadsheets into a small source file, refusing anything
it does not recognise.

ED attached "List of Institutions That Previously Submitted FVT/GE Data" to electronic announcement
GENERAL-26-49 (11 August 2026) and re-publishes it as institutions report. Each version lists, for
every institution in scope, the status ED recorded for each required FVT/GE file component as of the
date ED compiled it. Two releases are registered here:

  2026-08-06  compiled 6 August, published 11 August: 4,635 institutions, seven components (the
              2024 and 2025 reporting cycles). The live finding is built from this one, and its
              output, published/fvtge_reporting.parquet, is unchanged by this module.
  2026-10-05  compiled 5 October, published 8 October: 4,674 institutions, ten components (adds the
              2026 cycle), ED's new statuses ("Not Required*", "Update: No Longer Required"), and
              separate prior, current and total counts.

The rules, in the order they are checked. A file that breaks any of them is refused with the reason;
nothing is guessed, renamed or mapped onto an older meaning.
  1. The file is byte-for-byte the registered release (SHA-256). A re-published file under the same
     name is a different release and must be registered, with ED's caveats re-read, before use.
  2. ED's own text names the registered compile date ("compiled on October 5th, 2026").
  3. The Data sheet's header is exactly the release's columns, in order.
  4. Every row is kept. A fully empty row is skipped; a row with any value but no OPEID is refused,
     as is a duplicate OPEID, an OPEID that is not six characters, or a missing name, state or
     control. Control must be one of ED's four.
  5. Every component status is in the release's vocabulary, kept exactly as ED wrote it.
  6. ED's derived columns agree with the components on every row: each num_miss count equals the
     number of "Not Submitted" components in its group, and each yes_missing flag is ED's exact
     wording for whether that count is above zero.
  7. ED's Frequencies sheet agrees with the rows, both ways: every listed outcome has the stated
     count (or the stated percentage, to ED's precision, where no count is given), and every value in
     the data appears in the sheet.

Usage (from repo root, with the spreadsheet in data/raw/):
    python -m pipeline.build_fvtge_source                                  # 2026-08-06, as before
    python -m pipeline.build_fvtge_source --release 2026-10-05 --out PATH  # writes PATH only
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb
import openpyxl

from pipeline.config import RAW_DIR, ROOT

PRIOR = (
    "total2223",
    "program2324",
    "annual2324",
    "total2324",
    "program2425",
    "annual2425",
    "total2425",
)
CURRENT = ("program2526", "annual2526", "total2526")
CONTROLS = {"Public", "Private Non-Profit", "Private For-Profit", "Foreign"}


@dataclass(frozen=True)
class Release:
    compiled: str
    published: str
    path: Path
    sha256: str
    url: str
    compile_sheet: str
    compile_phrase: str
    columns: tuple[str, ...]
    statuses: frozenset[str]
    # num column -> (components it counts, flag column, flag wording when > 0, wording when 0)
    counts: dict
    # Columns written after the sheet's own, with their values. The August output keeps its
    # original two so published/fvtge_reporting.parquet is reproduced exactly.
    extra: tuple[tuple[str, str], ...]
    default_out: Path | None


AUG = Release(
    compiled="2026-08-06",
    published="2026-08-11",
    path=RAW_DIR / "FVTGEDataReportingFinal.xlsx",
    sha256="7b994e293c8f4091729e1a449235d0e7a46895673aed5751d56b12f1b46a7f13",
    url="https://fsapartners.ed.gov/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx",
    compile_sheet="Overview",
    compile_phrase="compiled on August 6th, 2026",
    columns=("opeid6", "instnm", "stabbr", "control", *PRIOR, "yes_missing", "num_miss"),
    statuses=frozenset({"Submitted", "Not Submitted", "Not Required"}),
    counts={"num_miss": (PRIOR, "yes_missing", "HAS MISSING FILES", "NO MISSING FILES")},
    extra=(
        ("compiled", "2026-08-06"),
        (
            "source_url",
            "https://fsapartners.ed.gov/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx",
        ),
    ),
    default_out=ROOT / "published" / "fvtge_reporting.parquet",
)
OCT = Release(
    compiled="2026-10-05",
    published="2026-10-08",
    path=RAW_DIR / "fvtge-updates" / "FVTGEDataReportingOct082026.xlsx",
    sha256="76b99260cdb97714fffead6ed2f11c2216d04fb0d0637c7a0454d1fa116923c8",
    url="https://fsapartners.ed.gov/sites/default/files/2026-10/FVTGEDataReportingOct082026.xlsx",
    compile_sheet="Technical",
    compile_phrase="compiled on October 5th, 2026",
    columns=(
        "opeid6",
        "instnm",
        "stabbr",
        "control",
        *PRIOR,
        *CURRENT,
        "num_miss_prior",
        "yes_missing_prior",
        "num_miss_current",
        "yes_missing_current",
        "num_miss_total",
        "yes_missing_total",
    ),
    statuses=frozenset(
        {
            "Submitted",
            "Not Submitted",
            "Not Required",
            "Not Required*",
            "Update: No Longer Required",
        }
    ),
    counts={
        "num_miss_prior": (
            PRIOR,
            "yes_missing_prior",
            "HAS MISSING FILE(S) FROM PRIOR CYCLES",
            "NO MISSING FILES FROM PRIOR CYCLES",
        ),
        "num_miss_current": (
            CURRENT,
            "yes_missing_current",
            "HAS MISSING FILE(S) FROM CURRENT CYCLE",
            "NO MISSING FILES FROM CURRENT CYCLE",
        ),
        "num_miss_total": (
            PRIOR + CURRENT,
            "yes_missing_total",
            "HAS MISSING FILE(S) FROM ANY CYCLE",
            "NO MISSING FILES FROM ANY CYCLE",
        ),
    },
    extra=(
        ("compiled", "2026-10-05"),
        ("published", "2026-10-08"),
        (
            "source_url",
            "https://fsapartners.ed.gov/sites/default/files/2026-10/FVTGEDataReportingOct082026.xlsx",
        ),
        ("source_sha256", "76b99260cdb97714fffead6ed2f11c2216d04fb0d0637c7a0454d1fa116923c8"),
    ),
    default_out=None,  # decided at release; until then --out is required
)
RELEASES = {r.compiled: r for r in (AUG, OCT)}


def refuse(msg: str) -> None:
    raise SystemExit(f"Refused: {msg}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(release: Release, path: Path | None = None, check_sha: bool = True) -> list[dict]:
    """Every institution row of the release, as ED wrote it, after rules 1 to 7."""
    path = path or release.path
    if check_sha and sha256(path) != release.sha256:
        refuse(f"{path.name} is not the registered {release.compiled} release (SHA-256 differs).")
    wb = openpyxl.load_workbook(path, read_only=True)
    text = " ".join(
        str(c) for r in wb[release.compile_sheet].iter_rows(values_only=True) for c in r if c
    )
    if release.compile_phrase not in text:
        refuse(f'the {release.compile_sheet} sheet does not say "{release.compile_phrase}".')
    rows = list(wb["Data"].iter_rows(values_only=True))
    if not rows or tuple(rows[0]) != release.columns:
        refuse(f"ED changed the Data sheet's columns: {rows[0] if rows else None}")
    body, seen = [], set()
    for n, r in enumerate(rows[1:], start=2):
        if r is None or all(v is None or v == "" for v in r):
            continue
        d = dict(zip(release.columns, r, strict=True))
        op = d["opeid6"]
        if not isinstance(op, str) or len(op) != 6:
            refuse(f"row {n} has OPEID {op!r}, not six characters.")
        if op in seen:
            refuse(f"OPEID {op} appears twice.")
        seen.add(op)
        if not d["instnm"] or not d["stabbr"] or d["control"] not in CONTROLS:
            refuse(
                f"OPEID {op} has a missing name or state, or an unknown control {d['control']!r}."
            )
        comps = [c for c in release.columns if c in PRIOR or c in CURRENT]
        bad = {d[c] for c in comps} - release.statuses
        if bad:
            refuse(f"unknown submission status {sorted(bad)} for OPEID {op}.")
        for num, (group, flag, yes, no) in release.counts.items():
            ns = sum(d[c] == "Not Submitted" for c in group)
            if d[num] != ns:
                refuse(
                    f"{num} is {d[num]!r} for OPEID {op}, but {ns} of its components are Not Submitted."
                )
            if d[flag] != (yes if ns else no):
                refuse(f"{flag} is {d[flag]!r} for OPEID {op}, which disagrees with {num} = {ns}.")
        body.append(d)
    check_frequencies(wb, release, body)
    return body


def check_frequencies(wb, release: Release, body: list[dict]) -> None:
    """Rule 7: ED's Frequencies sheet against the rows, in both directions."""
    rows = list(wb["Frequencies"].iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    has_count = "Count (N)" in hdr
    i_out = hdr.index("Outcome")
    i_n = hdr.index("Count (N)") if has_count else None
    i_pct = hdr.index("Frequency (%)")
    listed: dict[str, dict[str, tuple]] = {}
    var = None
    for r in rows[1:]:
        if not r or all(v is None for v in r):
            continue
        if r[0]:
            var = str(r[0])
        if var not in release.columns or r[i_out] is None:
            continue  # notes and the identifier rows ("N/A") carry no counts
        if str(r[i_pct]) == "N/A":
            continue
        listed.setdefault(var, {})[str(r[i_out])] = (r[i_n] if has_count else None, r[i_pct])
    if not listed:
        refuse("the Frequencies sheet lists no outcomes to check against.")
    total = len(body)
    for var, outcomes in listed.items():
        actual: dict[str, int] = {}
        for d in body:
            actual[str(d[var])] = actual.get(str(d[var]), 0) + 1
        for outcome, (n, pct) in outcomes.items():
            got = actual.get(outcome, 0)
            if has_count:
                if n != got:
                    refuse(
                        f"ED's Frequencies sheet gives {n} for {var} = {outcome!r}; the rows give {got}."
                    )
            else:
                places = len(str(pct).split(".")[1]) if "." in str(pct) else 0
                if round(100 * got / total, places) != round(float(pct), places):
                    refuse(
                        f"ED's Frequencies sheet gives {pct}% for {var} = {outcome!r}; the rows give {100 * got / total:.4f}%."
                    )
        missing = set(actual) - set(outcomes)
        if missing:
            refuse(f"{var} has values {sorted(missing)} that ED's Frequencies sheet does not list.")


def write(release: Release, body: list[dict], out: Path) -> None:
    con = duckdb.connect()
    cols = ", ".join(
        f"{c} INTEGER" if c.startswith("num_miss") else f"{c} VARCHAR" for c in release.columns
    )
    con.execute(f"CREATE TABLE ed ({cols})")
    con.executemany(
        f"INSERT INTO ed VALUES ({', '.join('?' * len(release.columns))})",
        [tuple(d[c] for c in release.columns) for d in body],
    )
    extra = ", ".join(f"'{v}' AS {k}" for k, v in release.extra)
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT *, {extra} FROM ed ORDER BY opeid6) TO '{out}' (FORMAT PARQUET)")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--release", default=AUG.compiled, choices=sorted(RELEASES))
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    release = RELEASES[a.release]
    out = a.out or release.default_out
    if out is None:
        refuse(f"release {release.compiled} has no default output yet; pass --out.")
    body = read_rows(release)
    write(release, body, out)
    num = next(iter(release.counts))
    print(
        f"FVT/GE status, compiled {release.compiled}: {len(body):,} institutions, "
        f"{sum(d[num] > 0 for d in body):,} with a {num} above zero"
    )
    print(f"wrote -> {out}")


if __name__ == "__main__":
    main()
