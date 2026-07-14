"""Truewise pipeline configuration.

Central place for source URLs, paths, and the field mapping used to build the
Value Check spine from College Scorecard's Field-of-Study data.

Field names: College Scorecard's bulk CSV column names are stable but occasionally
renamed between releases, and the Field-of-Study dictionary lives in an .xlsx we
can't parse blind. So instead of hard-coding one name per concept, each logical
field lists CANDIDATE column names; `resolve_columns()` picks the first that is
actually present in the downloaded file and fails loudly if none match. That keeps
the pipeline honest across data refreshes.

Confirmed from the College Scorecard changelog (2026-03-23 release): EARN_THR_STATE
and EARN_THR_NAT are the state/national earnings thresholds (typical HS-grad earnings
benchmark) that underpin the federal earnings-premium (EP) test.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
ARCHIVE_DIR = ROOT / "archive" / "fvt"  # dated snapshots = FVT/GE Monitor artifacts
DB_PATH = DATA_DIR / "truewise.duckdb"
PARQUET_DIR = DATA_DIR / "parquet"

# The Scorecard data home lists date-stamped bulk files. We parse the current
# "Most Recent ... Field of Study" link from this page rather than hard-code a
# filename that changes each release.
SCORECARD_DATA_HOME = "https://collegescorecard.ed.gov/data/"

# --- Field-of-Study logical field -> candidate column names (first present wins) ---
# Keys are Truewise's internal names; values are ordered candidates to look for.
FOS_FIELD_CANDIDATES: dict[str, list[str]] = {
    # Identity / grain
    "unitid": ["UNITID"],
    "opeid6": ["OPEID6"],
    "inst_name": ["INSTNM"],
    "control": ["CONTROL"],
    "state": ["STABBR", "ST_FIPS"],
    "cip_code": ["CIPCODE"],
    "cip_desc": ["CIPDESC"],
    "credential_level": ["CREDLEV"],
    "credential_desc": ["CREDDESC"],
    "completers_count": ["IPEDSCOUNT1", "IPEDSCOUNT2"],
    # Earnings after completion (median). Candidates cover recent renames; the
    # 2026-03-23 release added a 4-year-after-completion measure.
    "earnings_median_1yr": ["EARN_MDN_1YR", "EARN_MDN_HI_1YR", "MD_EARN_WNE_1YR"],
    "earnings_median_4yr": ["EARN_MDN_4YR", "EARN_MDN_HI_4YR", "MD_EARN_WNE_4YR"],
    # Earnings thresholds = typical HS-grad earnings (the EP benchmark). CONFIRMED.
    "earnings_threshold_state": ["EARN_THR_STATE"],
    "earnings_threshold_national": ["EARN_THR_NAT"],
    # Median debt at graduation for the program.
    "debt_median": [
        "DEBT_ALL_STGP_EVAL_MDN",
        "DEBT_ALL_STGP_EVAL_MDN10YR",
        "DEBT_ALL_STGP_ANY_MDN",
        "DEBTMEDIAN",
    ],
}

# Scorecard suppresses small-cohort values. These sentinels must become NULL and
# be surfaced as "insufficient data" — never imputed.
SUPPRESSION_SENTINELS = {"PrivacySuppressed", "PS", "NULL", "", "NA"}

# Preferred earnings horizon for the earnings-premium test (fallback order).
EARNINGS_FOR_EP = ["earnings_median_1yr", "earnings_median_4yr"]
