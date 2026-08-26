# Forest design system: approved reference

Snapshot of the Claude Design "Truewise Design Audit & System" templates (2026-08-14), committed so the
Release 3 forest rebrand is reproducible without the gitignored `design-audit-2026-08/`. These are the
APPROVED layout, composition, density, and responsive behaviour; the authoritative token VALUES and
usage rules (including the three contrast corrections) live in `truewise-stage0.3b-palette-forest.md`.

- `tokens.css` / `site.css`: the drop-in design-system CSS (base + components).
- `index.html`: the homepage composition.
- `program-table.html`: the scannable program table.

Note: these still carry the pre-correction values and the `@import` font load. B1 applies the corrected
tokens and non-blocking font loading per the decision record; do not copy `tokens.css` verbatim.
