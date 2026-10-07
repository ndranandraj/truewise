# PR #14 pre-merge acceptance (High Schools, Prototype H)

Build: the PR branch `k12-hub`, rebuilt locally with `./preview-build.sh`. Served from `site/` on
localhost:8787. Automated checks ran in Playwright (Firefox 155 and Chromium). "200% text" means
Firefox's native text-only zoom (`ui.textScaleFactor` 200), with body text confirmed at 30px.

## Automated (done)

**Layout, normal size and 200% text** (Firefox; 320×568, 320×700, 375×667, 390×844, 768×1024,
1100×800, 1280×800, 1440×900): the hub, the lookup and a school page. Body text confirmed (15px,
then 30px); no page wider than the screen; nothing in the search form runs past the form; the
Search button's text is not clipped.

**Found in this pass and fixed on the branch:** a school page was wider than the screen at 200%
text on phones, because CRDC names are in capitals and one word ("STUYVESANT") was wider than the
column at 60px. This was already true on the live site (52% of school pages at 320px, 29% at
390px). The name now takes the lede size when its block is narrow in its own text (40px at 200% text);
normal size is unchanged. Known limit: a word too long even at that size (for example
"INTERNATIONAL") still breaks inside the word at 320px, on about 9% of school pages (2% at 390px), and stays on
screen. The layout check now measures a school page (route `k12-school`, Stuyvesant).

**Search handoff** (Firefox and Chromium):
- Enter in the hub field goes to `/k12/advanced-courses/?q=Lane+Tech`; the lookup's field reads
  "Lane Tech", has focus, and the first result is Lane Technical High School.
- The Search button does the same (Stuyvesant found).
- An empty search lands on the lookup with an empty field; a two-letter search asks for three.

**Example links** (Firefox and Chromium): each of the five opens its own school page with the
right name and no "School not found"; "Find another school" returns to the search.

**Keyboard** (Firefox and Chromium): after the section links, Tab reaches the field, Search, the
five examples, then the tiles. Focus is visible (an outline of at least 2px) on each. Enter on a
focused example opens it; Back returns to the hub.

**axe-core** (WCAG 2 A/AA and best practice): no violations on the hub, the lookup or a school
page at 390 and 1280px.

## Found in review of 14f0c92 (6 October), fixed

Inherited lookup behaviour, not introduced by #14, but on the path the new hub leads into:
- **Result names ran past their cards.** At 320px with native 200% text, searching "international":
  "INTERNATIONAL" ran about 5px past its card's border while the page still fitted, so the
  document-width checks passed. Result cards now break a word too long for the card (hyphenated
  where the browser can); the text keeps its size.
- **No match missed the status region.** "No high schools match" was a list item, shown but outside
  `#rescount` (role="status"). It is now said in the status region and only there; changing or
  clearing the query updates it. `tests/k12_lookup_states.js` (jsdom; gate and PR CI) runs no
  match, a new query and clearing; on 14f0c92 it fails.
- **New layout-check probe, `boxedTextProbe`:** at doubled text, text must stay inside any box that
  draws a left and right border. With a populated-search route (`k12-search`,
  `?q=international`) it found two more of the same kind, both live today:
  - the school page's course cards at 769px ("International Baccalaureate" 19px past its card):
    the course grid's column minimum is now in em (13.333em, the old 200px at 15px text), so normal
    size is unchanged and enlarged cards widen;
  - the FVT/GE key-figure box at 320px ("of 4,635 colleges" 8px past it, from `white-space:
    nowrap`): outside #14's pages, fixed in its own commit at Anand's choice. Only that case
    changes; every other width and the profile summary are identical.
- **Result names skipped a heading level.** Found by the stricter axe scan, which now reaches a
  populated search: names were `h3` directly under the page's `h1` (axe heading-order; live has
  it too). They are `h2` now, sized like the hub's tool cards (`--t-sub`, 18px, from 16.8px), the
  nearest type token, since the page's heading sizes must use tokens.
- Evidence scripts: the keyboard pass now continues through the Compare schools tile; the axe scan
  requires HTTP 200 and the intended content before scanning and adds populated and no-match
  searches.

## Not done (record explicitly)

- **Safari:** not tested. Playwright's WebKit is not installed here, and WebKit would not count
  as Safari in any case. Needs Safari on macOS and iOS.
- **Real device:** not tested.
- **VoiceOver:** not tested (cannot be automated). Script below.
- **Timing:** inconclusive. The machine was heavily loaded by processes outside the project; the
  baseline comparison flagged unchanged pages. Rerun `node tests/layout_check.js --perf` on a
  quiet machine.

## VoiceOver script (about 5 minutes, Safari on macOS)

Start VoiceOver (Cmd+F5). Open `/k12/` on the PR build.

1. **Rotor, landmarks** (VO+U, then left/right arrow to Landmarks). Expect: banner, the
   "Primary" navigation, the "High-school views" navigation, main, a **search** landmark, the
   "From the data" complementary region, the "About the data" complementary region, and the
   footer's "Explore" and "Research" navigation. Note anything missing or unnamed.
2. **Rotor, headings.** Expect "What does your high school offer?" as the only heading level 1,
   then "State report cards" and "Compare schools".
3. **Search.** VO+Right from the intro into the form. Expect the field announced as "Find a high
   school, search text field" (or similar), then the Search button.
4. **Examples.** Continue. Expect "Examples, not recommendations", then a list of 5 items, each
   link read as the school and its place, for example "Lane Tech Chicago, link". Check the place
   is read, not skipped.
5. **The note.** Continue into "From the data". Expect the whole sentence, including "7,016 of
   27,085" and "a count that includes alternative, special-education and juvenile-justice
   schools". Check numbers are read as numbers.
6. **Handoff.** Go back to the field, type "Lane Tech", press Return. Expect the new page, focus
   in its search field, and the result count announced politely (for example "2 schools").
7. **A school page.** Open Lane Technical High School from the results. Expect focus on its name
   (the heading), and the page title to change to the school's name.
8. **Back.** Use "Find another school". Expect focus back on the search heading.

Record for each step: what was spoken, and pass or fail.
