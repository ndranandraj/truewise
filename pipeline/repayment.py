"""Parse the College Scorecard's loan-repayment fields, including censored bounds.

The repayment columns do not behave like the earnings columns. Alongside exact rates and the
usual suppression tokens, ED publishes *censored bounds* such as "<=0.05", meaning the true
rate is at most 5%. Dropping those would throw away real information (they tell you the rate
is low); treating them as exact would overstate precision.

So each rate becomes two values: the number, and a flag saying whether that number is an upper
bound rather than an exact figure. Bounded values are shown as "5% or less" and must never be
averaged or ranked as if they were exact.
"""

from __future__ import annotations

# Tokens that mean "no value", as opposed to a censored bound.
SUPPRESSED = {"PS", "PrivacySuppressed", "NULL", "NA", "", None}


def parse_rate(raw) -> tuple[float | None, bool]:
    """Return (value, is_upper_bound) for one published repayment figure.

    >>> parse_rate("0.02")
    (0.02, False)
    >>> parse_rate("<=0.05")
    (0.05, True)
    >>> parse_rate("PS")
    (None, False)
    """
    if raw is None:
        return None, False
    s = str(raw).strip()
    if s in SUPPRESSED:
        return None, False
    bounded = False
    if s.startswith("<="):
        bounded = True
        s = s[2:].strip()
    elif s.startswith("<"):
        bounded = True
        s = s[1:].strip()
    try:
        return float(s), bounded
    except ValueError:
        return None, False


def format_rate(value: float | None, is_bound: bool) -> str:
    """Human phrasing that never implies more precision than ED published."""
    if value is None:
        return "not reported"
    pct = round(value * 100)
    return f"{pct}% or less" if is_bound else f"{pct}%"
