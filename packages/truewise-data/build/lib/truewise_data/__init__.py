"""truewise-data — clean US college program value data in two lines of Python.

    import truewise_data as tw
    df = tw.load_value_check()   # one row per school x field of study x credential

Data derives from the U.S. Department of Education's College Scorecard
(Field-of-Study + Institution files), cleaned and joined so the federal
earnings-premium comparison is ready to use. See https://truewise.dev.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

__version__ = "0.1.0"

__all__ = ["load_value_check", "load_summary", "meta", "DATA_VERSION", "__version__"]


def _data_file(name: str):
    return resources.files(__name__).joinpath("data", name)


@lru_cache(maxsize=1)
def meta() -> dict[str, Any]:
    """Dataset provenance: Scorecard release, generation date, row count, license."""
    with _data_file("meta.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_value_check(decided_only: bool = False):
    """Return the program-level Value Check table as a pandas DataFrame.

    One row per institution x 4-digit CIP x credential level. Key columns:
      earnings                     median earnings 4 years after completion (USD)
      earnings_threshold_state     typical HS-grad earnings in the school's state (USD)
      earnings_premium_state       earnings - threshold (USD; negative = below)
      value_flag                   passes_earnings_premium | fails_earnings_premium | insufficient_data
      share_earning_above_hs_grad  fraction of graduates out-earning a HS grad
      debt_median, debt_to_earnings_ratio

    Suppressed (small-cohort) values are NULL, never imputed. Pass decided_only=True
    to drop rows with insufficient data.
    """
    import pandas as pd

    with resources.as_file(_data_file("value_check.parquet")) as path:
        df = pd.read_parquet(path)
    if decided_only:
        df = df[df["value_flag"] != "insufficient_data"].reset_index(drop=True)
    return df


def load_summary() -> dict[str, Any]:
    """National + state Value Check summary (fail rates, worst fields, by-state counts)."""
    with _data_file("summary.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


DATA_VERSION: str = meta().get("scorecard_release", "unknown")
