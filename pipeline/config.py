"""Truewise pipeline configuration.

Central place for source URLs, paths, and the field mapping used to build the
Value Check spine from College Scorecard data.

Two source files are needed and joined on UNITID:
  * Field-of-Study file  -> per-program median earnings, debt, and the count of
    graduates out-earning a typical HS grad.
  * Institution file     -> the earnings THRESHOLDS (EARN_THR_STATE / EARN_THR_NAT):
    the "typical high-school-graduate earnings" benchmark. These are institution-level
    (one per school, based on its state) and are NOT in the Field-of-Study file, so
    the federal earnings-premium (median earnings vs threshold) requires this join.

Field names: bulk-CSV column names are stable but occasionally renamed between
releases, and the dictionary lives in an .xlsx we can't parse blind. So each logical
field lists CANDIDATE column names; `resolve_columns()` picks the first present and
fails loudly if a required one is missing. Names below were confirmed against the
2026 Field-of-Study file header. Suppressed values appear as 'PS' / 'NA'.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
ARCHIVE_DIR = ROOT / "archive" / "fvt"  # dated snapshots = FVT/GE Monitor artifacts
DB_PATH = DATA_DIR / "truewise.duckdb"
PARQUET_DIR = DATA_DIR / "parquet"

SCORECARD_DATA_HOME = "https://collegescorecard.ed.gov/data/"

# Bulk files to fetch: logical name -> substring identifying its link on the data home.
BULK_FILES = {
    "field_of_study": "Most-Recent-Cohorts-Field-of-Study",
    "institution": "Most-Recent-Cohorts-Institution",
}

# --- Field-of-Study: logical field -> candidate column names (first present wins) ---
FOS_FIELD_CANDIDATES: dict[str, list[str]] = {
    "unitid": ["UNITID"],
    "opeid6": ["OPEID6"],
    "inst_name": ["INSTNM"],
    "control": ["CONTROL"],
    "cip_code": ["CIPCODE"],
    "cip_desc": ["CIPDESC"],
    "credential_level": ["CREDLEV"],
    "credential_desc": ["CREDDESC"],
    "completers_count": ["IPEDSCOUNT1", "IPEDSCOUNT2"],
    # Median earnings after completion.
    "earnings_median_1yr": ["EARN_MDN_1YR", "EARN_MDN_HI_1YR"],
    "earnings_median_4yr": ["EARN_MDN_4YR", "EARN_MDN_HI_4YR"],
    # Count of graduates (working, not enrolled) earning above the HS-grad threshold,
    # and the working-not-enrolled denominator -> "share out-earning a HS grad".
    "earn_gt_threshold_1yr": ["EARN_GT_THRESHOLD_1YR"],
    "earn_count_wne_1yr": ["EARN_COUNT_WNE_1YR"],
    # Median debt at graduation.
    "debt_median": ["DEBT_ALL_STGP_EVAL_MDN", "DEBT_ALL_STGP_ANY_MDN"],
}
FOS_REQUIRED = ["unitid", "cip_code", "credential_level", "earnings_median_1yr"]

# --- Institution: logical field -> candidate column names ---
# EARN_THR_STATE / EARN_THR_NAT confirmed added to Scorecard on 2026-03-23.
INST_FIELD_CANDIDATES: dict[str, list[str]] = {
    "unitid": ["UNITID"],
    "inst_name": ["INSTNM"],
    "state": ["STABBR"],
    "earnings_threshold_state": ["EARN_THR_STATE"],
    "earnings_threshold_national": ["EARN_THR_NAT"],
}
INST_REQUIRED = ["unitid", "earnings_threshold_state", "earnings_threshold_national"]

# Scorecard suppresses small-cohort values. These sentinels must become NULL and
# be surfaced as "insufficient data" — never imputed.
SUPPRESSION_SENTINELS = {"PrivacySuppressed", "PS", "NULL", "", "NA"}
