# Truewise components (Stage 3)

Shared UI components, built and validated **in isolation** before any live route adopts them
(that adoption is Stage 5). Nothing here is deployed: the folder sits outside `site/`, and every
fixture carries `noindex`.

## Why isolated

The redesign consolidates two profile systems and four searches. Building the reusable pieces here,
against the final palette, means each is built once and passes accessibility before it touches a
production page. See `../truewise-stage0.4-components.md` for the full inventory and the pass/fail
criteria, and `../truewise-stage0.3-palette.md` for the colour system.

## Files

- `tokens-final.css` — the Stage 0.3 final palette as CSS custom properties. Fixture-only; production
  still serves the current values from `site/styles.css` until Stage 5. Values mirror
  `design/palette-final.json` (enforced by `tests/test_components.py`).
- `components.css` — component styles, referencing tokens only (no raw hex).
- `search.js` — the accessible combobox shell (B1), wrapping the domain providers in
  `site/assets/college-search.js`.
- `fixtures/` — one standalone page per component for manual and automated checks.

## Validating

- Behavioural: `make test-components` (jsdom smoke, `tests/components_smoke.js`; needs `npm install
  jsdom`). Covers ARIA state, keyboard nav, selection, the live-region count, and Escape.
- Structural + palette sync + contrast: the Python suite (`pytest tests/test_components.py
  tests/test_contrast.py`), which runs in CI.
- Manual: open `fixtures/search.html` in a browser, run an axe scan, and do a keyboard and
  screen-reader pass. Record the result before the component leaves Stage 3.

## Status

- B1 search combobox shell + college/K-12 providers: built, smoke green.
- B5 program / comparison table (`table.js`): built, smoke green. Coverage first, sortable columns
  with aria-sort, suppressed rows kept visible and sunk to the bottom, decorative premium bar, and a
  mobile layout that keeps every value's column label.
- B2-B4, B6-B15 (results row, empty state, state chips, coverage note, source note, status pill,
  filters, calculator, disclosure, loading/error/suppressed, sticky subnav): pending.
