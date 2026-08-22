"""Guard the single source of truth for design tokens (Stage 2).

design/tokens.json generates the CSS custom properties in styles.css and the Python colour
constants in tokens_gen.py. These tests fail if either generated file drifts from the source, or
if a generator reintroduces a hand-copied palette hex, which is the bug that once shipped ~5,300 OG
cards a different blue from the site.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline import build_tokens, tokens_gen

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"


def test_generated_files_are_current():
    """styles.css :root and tokens_gen.py must equal what tokens.json generates right now.
    If this fails, run `make tokens`."""
    assert build_tokens.build(check=True) == 0, "generated token files are stale; run `make tokens`"


def test_semantic_bridge_covers_every_component_token():
    """The Stage 3 components reference semantic token names (--text, --paper, --brand-strong, ...).
    Every one must be defined in the live styles.css, or a component renders with an undefined colour
    on a real page. This is the Stage 4.3 bridge that lets components go live before the palette
    cutover."""
    styles = (ROOT / "site" / "styles.css").read_text()
    live = set(re.findall(r"^  --([a-z0-9-]+):", styles, re.M))
    for css in ("components.css",):
        used = set(re.findall(r"var\(--([a-z0-9-]+)\)", (ROOT / "components" / css).read_text()))
        missing = used - live
        assert not missing, f"{css} uses tokens not defined in live styles.css: {missing}"


def test_bridge_holds_current_values_not_final():
    """The bridge deliberately aliases to the CURRENT palette so it is a no-visual-change change; the
    final 0.3 values land at the Stage 5 cutover. Guard that --text-muted is still the current value
    (a premature swap to the final #67717f would be an unplanned live restyle)."""
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text())
    sem = tokens["semantic"]
    assert sem["text-muted"] == "#6b7688", (
        "bridge must stay on the current muted value until Stage 5"
    )
    assert sem["text"] == tokens["color"]["ink"]["value"]
    assert sem["paper"] == tokens["color"]["bg"]["value"]
    assert sem["brand-strong"] == tokens["color"]["brand-deep"]["value"]


def test_css_and_python_share_identical_values():
    """Every shared colour must have the same value in the CSS block and the Python constants."""
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text())
    css = build_tokens.render_css_root(tokens)
    for name, spec in tokens["color"].items():
        if not spec.get("shared"):
            continue
        py_val = getattr(tokens_gen, name.upper().replace("-", "_"))
        assert py_val == spec["value"], f"{name}: python {py_val} != source {spec['value']}"
        assert f"--{name}: {spec['value']};" in css, f"{name} missing or wrong in CSS block"


def test_generators_carry_no_hand_copied_palette_hex():
    """The three generators that render colour must pull every palette value from tokens_gen, never
    a literal hex. A new raw palette colour here is how drift starts."""
    palette = {v.lower() for v in tokens_gen.TOKENS.values()}
    for rel in ("og_images.py", "build_home_chart.py", "build_majors_pages.py"):
        src = (PIPELINE / rel).read_text()
        found = {m.group(0).lower() for m in re.finditer(r"#[0-9a-fA-F]{6}", src)}
        leaked = found & palette
        assert not leaked, f"{rel} hard-codes palette hex {leaked}; import from tokens_gen instead"
