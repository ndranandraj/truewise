"""Fetch the three public inputs for the Careers demand layer and extract them to clean CSV.

Runs where there is open network (your Mac, or GitHub Actions), NOT in the restricted build
sandbox. Each source is a messy multi-sheet workbook; this step pulls out only the columns
pipeline.build_careers_demand needs and writes a small, canonical CSV to data/raw/:

  * cip_soc_crosswalk.csv  (cip, soc)            <- NCES CIP 2020 -> SOC 2018 crosswalk
  * oews_national.csv      (soc, title, wage)    <- BLS OEWS national wages (median annual)
  * ep_projections.csv     (soc, growth, openings) <- BLS Employment Projections (percent change
                                                     and annual openings, latest 10-year horizon)

Two robustness features, because BLS/NCES block some automated requests and move files:

  1. A browser User-Agent is sent (BLS returns 403 to non-browser agents).
  2. If a source will not download, grab it from the source page in your browser and drop the
     native file into data/raw/ (e.g. *Crosswalk*.xlsx, oesm*nat*.zip, occupation*.xlsx); each
     step prefers a local file over downloading. Steps are independent, so one failure does not
     block the others. Columns are matched by substring, so a new vintage keeps working.

Needs `requests`, `pandas`, and `openpyxl` (see requirements.txt).

Usage (run from the repo root, on a machine with network access):
    python -m pipeline.download_bls
"""

from __future__ import annotations

import io
import zipfile

from pipeline.config import RAW_DIR

CIP_SOC_XLSX = "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx"
OEWS_NAT_ZIP = "https://www.bls.gov/oes/special-requests/oesm23nat.zip"
EP_XLSX = "https://www.bls.gov/emp/tables/occupational-projections-and-openings.xlsx"

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
SOURCE_PAGES = {
    "crosswalk": "https://nces.ed.gov/ipeds/cipcode/resources.aspx (CIP 2020 to SOC 2018 crosswalk)",
    "oews": "https://www.bls.gov/oes/tables.htm (OEWS, May 2023, National, 'All data' zip)",
    "ep": "https://www.bls.gov/emp/tables/occupational-projections-and-openings.htm",
}


def _bytes(url: str, local_globs: list[str]) -> tuple[bytes, str]:
    """Return the source bytes, preferring a hand-placed local file over downloading."""
    for pattern in local_globs:
        hits = sorted(RAW_DIR.glob(pattern))
        if hits:
            return hits[-1].read_bytes(), f"local file {hits[-1].name}"
    import requests  # imported lazily so the build sandbox need not have it

    r = requests.get(url, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"}, timeout=120)
    r.raise_for_status()
    return r.content, url


def _pick(cols, *needles):
    """First column whose lowercased name contains every needle."""
    for c in cols:
        cl = str(c).lower()
        if all(n in cl for n in needles):
            return c
    raise KeyError(f"no column matching {needles} in {list(cols)}")


def _crosswalk(pd) -> None:
    raw, src = _bytes(CIP_SOC_XLSX, ["*Crosswalk*.xlsx", "*crosswalk*.xlsx"])
    xl = pd.ExcelFile(io.BytesIO(raw))
    sheet = next((s for s in xl.sheet_names if "cip" in s.lower() and "soc" in s.lower()), None)
    df = xl.parse(sheet or 0, dtype=str)
    out = pd.DataFrame(
        {"cip": df[_pick(df.columns, "cip", "code")], "soc": df[_pick(df.columns, "soc", "code")]}
    ).dropna()
    out.to_csv(RAW_DIR / "cip_soc_crosswalk.csv", index=False)
    print(f"  [OK]  crosswalk: {len(out):,} CIP-SOC pairs (from {src})")


def _oews(pd) -> None:
    raw, src = _bytes(OEWS_NAT_ZIP, ["oesm*nat*.zip", "*national_M*_dl.xlsx"])
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            member = next(n for n in z.namelist() if n.endswith("_dl.xlsx"))
            with z.open(member) as fh:
                df = pd.read_excel(fh, dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(raw), dtype=str)
    grp = _pick(df.columns, "o_group")
    df = df[df[grp].str.lower() == "detailed"]
    out = pd.DataFrame(
        {
            "soc": df[_pick(df.columns, "occ_code")],
            "title": df[_pick(df.columns, "occ_title")],
            "wage": df[_pick(df.columns, "a_median")],
        }
    )
    out.to_csv(RAW_DIR / "oews_national.csv", index=False)
    print(f"  [OK]  OEWS: {len(out):,} detailed occupations (from {src})")


def _ep(pd) -> None:
    raw, src = _bytes(EP_XLSX, ["*occupation*.xlsx", "*rojection*.xlsx", "*openings*.xlsx"])
    xl = pd.ExcelFile(io.BytesIO(raw))
    # The workbook has many tables; find the sheet carrying both percent-change and openings.
    frame = None
    for s in xl.sheet_names:
        d = xl.parse(s, dtype=str, header=1)
        try:
            _pick(d.columns, "change, percent")
            _pick(d.columns, "openings")
            _pick(d.columns, "code")
            frame = d
            break
        except KeyError:
            continue
    if frame is None:
        raise KeyError("no EP sheet with change-percent + openings columns")
    typ = _pick(frame.columns, "occupation type")
    frame = frame[frame[typ].str.lower() == "line item"]  # detailed occupations only
    out = pd.DataFrame(
        {
            "soc": frame[_pick(frame.columns, "code")],
            "growth": frame[_pick(frame.columns, "change, percent")],
            "openings": frame[_pick(frame.columns, "openings")],
        }
    )
    out.to_csv(RAW_DIR / "ep_projections.csv", index=False)
    print(f"  [OK]  EP: {len(out):,} detailed occupations (from {src})")


def main() -> None:
    import pandas as pd

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    steps = {"crosswalk": _crosswalk, "oews": _oews, "ep": _ep}
    ok = 0
    for name, fn in steps.items():
        try:
            fn(pd)
            ok += 1
        except Exception as e:  # keep going so one blocked source does not stop the others
            print(f"  [SKIP] {name}: {e}")
            print(f"         Download by hand from {SOURCE_PAGES[name]}")
            print(f"         and drop the file in {RAW_DIR}, then re-run.")
    print(f"\n{ok}/3 sources ready in {RAW_DIR}.")
    if ok < 3:
        raise SystemExit("Not all Careers demand sources are available yet (see notes above).")


if __name__ == "__main__":
    main()
