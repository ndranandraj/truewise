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
    "city": ["CITY"],
    "enrollment": ["UGDS", "UG"],
    "school_url": ["INSTURL"],
    "earnings_threshold_state": ["EARN_THR_STATE"],
    "earnings_threshold_national": ["EARN_THR_NAT"],
    # Mobility: access (share of low-income / first-gen students) + completion.
    "pell_share": ["PCTPELL"],
    "first_gen_share": ["PAR_ED_PCT_1STGEN"],
    # Completion (150% of normal time). A school reports either the 4-year (C150_4) or
    # the less-than-4-year (C150_L4) rate; build_spine coalesces the two.
    "completion_4yr": ["C150_4"],
    "completion_l4": ["C150_L4"],
    # Loan repayment, borrower-based, two years after entering repayment, for students who
    # COMPLETED (graduates), which matches how the rest of the site counts people. These are
    # shares of borrowers in each status and sum to about 1 across the status categories.
    "repay_completers_n": ["BBRR2_FED_UGCOMP_N"],
    "repay_default": ["BBRR2_FED_UGCOMP_DFLT"],
    "repay_delinquent": ["BBRR2_FED_UGCOMP_DLNQ"],
    "repay_forbearance": ["BBRR2_FED_UGCOMP_FBR"],
    "repay_deferment": ["BBRR2_FED_UGCOMP_DFR"],
    "repay_not_progressing": ["BBRR2_FED_UGCOMP_NOPROG"],
    "repay_progressing": ["BBRR2_FED_UGCOMP_MAKEPROG"],
    "repay_paid_in_full": ["BBRR2_FED_UGCOMP_PAIDINFULL"],
    # Share of all borrowers whose balance is declining three years in (a different, older
    # measure ED also publishes; kept for context, not mixed with the status shares above).
    "repay_3yr_declining": ["RPY_3YR_RT"],
}
INST_REQUIRED = ["unitid", "earnings_threshold_state", "earnings_threshold_national"]

# Scorecard suppresses small-cohort values. These sentinels must become NULL and
# be surfaced as "insufficient data", never imputed.
SUPPRESSION_SENTINELS = {"PrivacySuppressed", "PS", "NULL", "", "NA"}
