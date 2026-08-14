"""Unit tests for the per-page social share card renderer.

These guard the two things a social scraper cares about: the file is a real PNG at the exact
1200x630 the Open Graph spec wants, and the generator degrades safely on long text rather than
raising. Content correctness (which number lands on which card) is covered by the page-builder
tests that call card() with real data.
"""

from __future__ import annotations

import struct

import pipeline.og_images as og


def _png_size(path) -> tuple[int, int]:
    """Read width/height straight from the PNG IHDR chunk, no image library needed."""
    with open(path, "rb") as fh:
        header = fh.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    w, h = struct.unpack(">II", header[16:24])
    return w, h


def test_card_writes_1200x630_png(tmp_path):
    out = tmp_path / "nested" / "card.png"
    og.card(out, "College major", "Nursing", big="$85,357", sub="Median a few years after.")
    assert out.exists(), "card() did not create the file"
    assert _png_size(out) == (1200, 630)


def test_card_survives_overlong_text(tmp_path):
    out = tmp_path / "card.png"
    og.card(
        out,
        "eyebrow " * 20,
        "A headline so long it must wrap and then truncate " * 6,
        big="1 in 11",
        big_color=og.BAD,
        sub="A subtitle that also runs well past two lines to force the wrap path. " * 6,
    )
    assert _png_size(out) == (1200, 630)


def test_card_optional_fields(tmp_path):
    # No big stat, no subtitle: eyebrow + headline only must still render.
    out = tmp_path / "card.png"
    og.card(out, "Findings", "A plain card")
    assert _png_size(out) == (1200, 630)
