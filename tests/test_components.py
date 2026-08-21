"""Structural guards for the Stage 3 component fixtures.

These run in the Python suite (CI) even though the behavioural check (components_smoke.js) is a manual
jsdom smoke. They assert the fixtures stay isolated from production, the fixture palette matches the
contrast-validated one, and component CSS references tokens rather than raw hex.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "components"


def test_tokens_final_matches_the_validated_palette():
    """Every colour in components/tokens-final.css must equal its value in palette-final.json, so the
    fixtures render the exact palette the contrast gate checks."""
    palette = json.loads((ROOT / "design" / "palette-final.json").read_text())
    values = {}
    values.update({k: v["value"] for k, v in palette["text"].items()})
    values.update({k: v["value"] for k, v in palette["non_text"].items()})
    values.update(palette["surfaces"])
    css = (COMPONENTS / "tokens-final.css").read_text()
    declared = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))

    # Spot the load-bearing tokens explicitly (names differ slightly from palette keys by design).
    for token, expected in [
        ("text-muted", values["text-muted"]),
        ("text-on-dark-muted", values["text-on-dark-muted"]),
        ("focus-ring-on-dark", values["focus-ring-on-dark"]),
        ("brand-strong", palette["surfaces"]["brand-strong"]),
    ]:
        assert declared.get(token) == expected, (
            f"{token} in tokens-final.css != palette ({expected})"
        )


def test_component_css_uses_tokens_not_raw_palette_hex():
    """components.css styles must reference var(--token); a raw palette hex would dodge the contrast
    gate. Shadows/overlays using rgba() are allowed."""
    css = (COMPONENTS / "components.css").read_text()
    hexes = re.findall(r"#[0-9a-fA-F]{6}", css)
    assert not hexes, f"components.css should use tokens, found raw hex: {set(hexes)}"


def test_fixtures_are_noindex_and_out_of_the_site_tree():
    """Fixtures must never be crawlable or deployed: they live in components/, not site/, and carry a
    noindex robots tag."""
    assert not (ROOT / "site" / "_fixtures").exists(), "fixtures must not live under site/"
    for html in (COMPONENTS / "fixtures").glob("*.html"):
        assert 'name="robots" content="noindex"' in html.read_text(), f"{html.name} missing noindex"


def test_search_shell_implements_the_combobox_contract():
    """Guard the ARIA combobox wiring so a refactor cannot quietly drop it (0.4 B1 pass/fail)."""
    js = (COMPONENTS / "search.js").read_text()
    for needed in (
        'role="combobox"',
        'role="listbox"',
        'role="option"',
        "aria-activedescendant",
        'aria-live="polite"',
        "aria-expanded",
    ):
        assert needed in js, f"search shell missing {needed}"


def test_program_table_keeps_its_accessibility_contract():
    """Guard the B5 table semantics: real table headers, sortable aria-sort, per-cell mobile labels,
    and suppressed cells that say insufficient data rather than 0."""
    js = (COMPONENTS / "table.js").read_text()
    for needed in (
        'scope="col"',
        'scope="row"',
        "aria-sort",
        "data-label",
        "insufficient data",
        'aria-hidden="true"',  # the premium bar is decorative
    ):
        assert needed in js, f"program table missing {needed}"


def test_small_components_carry_their_contracts():
    """Guard the B3/B4/B8/B9/B11/B12/B13 wiring in ui.js: status carries text, chips/toggle expose
    state, loading is announced, error is an alert, suppressed says insufficient data."""
    js = (COMPONENTS / "ui.js").read_text()
    for needed in (
        "clears the bar",  # B8 status is text, not colour alone
        "falls short",
        "insufficient data",  # B14 suppressed + B8 insufficient
        "aria-pressed",  # B4 chips
        'aria-busy="true"',  # B12 loading
        'role="alert"',  # B13 error
        "Escape",  # B11 disclosure collapses
    ):
        assert needed in js, f"ui.js missing {needed}"
