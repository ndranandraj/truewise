"""Tests for the truewise-data package public API (run against the installed package)."""

from __future__ import annotations

import truewise_data as tw


def test_load_value_check_shape():
    df = tw.load_value_check()
    assert len(df) > 50_000
    for col in ("unitid", "earnings", "earnings_threshold_state", "value_flag"):
        assert col in df.columns


def test_flags_are_expected_values():
    df = tw.load_value_check()
    assert set(df["value_flag"].unique()) <= {
        "passes_earnings_premium",
        "fails_earnings_premium",
        "insufficient_data",
    }


def test_decided_only_drops_insufficient():
    df = tw.load_value_check(decided_only=True)
    assert (df["value_flag"] != "insufficient_data").all()


def test_no_imputation_suppressed_is_null():
    # Insufficient-data rows must not carry a fabricated earnings value.
    df = tw.load_value_check()
    insuff = df[df["value_flag"] == "insufficient_data"]
    # These rows lack a usable earnings/threshold pairing.
    assert insuff["earnings"].isna().sum() + (
        insuff["earnings_threshold_state"].isna().sum()
    ) >= len(insuff)


def test_summary_and_meta():
    s = tw.load_summary()
    assert s["programs_fail_earnings_premium"] > 0
    m = tw.meta()
    assert m["license"] == "CC-BY-4.0"
    assert tw.DATA_VERSION == m["scorecard_release"]
