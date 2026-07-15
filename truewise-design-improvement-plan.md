# Truewise.dev Design Improvement Plan

Based on a design review of the live site (homepage, /value-check/ search page, and school profile page) on 2026-07-15. Items are grouped into phases by impact. Each item has a "Done when" check so progress is verifiable.

---

## Phase 1: School profile page (highest impact, core product)

### 1.1 Replace prose program cards with a scannable comparison view
The program list is 60+ near-identical cards, each repeating the full sentence "Graduates typically earn $X ... versus $34,809 for a typical high-school graduate in this state, a $Y premium." The repetition buries the numbers.

- State the baseline once above the list, e.g. "Texas high-school-grad baseline: $34,809 (median earnings)".
- Convert each program card to a compact row or table layout with columns: Program, Degree level, Median earnings, Premium vs HS grad (colored, signed), Median debt, Debt-to-earnings ratio, Graduate count.
- Keep the pass/fall-short status as a small colored chip or a colored premium value, not a full badge plus a full sentence.
- Optionally keep an expandable row for the plain-language sentence for users who want it.

Done when: a user can scan all programs and compare earnings and premiums without reading repeated sentences.

### 1.2 Add sorting and search within the program list
- Sort controls: by premium (default), earnings, debt, graduate count, alphabetical.
- A small filter/search input to find a program by name (e.g. "Nursing") without scrolling.

Done when: sorting and in-list search work with the existing All / Falls short / Passes filter pills.

### 1.3 Add a small inline visualization per program
The site currently has zero data visualizations. Add a tiny horizontal bar per program row showing earnings vs the state HS baseline (baseline as a reference line or second bar). Keep it subtle and consistent with the minimal aesthetic.

Done when: each program row communicates the premium visually at a glance.

### 1.4 Flag mixed measurement timeframes
Some programs show earnings "1 year after completing" and others "4 years after completing" with no visual distinction. This silently breaks comparability.

- Add a visible tag such as "1-yr data" on programs that only have the shorter window.
- Mention the difference in the "How to read this" box.

Done when: a user comparing two programs can immediately see when the timeframes differ.

### 1.5 Fix badge placement inconsistency
The status badge sits right of the title on short names but wraps below the title on long names (e.g. Romance Languages vs Biology). Pin the badge to one consistent position regardless of title length.

Done when: badge position is identical on every card/row at all viewport widths.

### 1.6 Strip trailing periods from program names
CIP titles render with trailing periods ("Biology, General.", "Accounting and Related Services."). Strip them at the data-cleaning or display layer.

Done when: no program name ends with a period.

### 1.7 Promote "not enough data" to a filter pill
Currently a paragraph plus a "Why?" disclosure. Make it a fourth pill: All (64) / Falls short (2) / Passes (62) / Not enough data (119). This also answers "where is my program?" directly. Keep the "Why?" explanation inside that view.

Done when: suppressed programs are browsable behind a pill, listed by name with a "not enough data" note.

### 1.8 Affordability: default-select an income chip
"Select your family income above." reads like an error state even though an all-families average is displayed. Add an "All families" chip, selected by default, so the component always looks intentional.

Done when: a chip is always active and the instruction line is removed or reworded.

### 1.9 Improve long-page navigation
- Make the live module cards at the top (Value Check, Affordability) anchor-scroll to their sections.
- Add a "back to top" affordance or a slim sticky section nav on long profiles.

Done when: users can jump between summary, Value Check, and Affordability without manual scrolling.

---

## Phase 2: Homepage

### 2.1 Move the primary CTA into the hero
"Look up a college" sits below the fold behind a paragraph, a status pill, and a callout. Place the CTA (ideally an actual search box, reusing the Value Check search component) directly in the hero so users can act immediately.

Done when: a visitor can start a college search without scrolling.

### 2.2 Give the headline finding a visual treatment
The "1 in 11 college programs (9%)" finding is the strongest asset on the page but renders as a bolded sentence in a gray box. Options: a large stat number treatment, a simple 11-dot graphic with one highlighted, or a small bar chart including the 86% cosmetology figure.

Done when: the finding reads as a visual centerpiece, not body text.

### 2.3 Differentiate live vs coming-soon modules
The Value Check (live) card looks nearly identical to five coming-soon cards, so the page feels mostly placeholder.

- Make Value Check visually dominant: larger card, stronger border or accent, prominent CTA.
- Collapse the five coming-soon modules into a muted compact grid or a simple list with "coming soon" labels.

Done when: the live product is unmistakably the focus of the "What's coming" section.

### 2.4 Copy and typography polish
- Fix the stray space in the status pill: "First module: Value Check ." should read "First module: Value Check."
- Cap body text measure at roughly 65 to 75 characters per line; paragraphs currently run ~850px wide.

Done when: no stray spacing around the pill link and comfortable line lengths at all widths.

---

## Phase 3: Global / site-wide

### 3.1 Fix the translucent sticky header
Content visibly smears behind the logo and nav while scrolling because the header background is semi-transparent without blur. Use an opaque background, or add backdrop-filter blur with a mostly opaque fill, plus a subtle bottom border or shadow when scrolled.

Done when: no page content shows through the header during scroll.

### 3.2 Keep the primary CTA in the nav at every breakpoint
At tablet widths the nav drops "Find a college" (the primary action) while keeping secondary links. Keep "Find a college" visible at all breakpoints, styled as a small button if space is tight; collapse secondary links first (or into a menu).

Done when: "Find a college" is reachable from the header at every viewport width.

### 3.3 Make navigation consistent across pages
Home shows four nav items; app pages show only "Methodology". Adopt one persistent header: logo, Find a college, Data, Methodology (secondary links can collapse on small screens).

Done when: the header is identical (or predictably reduced) across home, search, and profile pages.

### 3.4 Investigate blank rendering on fast scroll
Jumping to the bottom of a long profile page rendered blank frames before content painted. Likely a content-visibility or lazy-render placeholder issue on the long program list. The table conversion in 1.1 may fix this; verify after.

Done when: End-key or fast scroll to the bottom paints content without blank frames.

### 3.5 Small polish items
- Use tabular numerals (font-variant-numeric: tabular-nums) for all dollar figures so columns align.
- Add an Open Graph image; the social card is currently text-only (twitter:card is "summary" with no image).
- Verify WCAG AA contrast on light gray text ("not enough data" counts, footer text).
- Add a favicon if not already present.

Done when: each sub-item is checked and applied.

---

## What is already working (do not regress)

- Honest handling of suppressed data ("insufficient data", never imputed).
- Plain-language framing ("students like you earned roughly", never a promise).
- Source and vintage citations in the "How to read this" box.
- Clean, minimal, trustworthy aesthetic; good search experience with example hints.
- Color-coded pass / fall short / not enough data summary chips on search results.

## Suggested execution order

1. Phase 1 items 1.1, 1.2, 1.6 together (one refactor of the program list).
2. Phase 3 items 3.1 to 3.3 (header fixes, small and site-wide).
3. Phase 2 (homepage hero and module cards).
4. Remaining Phase 1 items (1.3, 1.4, 1.5, 1.7, 1.8, 1.9).
5. Phase 3 polish (3.4, 3.5).
