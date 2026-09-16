/* Page timing: LCP, CLS and long tasks, measured rather than gated.
 *
 * WHAT THIS IS NOT. It is not a Core Web Vitals gate, and it deliberately does not compare anything
 * to 2.5 seconds. Decision A was approved as a lab gate on that threshold, and reconsidering it
 * found the framing wrong:
 *
 *   - The 2.5s boundary does work because it feeds Google's page-experience signal, and that signal
 *     is applied where Google HAS field data. The Chrome UX Report has none for truewise.dev, on
 *     mobile or desktop, because the site is below its minimum sample. So the boundary currently
 *     decides nothing.
 *   - The measurement it was meant to settle is a 2.503s median against 2.500s. That is a 3ms
 *     margin. Run-to-run variance on the same machine is tens of milliseconds and on a shared CI
 *     runner it is hundreds. A threshold inside the noise turns coin flips into verdicts, which is
 *     this project's recurring failure wearing a stopwatch.
 *
 * So: measure, record, and guard against a LARGE regression against a recorded baseline. The risk
 * worth catching is not three milliseconds. It is the day a hero image, a third font or a tag
 * manager turns 2.5s into 6s, and that shows up against any honest baseline.
 *
 * The median of several cold runs is reported WITH its spread. A median printed alone invites the
 * reader to treat it as exact, and the spread is the part that says how much to trust it.
 */

"use strict";

/** Fixed conditions, so two runs are comparable. Roughly a mid-range Android on a good 4G link.
 *  The absolute numbers matter less than their stability: everything here is held constant so that
 *  a change in the result means a change in the page. */
const CONDITIONS = {
  cpuThrottlingRate: 4,
  network: {
    offline: false,
    downloadThroughput: (1.6 * 1024 * 1024) / 8, // 1.6 Mbps
    uploadThroughput: (750 * 1024) / 8,
    latency: 150,
  },
  viewport: { width: 390, height: 844 },
  runs: 5,
};

/** Installed BEFORE navigation via addInitScript, because LCP and layout shifts are emitted during
 *  load. An observer attached after the page settles sees a clean slate and reports zero, which
 *  would be a confident measurement of nothing. */
function installObservers() {
  window.__perf = { lcp: 0, cls: 0, longTasks: 0, tbt: 0, shifts: [] };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__perf.lcp = e.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        /* Shifts the user caused by interacting are excluded by the metric's own definition. */
        if (e.hadRecentInput) continue;
        window.__perf.cls += e.value;
        /* ATTRIBUTION, not just a total.
         *
         * The first version recorded the number alone. It reported CLS 0.345 on Compare, which is
         * 3.45x the "good" threshold, and told nobody WHAT moved. Reproducing it by hand then
         * failed, because layout shift only appears on a slow connection and a fast browser session
         * shows a clean 0. A metric that can only be observed under conditions the reader cannot
         * easily recreate has to carry its own explanation, or it is a number to worry about rather
         * than a defect to fix. */
        window.__perf.shifts.push({
          value: e.value,
          at: Math.round(e.startTime),
          /* A ZERO currentRect DOES NOT MEAN THE ELEMENT WAS REMOVED. It means the element moved
           * out of the viewport, so its intersection with the viewport is empty.
           *
           * Reading it as removal sent me looking for code that deletes `.caveats` from the Compare
           * page. Nothing does. `isConnected` and a live rect settled it in one run: the element
           * reported `still in document: true` and `actual now y=3016 h=322`, having been at y=492
           * before. It had not gone anywhere; the comparison table rendered into the empty `#cmp`
           * above it and pushed it 2,500px down the page.
           *
           * Those two fields are here so the next reader does not repeat that. The before and after
           * rects alone are ambiguous between "moved far" and "disappeared", and the two call for
           * opposite fixes.
           */
          sources: (e.sources || []).slice(0, 3).map((s) => {
            const n = s.node;
            if (!n || !n.tagName) return "(node was already gone when the shift was recorded)";
            const cls = n.className && typeof n.className === "string"
              ? "." + n.className.trim().split(/\s+/)[0] : "";
            const text = (n.textContent || "").trim().replace(/\s+/g, " ").slice(0, 36);
            const r = (rect) => (rect ? `y=${Math.round(rect.y)} h=${Math.round(rect.height)}` : "none");
            let live = "unreadable";
            try {
              const b = n.getBoundingClientRect();
              live = `y=${Math.round(b.y)} h=${Math.round(b.height)}`;
            } catch (_) { /* detached nodes can throw; that is itself the answer */ }
            return `${n.tagName.toLowerCase()}${n.id ? "#" + n.id : ""}${cls} "${text}" | ` +
                   `before ${r(s.previousRect)} | after ${r(s.currentRect)} | ` +
                   `still in document: ${n.isConnected} | actual now ${live}`;
          }),
        });
      }
    }).observe({ type: "layout-shift", buffered: true });

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        window.__perf.longTasks += 1;
        /* Total Blocking Time counts only the part of a task beyond 50ms. */
        window.__perf.tbt += Math.max(0, e.duration - 50);
      }
    }).observe({ type: "longtask", buffered: true });
  } catch (_) {
    /* An engine without one of these entry types should not take the run down. The harness reports
     * a missing metric as missing rather than as a zero. */
  }
}

