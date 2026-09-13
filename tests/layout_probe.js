/* The layout and interaction probe: one measurement pass over a rendered page.
 *
 * WHY THIS EXISTS, and why it is a separate file from the harness.
 *
 * Three browser review rounds on work whose tests were green found seven defects. Two of my own
 * tests passed while agreeing with a bug, because jsdom has no layout engine: every offsetWidth is
 * 0, every getBoundingClientRect is a rectangle of zeroes, and an assertion about geometry against
 * zeroes is an assertion about nothing. So the smoke suites cannot see overflow, clipping, tap
 * target size or anything else that depends on a box actually being laid out.
 *
 * This file holds ONLY the measurement, as one self-contained function with no imports, no closure
 * over anything, and no Node APIs. That makes it runnable three ways from a single source of truth:
 *
 *   1. Playwright:      page.evaluate(probe, options)
 *   2. Any DevTools:    paste `(<the function>)()` into the console
 *   3. The in-app browser, via its javascript tool
 *
 * The third route is what made it possible to get real findings from the live site on a machine
 * where no browser binary could be installed. If the probe imported anything, that would not work.
 *
 * WHAT IT DELIBERATELY DOES NOT DO. It does not click. Focus recovery and live-region announcement
 * are properties of what happens AFTER an interaction, and a probe that drove its own interactions
 * would be asserting over a page state it invented. The harness drives; the probe measures. The two
 * focus helpers below exist to be called by the harness at the moment it chooses.
 */

"use strict";

/** Widths from the agreed scope. 320 is the narrowest phone still in real use, 390 is the modern
 *  iPhone, 768 is the tablet breakpoint the program table stacks at, 1280 is a laptop. */
const WIDTHS = [
  { label: "320", width: 320, height: 720, mobile: true },
  { label: "390", width: 390, height: 844, mobile: true },
  { label: "768", width: 768, height: 1024, mobile: false },
  { label: "desktop", width: 1280, height: 900, mobile: false },
];

/** The six agreed routes. Penn State is the 489-program giant that exercises the progressive tail;
 *  Agape is the all-insufficient profile where every row must read "insufficient data".
 *
 *  Compare CARRIES SCHOOLS ON PURPOSE. The first real run measured `/compare/` bare, which is a
 *  search box and nothing else, and reported it clean at all four widths. The reason Compare is in
 *  this list at all is the metric-major card stacking below 929px, and that layout does not exist
 *  until schools are selected: the run was a clean sweep over the one state the route was added to
 *  exercise. Penn State, UCLA and Baylor are three real unitids with contrasting coverage.
 *
 *  `kind` tells the harness which interaction driver applies. Careers is not a `tw-table`; it has
 *  its own `cr-*` markup and its own live region, and treating "no .tw-table" as "nothing to drive"
 *  silently skipped every Careers interaction while the report said clean.
 */
const ROUTES = [
  { label: "homepage", path: "/", kind: "static" },
  { label: "value-check", path: "/value-check/", kind: "static" },
  { label: "penn-state", path: "/college/pennsylvania-state-university-main-campus/", kind: "twtable" },
  { label: "agape", path: "/college/agape-college-of-business-and-science/", kind: "twtable" },
  { label: "compare", path: "/compare/?schools=214777,110662,223232", kind: "compare" },
  { label: "careers", path: "/careers/", kind: "careers" },
];

/* ------------------------------------------------------------------------------------------- */

/**
 * Measure one page at its current viewport size. Returns a plain JSON-safe object.
 *
 * @param {{minTarget?: number, tolerance?: number}} [opts]
 */
