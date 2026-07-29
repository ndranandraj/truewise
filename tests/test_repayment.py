"""Test parsing of the repayment fields, where ED publishes censored bounds.

The failure mode this guards against is presenting "at most 5%" as if it were exactly 5%,
or throwing the bound away entirely. Both misrepresent what the government published.
"""

from __future__ import annotations

from pipeline.repayment import format_rate, parse_rate


def test_exact_values_parse_as_exact():
    assert parse_rate("0.02") == (0.02, False)
    assert parse_rate(" 0.7243295 ") == (0.7243295, False)
    assert parse_rate("0") == (0.0, False)


def test_censored_bounds_keep_the_value_and_flag_it():
    assert parse_rate("<=0.05") == (0.05, True)
    assert parse_rate("<=0.01") == (0.01, True)
    assert parse_rate("<0.2") == (0.2, True)
    assert parse_rate(" <= 0.05 ") == (0.05, True)


def test_suppressed_and_junk_become_null_never_guessed():
    for token in ("PS", "PrivacySuppressed", "NULL", "NA", "", None, "not a number"):
        assert parse_rate(token) == (None, False), token


def test_missing_values_never_leak_through_as_numbers():
    # pandas represents an empty cell as float NaN; that is missing data, not a rate.
    # Caught in a cross-check against ED's raw file, where NaN was passing through as a float.
    assert parse_rate(float("nan")) == (None, False)
    assert parse_rate("NaN") == (None, False)
    assert parse_rate("nan") == (None, False)
    assert parse_rate("None") == (None, False)


def test_formatting_never_overstates_precision():
    assert format_rate(0.02, False) == "2%"
    assert format_rate(0.02, True) == "2% or less"
    assert format_rate(None, False) == "not reported"
    # A bound must never render as a bare percentage.
    assert "or less" in format_rate(0.05, True)
