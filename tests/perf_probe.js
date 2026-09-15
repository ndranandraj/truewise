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
          sources: (e.sources || []).slice(0, 3).map((s) => {
            const n = s.node;
            if (!n || !n.tagName) return "(node no longer in the document)";
            const cls = n.className && typeof n.className === "string"
              ? "." + n.className.trim().split(/\s+/)[0] : "";
            const text = (n.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
            const py = s.previousRect ? Math.round(s.previousRect.y) : null;
            const cy = s.currentRect ? Math.round(s.currentRect.y) : null;
            const ph = s.previousRect ? Math.round(s.previousRect.height) : null;
            const ch = s.currentRect ? Math.round(s.currentRect.height) : null;
            return `${n.tagName.toLowerCase()}${n.id ? "#" + n.id : ""}${cls} "${text}" ` +
                   `moved y ${py}->${cy}, height ${ph}->${ch}`;
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
  REGRESSION, CLS_GOOD, CLS_POOR,
};
