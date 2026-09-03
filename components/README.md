# Truewise components

Shared UI components, authored **in isolation** so each is built once and passes accessibility
before it reaches a production page.

Two of these files ARE deployed. `pipeline/build_components.py` copies `components.css` and the
four scripts into `site/` at build time (as `/components.css` and `/components/*.js`), because the
canonical college profile references them at site-root paths. Source of truth stays here; the
copies under `site/` are generated, and `python -m pipeline.build_components --check` fails if they
are stale. The fixtures and `tokens-final.css` are NOT deployed: they are a development harness,
and every fixture carries `noindex`.

## Why isolated

The redesign consolidates two profile systems and four searches. Building the reusable pieces here,
against the final palette, means each is built once and passes accessibility before it touches a
production page. See `../truewise-stage0.4-components.md` for the full inventory and the pass/fail
criteria, and `../truewise-stage0.3-palette.md` for the colour system.

## Files

- `tokens-final.css` — **generated** by `make tokens` from `design/tokens.json`; do not edit it by
  hand. It is the same `:root` the site serves, so a component reviewed in a fixture looks like the
  same component in production. It used to be hand-maintained and drifted: through the Release 3
  forest rebrand it still declared the old blue brand, status and surface colours, so the fixtures
  showed one palette while the site served another. The drift test claimed to check every colour and
  actually spot-checked four. Both are fixed: the file is generated, and `tests/test_components.py`
  now checks every declared colour against `design/palette-final.json`.
- `components.css` — component styles, referencing tokens only: no raw hex, no ad-hoc radii (they
  use `--r-sm`/`--r-md`/`--r-lg`/`--r-pill`), and no off-palette `rgba()`. Tinted backgrounds name
  `--sand`; `--surface` is the white surface the decision record defines.
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
- B3/B4/B6/B7/B8/B9/B11/B12/B13/B14 (`ui.js`): built, smoke green. Empty state with routes, state
  chips (aria-pressed + announced narrowing), coverage note, source note, status pill (text not
  colour alone), filters (announced count), disclosure (Escape collapses), loading skeleton (aria-
  busy), error (role=alert), suppressed value.
- B2 result row + B15 sticky subnav: covered inside B1 (the option row) and shipped live in Stage 1.5
  (the subnav offset); no separate fixture needed.
- B10 affordability calculator: deferred to Stage 4, where it is built directly on the canonical
  profile against real net-price data rather than mocked in a fixture.
- Canonical profile progressive enhancement (`profile.js`, Stage 4.2): upgrades a server-rendered
  static program table into the interactive `ProgramTable` and loads the remaining programs on demand
  via "Show all N" (table.js `onMore`/`remaining`). No-JS-safe: the static table stands alone.
  `tests/profile_smoke.js` drives the full load-and-sort flow, 10/10.

## Independent test report fixes (2026-08-21)

A rendered-browser test report (axe + three engines) found issues the jsdom smokes could not. All
resolved:

- P0.1 mobile table clipping: the component now sets its own `box-sizing: border-box` (it no longer
  relies on the host's global reset), and the caption is a full-width block at the mobile breakpoint.
- P0.2 sort dropped keyboard focus: the sort handler restores focus to the active sort button after
  re-render.
- P0.3 no-results link nested in a disabled listbox option: the empty state now renders in a sibling
  region outside the listbox.
- P0.4 the real college provider discarded the computed match reason: `why` (alias / city / close
  spelling) is now carried through; gold set asserts it.
- P0.5 empty-state links measured 4.31:1 on the surface: they use `--brand-strong`; a `--text-on-brand`
  token replaces the raw white chip text, and the raw-hex guard now catches 3/4/6/8-digit forms.
- P1: fixtures gained a `<main>` landmark; the K-12 search + state-chip + provider flow is composed in
  the search fixture via a new `providerOpts` hook.

A second verification confirmed all five P0 fixes and found one new runtime blocker: the composed
K-12 fixture constructed the chips via `TWSearchUI.StateChips`, but `StateChips` is exported by
`TWUI` (ui.js). Fixed to `TWUI.StateChips`. Added `tests/integration_smoke.js`, which boots the same
three modules the fixture loads and drives the full search-then-narrow flow (this is what the earlier
tests lacked: they exercised components in isolation but never the composed flow), plus a structural
guard on the namespace. The gold-set summary now counts assertions, not query cases (was 42/39).

Still requires a real VoiceOver pass to close the gate: confirm the search, no-results, mobile table,
state-chip, filter, and disclosure flows, and that the mobile `::before` labels are not announced
redundantly with the column headers.