/** Read the observers plus the navigation timings. Returns nulls, never zeros, for anything that
 *  did not report: a zero LCP is indistinguishable from an instant one. */
function readPerf() {
  const p = window.__perf || {};
  const nav = performance.getEntriesByType("navigation")[0] || {};
  const fcp = performance.getEntriesByName("first-contentful-paint")[0];
  return {
    lcp: p.lcp > 0 ? Math.round(p.lcp) : null,
    cls: typeof p.cls === "number" ? Math.round(p.cls * 1000) / 1000 : null,
    tbt: typeof p.tbt === "number" ? Math.round(p.tbt) : null,
    longTasks: p.longTasks ?? null,
    fcp: fcp ? Math.round(fcp.startTime) : null,
    domContentLoaded: nav.domContentLoadedEventEnd ? Math.round(nav.domContentLoadedEventEnd) : null,
    transferKB: nav.transferSize ? Math.round(nav.transferSize / 1024) : null,
    shifts: (p.shifts || [])
      .slice()
      .sort((a, b) => b.value - a.value)
      .slice(0, 5)
      .map((s) => ({ value: Math.round(s.value * 1e4) / 1e4, at: s.at, sources: s.sources })),
  };
}

const median = (xs) => {
  const v = xs.filter((x) => x != null).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : Math.round((v[m - 1] + v[m]) / 2);
};

/** Median with the spread that says how much to trust it. */
function summarise(values) {
  const v = values.filter((x) => x != null);
  if (!v.length) return { median: null, min: null, max: null, n: 0 };
  return {
    median: median(v),
    min: Math.min(...v),
    max: Math.max(...v),
    spread: Math.round((Math.max(...v) - Math.min(...v)) * 1000) / 1000,
    n: v.length,
  };
}

/* REGRESSION THRESHOLDS, deliberately wide.
 *
 * These are not quality targets. They are the point at which a change is too large to be variance,
 * so that the check speaks only when it has something to say. A 5% drift says nothing; a doubling
 * says someone shipped something heavy.
 */
const REGRESSION = {
  lcp: { factor: 1.5, floor: 400 },   // 50% worse AND at least 400ms worse
  tbt: { factor: 2.0, floor: 150 },
  cls: { factor: 2.0, floor: 0.05 },
};

/* CLS DOES get an absolute threshold, and LCP does not. That is not an inconsistency, and the first
 * version of this file got it wrong by treating all three metrics the same.
 *
 * The argument against grading LCP was specific: the question was 2.503s against 2.500s, a 3ms
 * margin, while five cold runs of one page spread by 100ms or more. The threshold sat inside its own
 * noise, so a verdict would have been a coin flip.
 *
 * Neither half of that holds for CLS. The first real run measured 0.345 on Compare against a 0.1
 * "good" boundary: not a 3ms margin but a 3.45x overshoot. And the measurement is stable, since four
 * of six routes returned exactly 0. A metric with a wide margin and no noise is exactly what an
 * absolute threshold is for.
 *
 * It also differs in kind. LCP without field data is a proxy for a ranking signal that is not
 * currently being applied. Layout shift is not a proxy for anything: it is content moving under
 * someone's finger as they reach for it, and it is a defect whether or not Google is watching.
 */
const CLS_GOOD = 0.1;
const CLS_POOR = 0.25;

/* SELF-TEST for the attribution, run in the page after the real measurement is taken.
 *
 * Everything else in this harness was validated by making it fail on purpose. The shift attribution
 * was not, and it promptly produced a reading that did not fit the markup. Two attempts to confirm
 * it by hand recorded zero entries, because layout shift only counts content inside the viewport and
 * only appears under throttling, so the usual "break it and watch" check kept measuring nothing.
 *
 * So the probe proves itself instead: force a known shift at the TOP of the viewport, where it must
 * be counted, and check that the observer names the element that was actually moved. If it does not,
 * the run says the attribution is unreliable rather than printing it as fact.
 */
