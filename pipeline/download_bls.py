"""Download the three public inputs for the Careers demand layer and extract them to CSV.

Runs where there is open network (your Mac, or GitHub Actions), NOT in the restricted build
sandbox. Each source is fetched, the one sheet/columns we need is read, and a small CSV is
written to data/raw/ for pipeline.build_careers_demand:

  * cip_soc_crosswalk.csv  <- NCES CIP 2020 -> SOC 2018 crosswalk
  * oews_national.csv      <- BLS OEWS national occupational wages (median annual wage)
  * ep_projections.csv     <- BLS Employment Projections (2023-33 % change + annual openings)

The URLs are pinned below and may need updating when NCES/BLS publish a new vintage. Because
the source layouts drift, this downloader is deliberately thin: it pulls the file, keeps only
the columns build_careers_demand resolves, and writes a plain CSV. If a URL 404s, update the
constant here. Needs `requests`, `pandas`, and `openpyxl` (see requirements.txt).

Usage (run from the repo root, on a machine with network access):
    python -m pipeline.download_bls
"""

from __future__ import annotations

import io
import zipfile

from pipeline.config import RAW_DIR

# Pinned sources. Update these when a newer vintage is published.
CIP_SOC_XLSX = "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx"
OEWS_NAT_ZIP = "https://www.bls.gov/oes/special-requests/oesm23nat.zip"
OEWS_MEMBER = "national_M2023_dl.xlsx"  # the sheet inside the OEWS zip
EP_XLSX = "https://www.bls.gov/emp/tables/occupational-projections-and-openings.xlsx"


def _get(url: str) -> bytes:
    import requests  # imported lazily so the build sandbox need not have it

    r = requests.get(
        url, headers={"User-Agent": "truewise-data (github.com/ndranandraj)"}, timeout=120
    )
    r.raise_for_status()
    return r.content


def main() -> None:
    import pandas as pd

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. CIP -> SOC crosswalk (single sheet, columns resolved downstream).
    xwalk = pd.read_excel(io.BytesIO(_get(CIP_SOC_XLSX)), dtype=str)
    xwalk.to_csv(RAW_DIR / "cip_soc_crosswalk.csv", index=False)
    print(f"crosswalk rows: {len(xwalk):,}")

    # 2. OEWS national wages (inside a zip).
    with zipfile.ZipFile(io.BytesIO(_get(OEWS_NAT_ZIP))) as z:
        member = next((n for n in z.namelist() if n.endswith(OEWS_MEMBER)), None) or next(
            n for n in z.namelist() if n.endswith(".xlsx")
        )
        with z.open(member) as fh:
            oews = pd.read_excel(fh, dtype=str)
    oews.to_csv(RAW_DIR / "oews_national.csv", index=False)
    print(f"OEWS rows: {len(oews):,}")

    # 3. Employment Projections (percent change + annual openings).
    ep = pd.read_excel(io.BytesIO(_get(EP_XLSX)), dtype=str, header=1)
    ep.to_csv(RAW_DIR / "ep_projections.csv", index=False)
    print(f"EP rows: {len(ep):,}")

    print(f"wrote 3 CSVs -> {RAW_DIR}")


if __name__ == "__main__":
    main()