function probe(opts) {
  const o = opts || {};
  /* WCAG 2.2 Target Size (Minimum) is 24 by 24 CSS pixels. Using 24 rather than the 44 from the
   * older iOS guidance keeps this a standards check rather than a taste check, so a failure is
   * arguable in one direction only. */
  const MIN_TARGET = o.minTarget || 24;
  /* Sub-pixel rounding routinely puts a box at 390.4px in a 390px viewport. A 1px tolerance keeps
   * that from being reported as a defect; anything genuinely overflowing exceeds it by far more. */
  const TOL = o.tolerance == null ? 1 : o.tolerance;

  const vw = window.innerWidth;

  /* A viewport of zero is not a narrow viewport. It happens when the page is measured before the
   * browser has laid anything out, or in a hidden pane, and every box then reports as overflowing a
   * 0px window. The first live run of this probe did exactly that and returned four confident
   * findings about a page it had not measured, which is the reachability probe's own bug in a new
   * place: a conclusion drawn from a measurement that never happened. Refuse instead.
   */
  if (!vw || vw < 200) {
    return {
      inconclusive: true,
      viewport: { width: vw, height: window.innerHeight },
      url: location.pathname + location.search,
      findings: [],
      blocking: 0,
      detail:
        `Viewport reported ${vw}px, which is not a real layout. Nothing was measured, and this is ` +
        `not a pass.`,
    };
  }

  const findings = [];
  const add = (kind, blocking, detail, extra) =>
    findings.push(Object.assign({ kind, blocking, detail }, extra || {}));

  const describe = (el) => {
    if (!el || !el.tagName) return "(none)";
    const id = el.id ? "#" + el.id : "";
    const cls = el.className && typeof el.className === "string"
      ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".")
      : "";
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
    return el.tagName.toLowerCase() + id + cls + (text ? ` "${text}"` : "");
  };

  const visible = (el, rect) => {
    if (rect.width === 0 && rect.height === 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0";
  };

  /* An ancestor that scrolls horizontally ON PURPOSE. The program tables ship a
   * .tw-table__scroll wrapper precisely so a wide table can be swiped rather than breaking the
   * page, and there are ~2,821 such wrappers across the site. Reporting their contents as overflow
   * would bury the real findings under thousands of false ones, which is how a check stops being
   * read at all. */
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
    }
    return false;
  };

  /* --- 1. Horizontal overflow ------------------------------------------------------------- */

  const docOverflow = document.documentElement.scrollWidth - vw;
  if (docOverflow > TOL) {
    add("overflow-document", true,
      `The page is ${document.documentElement.scrollWidth}px wide in a ${vw}px viewport, so it ` +
      `scrolls sideways by ${docOverflow}px.`);
  }

  const offenders = [];
  const all = document.body ? document.body.querySelectorAll("*") : [];
  for (const el of all) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const over = Math.round(rect.right - vw);
    const under = Math.round(-rect.left);
    if (over <= TOL && under <= TOL) continue;
    if (inScroller(el)) continue;
    offenders.push({ el, selector: describe(el), overRight: over, overLeft: under, width: Math.round(rect.width) });
  }
  /* Report only the OUTERMOST offender in each chain. A 600px table in a 320px viewport otherwise
   * reports itself plus every cell, and the reader has to work out which one to fix. */
  const outermost = offenders.filter(
    (f) => !offenders.some((g) => g !== f && g.el.contains(f.el)),
  );
  for (const f of outermost) {
    add("overflow-element", true,
      `${f.selector} extends ${Math.max(f.overRight, f.overLeft)}px past the ${vw}px viewport ` +
      `(element is ${f.width}px wide) and is not inside a scrollable wrapper.`,
      { selector: f.selector });
  }

  /* --- 2. Element geometry ----------------------------------------------------------------- */

  /* Text cut off by an overflow:hidden ancestor is invisible in a screenshot diff and invisible to
   * jsdom, but a reader simply loses the end of the sentence. */
  const clipped = [];
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.overflow !== "hidden" && cs.overflowX !== "hidden") continue;
    if (el.scrollWidth - el.clientWidth <= TOL) continue;
    if (!el.textContent || !el.textContent.trim()) continue;
    if (el.querySelector("*")) continue; // leaf text nodes only, so we name the element that clips
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    clipped.push(el);
    add("clipped-text", true,
      `${describe(el)} hides ${el.scrollWidth - el.clientWidth}px of its own text behind ` +
      `overflow:hidden, so the end of it cannot be read or scrolled to.`,
      { selector: describe(el) });
  }

  /* WCAG 2.2 Target Size (Minimum), 2.5.8, is NOT a bare size threshold, and reading it as one is
   * how this check nearly shipped as noise.
   *
   * The first version reported every control under 24px. On one profile page that was 22 findings,
   * including every footer link and every column sort button. All 22 were compliant, because the
   * success criterion exempts an undersized target whose 24px-diameter circle does not intersect a
   * neighbouring target. Twenty-two findings, zero defects: a check nobody would read twice.
   *
   * So the rule implemented here is the spacing exception as written. For each undersized target,
   * put a 24px circle on its centre, then ask whether that circle reaches:
   *   - another UNDERSIZED target's circle  -> centre distance under 24px
   *   - any other target's BOUNDING BOX     -> nearest point of that box within 12px
   * Only then is it a finding. The box form matters: a wide link sitting one line below a short one
   * is missed entirely by a centre-to-centre test, because the centres are far apart horizontally
   * while the boxes are 10px apart vertically.
   */
  /* POINTER targets only. A focusable scroll region (`<div class="tw-table__scroll" tabindex="0"
   * role="region">`) is keyboard-scrollable, not clickable, so it is not a target under a criterion
   * about pointer input. Counting it as one made every link inside the table "overlap" it, because
   * a child always intersects its own container: 22 findings on Careers alone, all of them the
   * wrapper reporting its own contents. */
  const POINTER = 'a[href], button, input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="tab"], [role="menuitem"]';
  const targetEls = document.querySelectorAll(POINTER);
  const targets = [];
  for (const el of targetEls) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    /* A link inside a paragraph of running text is exempt under the Inline exception. A text-node
     * sibling is the cheap test for "this link sits in a sentence". */
    const inSentence =
      el.tagName === "A" &&
      el.parentElement &&
      Array.from(el.parentElement.childNodes).some(
        (n) => n.nodeType === 3 && n.textContent.trim().length > 0,
      );
    targets.push({
      el, rect, inSentence,
      cx: rect.left + rect.width / 2,
      cy: rect.top + rect.height / 2,
      under: rect.width < MIN_TARGET || rect.height < MIN_TARGET,
    });
  }

  const radius = MIN_TARGET / 2;
  const small = [];
  for (const t of targets) {
    if (!t.under || t.inSentence) continue;
    let hit = null;
    let nearest = Infinity;
    for (const o of targets) {
      if (o === t) continue;
      /* A target never conflicts with its own ancestor or descendant. Nested targets are a
       * different defect (and an HTML validity error when it is a link inside a link); the spacing
       * criterion is about two targets a finger could confuse, which containment is not. */
      if (o.el.contains(t.el) || t.el.contains(o.el)) continue;
      let gap;
      if (o.under) {
        gap = Math.hypot(o.cx - t.cx, o.cy - t.cy) - MIN_TARGET;
      } else {
        const dx = Math.max(o.rect.left - t.cx, 0, t.cx - o.rect.right);
        const dy = Math.max(o.rect.top - t.cy, 0, t.cy - o.rect.bottom);
        gap = Math.hypot(dx, dy) - radius;
      }
      if (gap < nearest) { nearest = gap; hit = o; }
    }
    if (nearest >= 0) continue; // spacing exception applies, so it conforms
    small.push(describe(t.el));
    add("tap-target", false,
      `${describe(t.el)} is ${Math.round(t.rect.width)} by ${Math.round(t.rect.height)} CSS px, ` +
      `and its 24px target circle overlaps ${describe(hit.el)} by ${Math.abs(Math.round(nearest))}px, ` +
      `so WCAG 2.2 Target Size (Minimum) is not met by size or by spacing.`,
      { selector: describe(t.el) });
  }

  const h1 = document.querySelector("h1");
  const headings = h1
    ? {
        text: (h1.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
        fontSize: Math.round(parseFloat(getComputedStyle(h1).fontSize) * 10) / 10,
        height: Math.round(h1.getBoundingClientRect().height),
      }
    : null;

  /* --- 3. Live regions and the count line -------------------------------------------------- */

  const liveRegions = Array.from(
    document.querySelectorAll('[aria-live], [role="status"], [role="alert"]'),
  ).map((el) => ({
    selector: describe(el),
    role: el.getAttribute("role") || "",
    politeness: el.getAttribute("aria-live") || "",
    text: (el.textContent || "").trim().replace(/\s+/g, " "),
  }));

  /* The program table states its own count in prose. Read the first number out of it and compare it
   * against the rows actually in the tbody. "Show all 489 programs" once rendered 160 while
   * announcing 489: three statements about one table, and the loudest was the false one. That
   * defect is invisible to any check that reads only one of the three. */
  const countEl = document.querySelector(".tw-table__count");
  const tbody = document.querySelector(".tw-table tbody");
  let countLine = null;
  if (countEl && tbody) {
    const text = (countEl.textContent || "").trim().replace(/\s+/g, " ");
    const numbers = (text.match(/[\d,]+/g) || []).map((n) => parseInt(n.replace(/,/g, ""), 10));
    const renderedRows = tbody.querySelectorAll("tr").length;
    countLine = { text, numbers, renderedRows };
    /* The claim is only checkable when the line is of the "Showing X of Y" shape: X must be the
     * rows on screen. When the page is filtered or the tail failed, the line says something else
     * and is reported verbatim rather than judged, because a check that guesses at prose is the
     * pattern-matches-prose failure in a new costume. */
    if (/^Showing /.test(text) && numbers.length >= 1 && numbers[0] !== renderedRows) {
      add("count-mismatch", true,
        `The table says "${text}" but the tbody holds ${renderedRows} rows. The page is stating a ` +
        `number it is not displaying.`);
    }
  }

  /* --- 4. Honesty sentinels ---------------------------------------------------------------- */

  /* The standing rule is that unknown is never rendered as a known value. The build-time honesty
   * scan covers the static HTML; this covers what JavaScript puts on screen afterwards, which the
   * scan never sees. */
  /* Two classes of sentinel, because one rule for both produces a false positive on this site's own
   * honest copy.
   *
   * HARD sentinels are never English. "undefined" and "NaN" appearing anywhere in the rendered text
   * mean a value failed to resolve, full stop.
   *
   * SOFT sentinels are also ordinary words or legitimate values. Agape's profile opens "None of
   * Agape College of Business and Science's 8 programs have enough data", which is the page saying
   * exactly the honest thing it is supposed to say. Scanning innerText for "None" flags that
   * sentence, and a check that fires on correct copy trains its reader to ignore it. So a soft
   * sentinel counts only when it is the ENTIRE text of a leaf element or table cell, which is what
   * a stringified null actually looks like when it lands in a rendered field.
   */
  const bodyText = document.body ? document.body.innerText || "" : "";
  for (const s of ["undefined", "NaN"]) {
    if (new RegExp(`(^|[\\s>(\\[])${s}([\\s<).,\\]]|$)`).test(bodyText)) {
      add("sentinel-rendered", true,
        `The rendered text contains "${s}", which means a value failed to resolve and reached the ` +
        `page as if it were data.`);
    }
  }
  const SOFT = ["None", "null", "nan", "NULL", "-9", "-8", "-11"];
  for (const el of document.querySelectorAll("td, th, dd, span, li, p")) {
    if (el.querySelector("*")) continue;
    const txt = (el.textContent || "").trim();
    if (!SOFT.includes(txt)) continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    add("sentinel-rendered", true,
      `${describe(el)} renders "${txt}" as its whole value. Unknown must read "insufficient data", ` +
      `never a sentinel and never 0.`,
      { selector: describe(el) });
  }

  return {
    viewport: { width: vw, height: window.innerHeight, dpr: window.devicePixelRatio || 1 },
    url: location.pathname + location.search,
    title: document.title,
    documentScrollWidth: document.documentElement.scrollWidth,
    headings,
    countLine,
    liveRegions,
    counts: {
      overflowing: outermost.length,
      clipped: clipped.length,
      smallTargets: small.length,
    },
    findings,
    blocking: findings.filter((f) => f.blocking).length,
  };
}

