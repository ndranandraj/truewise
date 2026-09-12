# Forest design system: ARCHIVAL reference (not implementation-ready)

Snapshot of the Claude Design "Truewise Design Audit & System" templates (2026-08-14), committed so the
Release 3 forest rebrand preserves the source DIRECTION (layout, composition, density, responsive
intent) even if the gitignored `design-audit-2026-08/` is lost.

This is NOT a drop-in stylesheet and NOT a final implementation target. Where these files disagree with
`truewise-stage0.3b-palette-forest.md` or the existing accessible production components, THE RECORD AND
THE PRODUCTION COMPONENTS WIN. The authoritative token values, usage rules, and the three contrast
corrections live in the decision record.

## Override manifest (rejected reference rules, do NOT copy)

- Fonts: `tokens.css` loads Sora and uses a render-blocking `@import`. REJECTED. B3 uses Source Serif +
  IBM Plex Mono only, on the system UI stack, loaded non-blocking (self-hosted WOFF2).
- Link hover uses `--short` (clay). REJECTED. Clay is earnings-shortfall only; link hover is
  `--brand-deep`.
- Pills use `--rule` (1.23:1) as their control boundary and `brand-300` (1.80:1 on paper) on hover.
  REJECTED. Controls use `--control-border` (>=3:1); see the record's interaction section.
- Corrected colours: `tokens.css` still has `--ink-400 #86918B`, `--caution #B4751A`, and the
  focus-on-dark defect. Use the corrected values (`#646F6A`, `#8A6412`, focus-on-dark `--paper`).
- New tokens absent: `--control-border*`, `--danger`, `--r-pill`, the 20/40 spacing steps. Add per the
  record.
- Off-scale sizes present (11, 14, 17, 22, 68, 72, 80, 88px) and 11px chip/table text. Tokenise to the
  role scale or drop; chart/label text stays >=12px.
- `.fig` scope: the record narrows mono to data figures, not all prose currency.
- Mobile: `index.html` overflows at 390px (header CTA, search button, example header, provenance).
  NOT responsive-approved; the mobile fixes are listed in the record's scales section.
- Homepage finding copy: `index.html` omits the one-year fallback, the strict four-year-only rate, and
  the "How we count" disclosure, and it carries an internal "copy verbatim" instruction. REJECTED.
  Preserve the COMPLETE production mixed-window disclosure (shipped in Release 2) and generate its
  figures from the current data summary, not from this file.
- `program-table.html`: VISUAL reference only. Its mobile CSS hides headers without stacked labels and
  its sort/announce script is a commented-out stub. B-work restyles the tested `tw-table` /
  `components/table.js` / `profile.js`; it does not replace their semantics, announcements, sort
  contract, or progressive enhancement.

## Not yet a complete visual baseline

The homepage chart area is empty (the generated SVG is absent), the program table has no
generator-fed data, and rendered screenshots are not captured yet. B7a adds corrected fixtures and
screenshots to `design/reference/shots/`; only then is the reference package "approved".

## Files
- `tokens.css` / `site.css`: archival design-system CSS (base + components).
- `index.html`: archival homepage composition.
- `program-table.html`: archival scannable program table (visual only).
