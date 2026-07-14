"""
Truewise — data spine starter: load College Scorecard into DuckDB.

This is a STARTER STUB for Module 1 (Affordability matcher). It shows the intended shape
of the pipeline. Read PLAN.md and DATA_SOURCES.md first. Field names below are indicative —
confirm against the current Scorecard data dictionary (see DATA_SOURCES.md).

Two ways to get data:
  A) BULK download (preferred for the real pipeline): full CSV, no rate limit.
     Get the file(s) from https://collegescorecard.ed.gov/data/ then point RAW_DIR at them.
  B) API (used below for a quick sample so you can see data flowing): needs a free key
     from https://api.data.gov/signup/  (rate limit 1,000 req/IP/hour).

Setup:
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    echo "SCORECARD_API_KEY=your_key_here" > .env
    python pipeline/load_scorecard.py
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "truewise.duckdb"
API_KEY = os.getenv("SCORECARD_API_KEY", "")
API_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"

# Fields for the Affordability matcher. Confirm names in the current data dictionary.
# NPT4 = average net price by family-income bracket (the core of Module 1).
FIELDS = ",".join(
    [
        "id",  # Scorecard id
        "school.name",
        "school.state",
        "school.ownership",  # 1 public, 2 private nonprofit, 3 private for-profit
        "latest.cost.tuition.in_state",
        "latest.cost.tuition.out_of_state",
        "latest.cost.avg_net_price.public",
        "latest.cost.avg_net_price.private",
        # Net price by income bracket (public shown; private has parallel fields):
        "latest.cost.net_price.public.by_income_level.0-30000",
        "latest.cost.net_price.public.by_income_level.30001-48000",
        "latest.cost.net_price.public.by_income_level.48001-75000",
        "latest.cost.net_price.public.by_income_level.75001-110000",
        "latest.cost.net_price.public.by_income_level.110001-plus",
        "latest.completion.rate_suffix_4_pooled",
        "latest.student.demographics.pell_grant_rate",
    ]
)


def fetch_sample(per_page: int = 100, pages: int = 2) -> list[dict]:
    """Pull a small sample via the API so you can see the shape end-to-end.
    Replace with the BULK loader (option A) for the real pipeline."""
    if not API_KEY:
        raise SystemExit("Set SCORECARD_API_KEY in .env — see https://api.data.gov/signup/")
    rows: list[dict] = []
    for page in range(pages):
        resp = requests.get(
            API_URL,
            params={
                "api_key": API_KEY,
                "fields": FIELDS,
                "per_page": per_page,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        rows.extend(resp.json().get("results", []))
    return rows


def load_to_duckdb(rows: list[dict]) -> None:
    """Land the data in DuckDB. Real pipeline: read bulk CSVs directly with
    duckdb.read_csv(...) and write Parquet — DuckDB does this without pandas."""
    import pandas as pd

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.json_normalize(rows)  # noqa: F841 — DuckDB reads this local var by name in the SQL below
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE OR REPLACE TABLE scorecard_institutions AS SELECT * FROM df")
    n = con.execute("SELECT count(*) FROM scorecard_institutions").fetchone()[0]
    print(f"Loaded {n} institutions into {DB_PATH}")
    # Sanity peek — cheapest net price for a low-income family (the Module 1 question):
    col = '"latest.cost.net_price.public.by_income_level.0-30000"'
    try:
        print(
            con.execute(
                f'SELECT "school.name", "school.state", {col} AS net_price_0_30k '
                f"FROM scorecard_institutions WHERE {col} IS NOT NULL "
                f"ORDER BY net_price_0_30k LIMIT 10"
            )
            .fetchdf()
            .to_string(index=False)
        )
    except Exception as e:
        print("(adjust field names to match the current data dictionary)", e)
    con.close()


# ---------------------------------------------------------------------------
# TODO for the real spine (see PLAN.md phase 1):
#   - Switch from the API sample to BULK CSV downloads (institution + field-of-study).
#   - Build the college identity layer keyed on IPEDS UnitID / OPEID.
#   - Load the field-of-study table (school x CIP x credential) for ROI + Value Check.
#   - Handle suppressed values as "insufficient data" (never impute).
#   - Write Parquet outputs; add pytest validation (row counts, null rates, join integrity).
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("Fetching a small Scorecard sample via API (swap for bulk in the real pipeline)…")
    load_to_duckdb(fetch_sample())