/* ------------------------------------------------------------------------------------------- */

/** Identify whatever currently holds focus, including the caret position for text inputs.
 *
 *  Focus falling to <body> after a reveal is the specific defect this catches: the reader presses
 *  "Show all", the table re-renders, the button they pressed no longer exists, and a keyboard user
 *  is silently returned to the top of the document. */
function focusState() {
  const a = document.activeElement;
  if (!a || a === document.body) {
    return { onBody: true, key: null, selector: "body", caret: null };
  }
  const holder = a.closest ? a.closest("[data-tw-focus]") : null;
  let caret = null;
  try {
    if (a.selectionStart != null) caret = a.selectionStart;
  } catch (_) {
    /* selectionStart throws on input types that do not support selection. Not a finding. */
  }
  const cls = a.className && typeof a.className === "string"
    ? "." + a.className.trim().split(/\s+/).slice(0, 2).join(".")
    : "";
  return {
    onBody: false,
    key: holder ? holder.getAttribute("data-tw-focus") : null,
    selector: a.tagName.toLowerCase() + (a.id ? "#" + a.id : "") + cls,
    text: (a.textContent || a.value || "").trim().replace(/\s+/g, " ").slice(0, 40),
    caret,
  };
}

/** Read every live region's current text, for comparing before and after an interaction. */
function liveText() {
  return Array.from(document.querySelectorAll('[aria-live], [role="status"], [role="alert"]'))
    .map((el) => (el.textContent || "").trim().replace(/\s+/g, " "))
    .filter(Boolean);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { probe, focusState, liveText, WIDTHS, ROUTES };
}
