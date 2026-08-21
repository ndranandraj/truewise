"""Stage 0.3 acceptance gate: every final palette pairing meets WCAG contrast, computed not asserted.

This recomputes the WCAG 2.x contrast ratio for every text token on every surface it is permitted on
(needs 4.5), and every non-text token against its adjacent surfaces (needs 3.0). A future palette
tweak that drops a colour below its threshold fails the build here. This is the test 0.3 section 7
promised, and it is what stops a sub-AA colour shipping the way the design-workbook palette nearly did.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTE = json.loads((ROOT / "design" / "palette-final.json").read_text())


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    ch = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def test_every_text_token_meets_aa_on_each_permitted_surface():
    surfaces = PALETTE["surfaces"]
    failures = []
    for name, spec in PALETTE["text"].items():
        for surf in spec["on"]:
            ratio = contrast(spec["value"], surfaces[surf])
            if ratio < spec["min"]:
                failures.append(f"{name} {spec['value']} on {surf}: {ratio} < {spec['min']}")
    assert not failures, "sub-AA text pairings:\n  " + "\n  ".join(failures)


def test_non_text_tokens_meet_3to1():
    surfaces = PALETTE["surfaces"]
    failures = []
    for name, spec in PALETTE["non_text"].items():
        for surf in spec["on"]:
            ratio = contrast(spec["value"], surfaces[surf])
            if ratio < spec["min"]:
                failures.append(f"{name} {spec['value']} on {surf}: {ratio} < {spec['min']}")
    assert not failures, "sub-3:1 non-text pairings:\n  " + "\n  ".join(failures)


def test_text_muted_is_the_lightest_neutral_text():
    """text-muted is the floor for NEUTRAL body text: no plain grey may be lighter than it (that is
    how the old sub-AA #8b95a7 crept in). Status colours (good/bad/caution) and brand text are not
    neutrals; they carry meaning and are validated against their own surfaces above, so a status hue
    that happens to be marginally lighter in luminance is allowed."""
    neutrals = {"text", "text-secondary", "text-muted"}
    muted = PALETTE["text"]["text-muted"]
    muted_lum = _luminance(muted["value"])
    for name in neutrals - {"text-muted"}:
        assert _luminance(PALETTE["text"][name]["value"]) <= muted_lum, (
            f"neutral text {name} is lighter than text-muted; muted must be the lightest neutral"
        )


def test_focus_ring_works_on_a_brand_filled_control():
    """The focus ring on a brand-deep or brand-filled button must reach 3:1, which is only true with
    the light on-dark ring (a brand ring directly on the fill is 2.37). Guards 0.3 section 4."""
    ring = PALETTE["non_text"]["focus-ring-on-dark"]["value"]
    assert contrast(ring, PALETTE["surfaces"]["brand"]) >= 3.0
    assert contrast(ring, PALETTE["surfaces"]["brand-strong"]) >= 3.0
