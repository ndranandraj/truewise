"""A city ED reports in capitals is shown in ordinary case, and only when that is safe."""

from __future__ import annotations

import pytest

from pipeline.build_site import display_city


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("CANAL WINCHESTER", "Canal Winchester"),
        ("PERU", "Peru"),
        # Already in ordinary case: untouched.
        ("Waco", "Waco"),
        ("St. Louis", "St. Louis"),
        # Case that cannot be derived from the letters stays as ED published it.
        ("MCALLEN", "MCALLEN"),
        ("O'FALLON", "O'FALLON"),
        ("ST. LOUIS", "ST. LOUIS"),
        (None, None),
        ("", ""),
    ],
)
def test_a_city_in_capitals_is_shown_in_ordinary_case(raw, want):
    assert display_city(raw) == want
