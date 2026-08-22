"""Guard the Stage 4.1 canonical-profile delivery model (static core + progressive tail).

The pilot generator decides what ships statically vs in the tail. These assert the threshold logic
and the honesty rules on the static HTML, so the delivery model cannot silently regress before the
Stage 4.3 build-out adopts it at scale.
"""

from __future__ import annotations

import json

from pipeline.build_profile_pilot import DEFAULT_THRESHOLD, build_profile


def _rows(n_decided, n_insuf):
    rows = [
        {
            "program": f"Program {i}",
            "credential": "Bachelor's Degree",
            "earnings": 50000 + i,
            "premium": 10000 + i,
            "verdict": "pass",
            "debt": 20000,
            "payback": 1.2,
            "completers": 100 - i,
        }
        for i in range(n_decided)
    ]
    rows += [
        {
            "program": f"Suppressed {i}",
            "credential": "Certificate",
            "earnings": None,
            "premium": None,
            "verdict": "insufficient",
            "debt": None,
            "payback": None,
            "completers": 5,
        }
        for i in range(n_insuf)
    ]
    return rows


def test_threshold_default_is_150():
    """Pilot raised the static threshold from 60 to 150 (transfer is gzip-bound, DOM is the real
    constraint). Guard the decided value so a silent revert is caught."""
    assert DEFAULT_THRESHOLD == 150


def test_small_school_is_fully_static_no_tail():
    meta = {"name": "Tiny College", "state": "CA", "control": "Private"}
    html, tail = build_profile(meta, _rows(2, 1), DEFAULT_THRESHOLD)
    assert tail is None, "a 3-program school needs no tail"
    assert html.count('<tr class="tw-tr') == 3
    # No tail: no progressive hooks, but the enhancement contract (island) is still present.
    assert 'data-remaining="0"' not in html and "data-tail" not in html
    assert 'class="tw-profile-data"' in html


def test_large_school_splits_at_threshold():
    meta = {"name": "Big University", "state": "PA", "control": "Public"}
    rows = _rows(200, 289)  # 489 total, like Penn State
    html, tail = build_profile(meta, rows, DEFAULT_THRESHOLD)
    assert html.count('<tr class="tw-tr') == DEFAULT_THRESHOLD, (
        "static core must carry exactly the threshold"
    )
    # The "Show all N" control is rendered client-side; the static page carries the progressive hooks.
    assert 'data-tail="programs-tail.json"' in html
    assert f'data-remaining="{489 - DEFAULT_THRESHOLD}"' in html
    tail_programs = json.loads(tail)["programs"]
    assert len(tail_programs) == 489 - DEFAULT_THRESHOLD
    # The JSON island carries the static rows as data for the enhancer.
    import re

    island = json.loads(re.search(r'tw-profile-data">(.*?)</script>', html, re.S).group(1))
    assert len(island["rows"]) == DEFAULT_THRESHOLD
    assert island["coverage"] == {"measured": 200, "total": 489}


def test_coverage_and_suppression_are_honest():
    meta = {"name": "Mostly Suppressed CC", "state": "CA", "control": "Public"}
    rows = _rows(1, 106)  # 107 total, 106 insufficient (Irvine Valley shape)
    html, _ = build_profile(meta, rows, DEFAULT_THRESHOLD)
    assert "<b>1 of 107</b> programs measured" in html
    assert "insufficient data" in html
    # A suppressed row must never render a bare 0 or an empty cell.
    assert ">0<" not in html and "$0<" not in html


def test_static_table_has_real_headers_and_labels():
    meta = {"name": "X", "state": "TX", "control": "Public"}
    html, _ = build_profile(meta, _rows(3, 0), DEFAULT_THRESHOLD)
    assert 'scope="col"' in html and 'scope="row"' in html
    assert 'data-label="Median earnings"' in html  # mobile labels for the stacked layout
    assert "Recent completers" in html  # not "graduates"
