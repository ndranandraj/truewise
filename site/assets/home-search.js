/* Homepage search suggestions (Prototype Q, approved 21 November 2026).
 *
 * The form works without this script: it submits to Value Check. With it, the box suggests colleges
 * as you type, from the matcher Value Check and Compare use (assets/college-search.js), and choosing
 * one opens the college's profile. The combobox is the site's own (components/search.js) in its
 * enhance mode, attached to the input that is already on the page; Enter with nothing chosen still
 * submits the form.
 *
 * The list of colleges (/college/search-index.json, written by build_college_pages from the same
 * slug map as the profiles) loads on first focus or first keystroke, so the page itself loads
 * nothing more. A visitor can tap the box before this script arrives, which fires no focus event it
 * can hear, so it also loads at start-up if the box already has focus. If the list does not load,
 * the status line says so and points to Search, and the next keystroke tries again.
 */
(function () {
  const form = document.querySelector("form.h-search[data-index]");
  const input = document.getElementById("h-q");
  if (!form || !input || !window.TWSearch || !window.TWSearchUI) return;

  const esc = (s) =>
    (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  let schools = null;
  let loading = null;
  let failed = false;

  const box = new window.TWSearchUI.SearchCombobox(form, {
    input,
    after: form.querySelector(".h-search__row"),
    provider: window.TWSearch.CollegeSearchProvider,
    data: () => schools,
    limit: 8,
    listLabel: "Colleges",
    loadingText: () =>
      failed
        ? "Suggestions did not load. Press Search to look the college up."
        : "Loading colleges…",
    countText: (n, limit) =>
      `${n} college${n === 1 ? "" : "s"}${n === limit ? " shown; press Search for more" : ""}. ` +
      "Use the arrow keys to choose one.",
    noneText: (q) => `No colleges match ${q}`,
    emptyHTML: (q) =>
      `No college matches “${esc(q)}”. Try its own name or its city, or ` +
      `<a href="/colleges/">browse colleges by state</a>.`,
    onSelect: (r) => window.location.assign(`/college/${r.raw.slug}/`),
  });

  function load() {
    if (schools || loading) return;
    failed = false;
    loading = fetch(form.getAttribute("data-index"))
      .then((r) => {
        if (!r.ok) throw new Error(`college list ${r.status}`);
        return r.json();
      })
      .then((rows) => {
        schools = rows.map(([name, city, state, enrollment, slug]) => ({
          unitid: slug,
          name,
          city,
          state,
          enrollment,
          slug,
        }));
        loading = null;
        box.refresh();
      })
      .catch(() => {
        loading = null;
        failed = true;
        if (input.value.trim().length >= 2) box.refresh();
      });
  }

  input.addEventListener("focus", load);
  input.addEventListener("input", load);
  if (document.activeElement === input) load();
})();
