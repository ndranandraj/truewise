/* Stage 3 UI components: the smaller shared pieces (B2, B3, B4, B6, B7, B8, B9, B11, B12, B13, B14).
 *
 * Render helpers return HTML strings; interactive pieces (StateChips, Filters, Disclosure) are small
 * classes. All built in isolation against the final palette; adopted on live routes in Stage 5.
 * Every status/label carries text, never colour alone, and suppressed data always reads
 * "insufficient data".
 */
(function (global) {
  const esc = (s) =>
    (s || "").replace(
      /[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
    );

  // ---- B8 status pill: text + colour, never colour alone ----
  function statusPill(state) {
    const map = {
      pass: ["tw-pill--pass", "clears the bar"],
      fail: ["tw-pill--fail", "falls short"],
      insufficient: ["tw-pill--insuf", "insufficient data"],
      caution: ["tw-pill--caution", "provisional"],
    };
    const [cls, label] = map[state] || map.insufficient;
    return `<span class="tw-pill ${cls}">${esc(label)}</span>`;
  }

  // ---- B14 suppressed cell/value ----
  function suppressed() {
    return `<span class="tw-insuf">insufficient data</span>`;
  }

  // ---- B6 coverage note (computed by the caller, never hard-coded) ----
  function coverageNote(measured, total) {
    if (!total) return `<p class="tw-coverage">${suppressed()}</p>`;
    const pct = Math.round((100 * measured) / total);
    const low = pct < 50 ? " tw-coverage--low" : "";
    return (
      `<p class="tw-coverage${low}"><b>${measured} of ${total}</b> programs measured ` +
      `<span class="tw-coverage__note">${pct}% have earnings data</span></p>`
    );
  }

  // ---- B7 source + vintage note ----
  function sourceNote({ source, release, vintage, note }) {
    const bits = [source, release ? `release ${release}` : "", vintage ? `data ${vintage}` : ""]
      .filter(Boolean)
      .map(esc)
      .join(", ");
    return `<p class="tw-source">Source: ${bits}.${note ? " " + esc(note) : ""}</p>`;
  }

  // ---- B3 empty state: says what was searched, routes onward, never a dead end ----
  function emptyState(query, links) {
    const routes = (links || [])
      .map((l) => `<a href="${esc(l.href)}">${esc(l.label)}</a>`)
      .join(" · ");
    return (
      `<div class="tw-empty"><p>No matches for <b>${esc(query)}</b>.</p>` +
      (routes ? `<p class="tw-empty__routes">Try: ${routes}</p>` : "") +
      `</div>`
    );
  }

  // ---- B12 loading skeleton: reserves space, no spinner, announced politely ----
  function skeleton(rows = 3) {
    const bars = Array.from({ length: rows }, () => `<div class="tw-skel__row"></div>`).join("");
    return `<div class="tw-skel" role="status" aria-live="polite" aria-busy="true"><span class="tw-visually-hidden">Loading</span>${bars}</div>`;
  }

  // ---- B13 error state: says what failed + a way forward, never blank ----
  function errorState(message, retry) {
    const action = retry ? ` <a href="${esc(retry.href)}">${esc(retry.label)}</a>` : "";
    return `<div class="tw-error" role="alert"><p>${esc(message)}${action}</p></div>`;
  }

  // ---- B4 state chips: narrow a large match set; announce the narrowed count ----
  class StateChips {
    constructor(root, { states, total, onPick, live }) {
      this.root = root;
      this.onPick = onPick;
      this.active = null;
      this.live = live || null; // optional live region to announce narrowing
      this._render(states, total);
    }
    _render(states, total) {
      this.root.className = "tw-chips";
      this.root.innerHTML =
        `<span class="tw-chips__label">Narrow by state</span>` +
        `<button type="button" class="tw-chip is-on" data-st="" aria-pressed="true">All ${total}</button>` +
        states
          .map(
            ([st, n]) =>
              `<button type="button" class="tw-chip" data-st="${esc(st)}" aria-pressed="false">${esc(st)} ${n}</button>`,
          )
          .join("");
      this.root.querySelectorAll(".tw-chip").forEach((b) =>
        b.addEventListener("click", () => this._pick(b)),
      );
    }
    _pick(btn) {
      this.active = btn.dataset.st || null;
      this.root.querySelectorAll(".tw-chip").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      if (this.live) this.live.textContent = this.active ? `Narrowed to ${this.active}` : "Showing all states";
      this.onPick(this.active);
    }
  }

  // ---- B9 filters: sort + insufficient toggle, announce the resulting count ----
  class Filters {
    constructor(root, { sorts, onChange, live }) {
      this.root = root;
      this.onChange = onChange;
      this.live = live || null;
      this.state = { sort: (sorts[0] || {}).key || null, showInsufficient: true };
      this._render(sorts);
    }
    _render(sorts) {
      const sid = "tw-sort-" + Math.random().toString(36).slice(2, 7);
      const tid = "tw-insuf-" + Math.random().toString(36).slice(2, 7);
      this.root.className = "tw-filters";
      this.root.innerHTML =
        `<label class="tw-filters__label" for="${sid}">Sort by</label>` +
        `<select id="${sid}" class="tw-filters__select">` +
        sorts.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("") +
        `</select>` +
        `<label class="tw-filters__check"><input id="${tid}" type="checkbox" checked /> Show programs with insufficient data</label>`;
      this.sel = this.root.querySelector("select");
      this.toggle = this.root.querySelector('input[type="checkbox"]');
      this.sel.addEventListener("change", () => this._change());
      this.toggle.addEventListener("change", () => this._change());
    }
    _change() {
      this.state = { sort: this.sel.value, showInsufficient: this.toggle.checked };
      const r = this.onChange(this.state);
      if (this.live && typeof r === "number") {
        this.live.textContent = `${r} program${r === 1 ? "" : "s"} shown`;
      }
    }
  }

  // ---- B11 disclosure: progressive enhancement of native <details>, Escape collapses ----
  function enhanceDisclosure(details) {
    details.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && details.open) {
        details.open = false;
        details.querySelector("summary").focus();
      }
    });
    return details;
  }

  const api = {
    statusPill,
    suppressed,
    coverageNote,
    sourceNote,
    emptyState,
    skeleton,
    errorState,
    StateChips,
    Filters,
    enhanceDisclosure,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.TWUI = api;
})(typeof window !== "undefined" ? window : globalThis);