function attributionSelfTest() {
  return new Promise((resolve) => {
    const seen = [];
    let po;
    try {
      po = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          for (const s of e.sources || []) {
            if (s.node && s.node.getAttribute && s.node.getAttribute("data-tw-selftest") === "1") {
              seen.push(Math.round(e.value * 1e4) / 1e4);
            }
          }
        }
      });
      po.observe({ type: "layout-shift" });
    } catch (e) {
      return resolve({ ran: false, reason: String(e) });
    }

    /* The victim must be an element that is ALREADY RENDERED and already inside the viewport.
     *
     * The first version of this self-test created a fresh <p>, inserted it, then pushed it down. It
     * reported "not attributed" on all six routes, including routes where attribution demonstrably
     * worked, because a newly inserted node is not a shifted node: the layout-shift API counts
     * previously-painted content that moves, and has nothing to say about content that did not
     * exist a frame ago. The self-test was failing itself rather than the thing it was testing,
     * which is at least the right direction to fail in, but it certified nothing.
     */
    window.scrollTo(0, 0);
    const vh = window.innerHeight;
    const victim = Array.from(document.body.querySelectorAll("p, h1, h2, li, div"))
      .find((el) => {
        const r = el.getBoundingClientRect();
        return r.height > 12 && r.width > 40 && r.top >= 0 && r.bottom < vh * 0.8 &&
               getComputedStyle(el).position === "static";
      });
    if (!victim) {
      try { po.disconnect(); } catch (_) {}
      return resolve({ ran: false, reason: "no statically positioned element inside the viewport to move" });
    }
    const before = Math.round(victim.getBoundingClientRect().y);
    victim.setAttribute("data-tw-selftest", "1");

    const spacer = document.createElement("div");
    spacer.style.cssText = "height:320px";
    victim.parentNode.insertBefore(spacer, victim);

    setTimeout(() => {
      try { po.disconnect(); } catch (_) {}
      const after = Math.round(victim.getBoundingClientRect().y);
      spacer.remove();
      victim.removeAttribute("data-tw-selftest");
      resolve({
        ran: true,
        movedBy: after - before,
        attributed: seen.length > 0,
        values: seen,
        note: seen.length
          ? "a known 320px shift was attributed to the element that actually moved, so the source " +
            "names above are evidence"
          : "a known 320px shift of an already-painted element produced no attributed entry, so the " +
            "element names above are NOT evidence",
      });
    }, 500);
  });
}

/** Absolute CLS judgement, separate from regression-against-baseline. */
function clsFindings(route, summary) {
  const v = summary && summary.cls && summary.cls.median;
  if (v == null) return [];
  if (v > CLS_POOR) {
    return [{ kind: "cls-poor", blocking: true, detail:
      `${route} shifts ${v} during load, over the ${CLS_POOR} "poor" boundary and ${Math.round(v / CLS_GOOD * 10) / 10}x ` +
      `the ${CLS_GOOD} target. Content is moving under the reader as the page settles.` }];
  }
  if (v > CLS_GOOD) {
    return [{ kind: "cls-needs-work", blocking: false, detail:
      `${route} shifts ${v} during load, over the ${CLS_GOOD} target but under the ${CLS_POOR} ` +
      `"poor" boundary.` }];
  }
  return [];
}

/** Compare a summary against a recorded baseline. Returns findings, never a verdict about 2.5s. */
function regressions(route, now, base) {
  const out = [];
  if (!base) return out;
  for (const key of ["lcp", "tbt", "cls"]) {
    const cur = now[key] && now[key].median;
    const was = base[key] && base[key].median;
    if (cur == null || was == null) continue;
    const rule = REGRESSION[key];
    const worse = cur - was;
    if (cur > was * rule.factor && worse >= rule.floor) {
      out.push({
        kind: `perf-${key}`,
        blocking: true,
        detail:
          `${route} ${key.toUpperCase()} moved from ${was} to ${cur} (${Math.round((cur / was - 1) * 100)}% worse, ` +
          `+${Math.round(worse * 1000) / 1000}). That is past variance, so something on the page changed.`,
      });
    }
  }
  return out;
}

module.exports = {
  CONDITIONS, installObservers, readPerf, summarise, regressions, clsFindings,
  attributionSelfTest,
  REGRESSION, CLS_GOOD, CLS_POOR,
};
