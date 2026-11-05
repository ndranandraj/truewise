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
     name is a different release and must be registered, with ED's caveats re-read, before use. The
     file is read once and every later rule parses those same bytes, so it cannot change between
     the checksum and the parse.
  2. ED's own text names the registered compile date ("compiled on October 5th, 2026").
  3. The Data sheet's header is exactly the release's columns, in order.
  4. Every row is kept. A row whose cells are all empty is skipped; any other row must be a
     complete institution, or the file is refused: a row with values (zeros included) but no OPEID,
     an OPEID that is not six digits as text (ED writes them with leading zeros, "001002", and a
     number would lose them), a duplicate OPEID (compared exactly, with no normalisation), or a
     missing name, state or control. Control must be one of ED's four. Names are kept as written.
  5. Every component status is in the release's vocabulary, kept exactly as ED wrote it.
  6. ED's derived columns agree with the components on every row: each num_miss count is an
     integer (not text, a float or a boolean) equal to the number of "Not Submitted" components in
     its group, and each yes_missing flag is ED's exact wording for whether that count is above
     zero. A release without a cycle has no columns for it: August's output has no 2026 fields,
     never zeros.
  7. ED's Frequencies sheet agrees with the rows, both ways. Its header is the release's. It has
     exactly the release's counted groups, no more and no fewer (August has no control group,
     October does), and lists each outcome of a group once. The only other rows allowed are ED's
     identifier rows (opeid6, instnm, stabbr, marked N/A) and its notes. Every listed outcome has the
     stated count (or the stated percentage, to ED's precision, where no count is given), and every
     value in the data appears in the sheet.

Output is written only after every rule passes, to a temporary file beside the target. That file is
read back and must have exactly the release's columns, in order and with their types, and the same
values with the same types, before it replaces the target. Paths reach SQL only as bound
parameters, so any filename works. On any failure the existing output is left untouched.

Usage (from repo root, with the spreadsheet in data/raw/):
    python -m pipeline.build_fvtge_source                                  # 2026-08-06, as before
    python -m pipeline.build_fvtge_source --release 2026-10-05 --out PATH  # writes PATH only
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
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
# ED lists the identifiers on its Frequencies sheet with N/A in place of counts.
FREQ_IDENTIFIERS = ("opeid6", "instnm", "stabbr")


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
    # The Frequencies sheet: its header, and the variables it gives counts or percentages for.
    freq_header: tuple[str, ...]
    freq_groups: tuple[str, ...]
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
    freq_header=("Variable", "Outcome", "Frequency (%)"),
    freq_groups=(*PRIOR, "yes_missing", "num_miss"),  # no control group in August
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
    freq_header=("Variable", "Outcome", "Count (N)", "Frequency (%)"),
    freq_groups=(
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
# The list the live finding is built from, which a check of ED's page compares against
# (pipeline/source_freshness.py). It moves when the finding does; a test holds it to the published file.
SOURCE_URL = AUG.url


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
    data = path.read_bytes()  # hashed and parsed from these same bytes
    if check_sha and hashlib.sha256(data).hexdigest() != release.sha256:
        refuse(f"{path.name} is not the registered {release.compiled} release (SHA-256 differs).")
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
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
        if not isinstance(op, str) or len(op) != 6 or not op.isdigit():
            refuse(f"row {n} has OPEID {op!r}, not six digits as text.")
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
            refuse(f"unknown submission status {sorted(map(repr, bad))} for OPEID {op}.")
        for num, (group, flag, yes, no) in release.counts.items():
            ns = sum(d[c] == "Not Submitted" for c in group)
            if type(d[num]) is not int or d[num] != ns:
                refuse(
                    f"{num} is {d[num]!r} for OPEID {op}, but {ns} of its components are Not Submitted."
                )
            if d[flag] != (yes if ns else no):
                refuse(f"{flag} is {d[flag]!r} for OPEID {op}, which disagrees with {num} = {ns}.")
        body.append(d)
    check_frequencies(wb, release, body)
    return body


def _blank(v) -> bool:
    return v is None or v == ""


def check_frequencies(wb, release: Release, body: list[dict]) -> None:
    """Rule 7: ED's Frequencies sheet against the rows, in both directions."""
    rows = list(wb["Frequencies"].iter_rows(values_only=True))
    if not rows or tuple(rows[0]) != release.freq_header:
        refuse(f"ED changed the Frequencies sheet's columns: {rows[0] if rows else None}")
    width = len(release.freq_header)
    has_count = "Count (N)" in release.freq_header
    listed: dict[str, dict[str, tuple]] = {}
    identifiers: set[str] = set()
    var = None
    for n, r in enumerate(rows[1:], start=2):
        r = tuple(r or ()) + (None,) * (width - len(r or ()))
        if all(_blank(v) for v in r):
            continue
        if not all(_blank(v) for v in r[width:]):
            refuse(f"Frequencies row {n} has values beyond the sheet's {width} columns.")
        head, outcome, *vals = r[:width]
        if isinstance(head, str) and head.startswith("Note") and all(_blank(v) for v in r[1:]):
            var = None  # a note ends the group above it
            continue
        if not _blank(head):
            var = str(head)
        if var is None:
            refuse(f"Frequencies row {n} has an outcome but no variable.")
        if var in FREQ_IDENTIFIERS:
            if (
                var in identifiers
                or _blank(head)
                or _blank(outcome)
                or any(v != "N/A" for v in vals)
            ):
                refuse(f"Frequencies row {n}: {var} is an identifier, listed once with N/A only.")
            identifiers.add(var)
            continue
        if var not in release.freq_groups:
            refuse(
                f"the Frequencies sheet has a counted group {var!r} that the {release.compiled} "
                "release does not have."
            )
        if _blank(outcome):
            refuse(f"Frequencies row {n} ({var}) has no outcome.")
        key = str(outcome)
        if key in listed.get(var, {}):
            refuse(f"the Frequencies sheet lists {var} = {key!r} twice.")
        count, pct = vals if has_count else (None, vals[0])
        if has_count and type(count) is not int:
            refuse(
                f"the Frequencies sheet gives count {count!r} for {var} = {key!r}, not a whole number."
            )
        if type(pct) not in (int, float):
            refuse(
                f"the Frequencies sheet gives percentage {pct!r} for {var} = {key!r}, not a number."
            )
        listed.setdefault(var, {})[key] = (count, pct)
    absent = [v for v in release.freq_groups if v not in listed]
    if absent:
        refuse(f"the Frequencies sheet has no group for {absent}.")
    total = len(body)
    for var in release.freq_groups:
        outcomes = listed[var]
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


def schema(release: Release) -> list[tuple[str, str]]:
    """The output's columns and types, in order: the sheet's own, then the release's extra ones."""
    own = [(c, "INTEGER" if c.startswith("num_miss") else "VARCHAR") for c in release.columns]
    return own + [(k, "VARCHAR") for k, _ in release.extra]


def write(release: Release, body: list[dict], out: Path) -> None:
    """Write to a temporary file beside `out`, read it back, and only if its columns, types and
    values all match replace `out` with it. Any failure leaves `out` as it was."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.tmp-{os.getpid()}")
    want_schema = schema(release)
    try:
        con = duckdb.connect()
        con.execute(f"CREATE TABLE ed ({', '.join(f'{c} {t}' for c, t in want_schema)})")
        rows = [
            (*(d[c] for c in release.columns), *(v for _, v in release.extra))
            for d in sorted(body, key=lambda d: d["opeid6"])
        ]
        con.executemany(f"INSERT INTO ed VALUES ({', '.join('?' * len(want_schema))})", rows)
        con.execute("COPY (SELECT * FROM ed ORDER BY opeid6) TO ? (FORMAT PARQUET)", [str(tmp)])
        con.close()
        back = duckdb.connect()
        got_schema = [
            (r[0], r[1])
            for r in back.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(tmp)]).fetchall()
        ]
        got = back.execute("SELECT * FROM read_parquet(?) ORDER BY opeid6", [str(tmp)]).fetchall()
        back.close()
        if got_schema != want_schema:
            refuse(
                f"the written file's columns or types are not the release's; {out} is unchanged."
            )
        typed = lambda rs: [tuple((type(v), v) for v in r) for r in rs]  # noqa: E731
        if typed(got) != typed(rows):
            refuse(f"the written file did not read back identically; {out} is unchanged.")
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()


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
