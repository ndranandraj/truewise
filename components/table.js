/* Accessible program / comparison table (Stage 3, component B5).
 *
 * Renders a school's programs (or a side-by-side comparison) with coverage stated first, sortable
 * columns, suppressed rows kept visible as "insufficient data", and a mobile layout that keeps every
 * value's column label. Pure rendering + sort; data mapping (parquet -> row shape) happens at
 * adoption in Stage 4/5.
 *
 * Row shape (all figures already computed; nulls mean "not measured"):
 *   { program, credential, earnings, premium, verdict: "pass"|"fail"|"insufficient",
 *     horizon: "4yr_after_completion"|"1yr_after_completion"|null, debt, payback, completers }
 * horizon is null unless a real assessed earnings value is displayed; a "1-year earnings" marker
 * renders beside the earnings figure when horizon is the 1-year window, identically to the static row.
 *
 * Contract:
 *   new ProgramTable(root, {
 *     rows, coverage: { measured, total }, caption, baseline,   // baseline: HS-grad $ for context
 *   })
 *
 * Accessibility: real <table> with <caption>, <th scope>, sortable columns are <button>s inside the
 * header cell with aria-sort on the active column; the premium bar is decorative (aria-hidden) and
 * the number is the real content; suppressed cells read "insufficient data", never 0 or blank.
 */
(function (global) {
  const esc = (s) =>
    (s || "").replace(
      /[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
    );
  const money = (n) => (n == null ? null : "$" + Math.round(n).toLocaleString());
  const INSUF = '<span class="tw-td__insuf">insufficient data</span>';

  // Columns: key, label, kind (num sorts numeric, text sorts alpha), and how to render a cell.
  const COLUMNS = [
    { key: "program", label: "Program", kind: "text", get: (r) => r.program },
    { key: "credential", label: "Degree", kind: "text", get: (r) => r.credential, sortable: false },
    { key: "earnings", label: "Median earnings", kind: "num", get: (r) => r.earnings },
    { key: "premium", label: "vs a high-school grad", kind: "num", get: (r) => r.premium },
    { key: "verdict", label: "Verdict", kind: "text", get: (r) => r.verdict, sortable: false },
    { key: "debt", label: "Median debt", kind: "num", get: (r) => r.debt },
    { key: "payback", label: "Years to repay", kind: "num", get: (r) => r.payback },
    { key: "completers", label: "Recent completers", kind: "num", get: (r) => r.completers },
  ];

  let seq = 0;

  class ProgramTable {
    constructor(root, opts) {
      this.root = root;
      this.o = opts || {};
      this.rows = (this.o.rows || []).slice();
      // remaining = programs not yet loaded (the progressive tail). onMore() fetches them.
      this.remaining = this.o.onMore && this.o.remaining > 0 ? this.o.remaining : 0;
      this.sortKey = null;
      this.sortDir = 1;
      // Unique per instance so the mobile sort control's <label for> points at its own <select>
      // even when a page renders more than one table.
      this.uid = "tw-sort-" + ++seq;
      this._render();
    }

    /* Apply a sort the same way whoever asked for it: the column header button on desktop, or the
       mobile select. Repeating the active key flips direction; a new key starts numeric columns
       high-to-low, which is what someone sorting by earnings means. */
    _applySort(key) {
      if (this.sortKey === key) this.sortDir *= -1;
      else {
        this.sortKey = key;
        this.sortDir = COLUMNS.find((c) => c.key === key).kind === "num" ? -1 : 1;
      }
    }

    /* Visible sort control for phone widths, where the header row is display:none.
     *
     * The header row used to be clipped to 1px instead, which left its six sort buttons focusable:
     * a keyboard user tabbed through six controls they could not see, on every profile page. The
     * header is now genuinely removed at that width (each cell already carries its own column name
     * through data-label) and sorting moves here, where it can be seen. */
    _sortControl() {
      const opts = COLUMNS.filter((c) => c.sortable !== false)
        .map(
          (c) =>
            `<option value="${c.key}"${this.sortKey === c.key ? " selected" : ""}>${esc(c.label)}</option>`,
        )
        .join("");
      const asc = this.sortDir === 1;
      const dirLabel = this.sortKey && COLUMNS.find((c) => c.key === this.sortKey).kind === "num"
        ? asc ? "Lowest first" : "Highest first"
        : asc ? "A to Z" : "Z to A";
      return (
        `<div class="tw-sort">` +
        `<label class="tw-sort__label" for="${this.uid}">Sort by</label>` +
        `<select class="tw-sort__select" id="${this.uid}">` +
        `<option value=""${this.sortKey ? "" : " selected"}>Table order</option>${opts}</select>` +
        (this.sortKey
          ? `<button type="button" class="tw-sort__dir">${dirLabel}</button>`
          : "") +
        `</div>`
      );
    }

    _verdictCell(r) {
      if (r.verdict === "insufficient") return `<span class="tw-verdict tw-verdict--insuf">insufficient data</span>`;
      if (r.verdict === "pass") return `<span class="tw-verdict tw-verdict--pass">clears the bar</span>`;
      return `<span class="tw-verdict tw-verdict--fail">falls short</span>`;
    }

    _premiumCell(r) {
      if (r.premium == null) return INSUF;
      const sign = r.premium >= 0 ? "+" : "-";
      const mag = money(Math.abs(r.premium));
      // Decorative bar; the signed number is the accessible content.
      const cls = r.premium >= 0 ? "pos" : "neg";
      return `<span class="tw-prem"><span class="tw-prem__bar tw-prem__bar--${cls}" aria-hidden="true"></span>` +
        `<span class="tw-prem__val">${sign}${esc(mag)}</span></span>`;
    }

    _num(v, fmt) {
      if (v == null) return INSUF;
      return esc(fmt ? fmt(v) : String(v));
    }

    _sorted() {
      if (!this.sortKey) return this.rows;
      const col = COLUMNS.find((c) => c.key === this.sortKey);
      const rows = this.rows.slice();
      rows.sort((a, b) => {
        const av = col.get(a);
        const bv = col.get(b);
        // Insufficient/null always sinks to the bottom regardless of direction.
        const an = av == null;
        const bn = bv == null;
        if (an && bn) return 0;
        if (an) return 1;
        if (bn) return -1;
        if (col.kind === "num") return (av - bv) * this.sortDir;
        return String(av).localeCompare(String(bv)) * this.sortDir;
      });
      return rows;
    }

    _render() {
      const cov = this.o.coverage;
      const covLine = cov
        ? `<p class="tw-table__coverage"><b>${cov.measured} of ${cov.total}</b> programs could be assessed` +
          ` <span class="tw-table__covnote">${Math.round((100 * cov.measured) / cov.total)}% have an earnings verdict</span></p>`
        : "";
      const baseLine = this.o.baseline
        ? `<p class="tw-table__baseline">Compared with a typical high-school graduate earning about ${esc(money(this.o.baseline))}/yr.</p>`
        : "";

      const head = COLUMNS.map((c) => {
        const sortable = c.sortable !== false;
        const active = this.sortKey === c.key;
        // aria-sort only belongs on a sortable column; active shows the direction, others "none".
        const ariaSort = sortable ? ` aria-sort="${active ? (this.sortDir === 1 ? "ascending" : "descending") : "none"}"` : "";
        const inner = sortable
          ? `<button type="button" class="tw-th__sort${active ? " is-active" : ""}" data-key="${c.key}">` +
            `${esc(c.label)}<span class="tw-th__arrow" aria-hidden="true">${active ? (this.sortDir === 1 ? " ▲" : " ▼") : ""}</span></button>`
          : esc(c.label);
        return `<th scope="col" class="tw-th tw-th--${c.kind}"${ariaSort}>${inner}</th>`;
      }).join("");

      const body = this._sorted()
        .map((r) => {
          const suppressed = r.verdict === "insufficient";
          const cells = [
            `<th scope="row" class="tw-td tw-td--program" data-label="Program">${esc(r.program)}</th>`,
            `<td class="tw-td" data-label="Degree">${esc(r.credential || "")}</td>`,
            `<td class="tw-td tw-td--num" data-label="Median earnings">${this._num(r.earnings, money)}` +
              (r.horizon === "1yr_after_completion" && r.earnings != null
                ? ' <span class="tw-oneyr">1-year earnings</span>'
                : "") +
              `</td>`,
            `<td class="tw-td tw-td--num" data-label="vs a high-school grad">${this._premiumCell(r)}</td>`,
            `<td class="tw-td" data-label="Verdict">${this._verdictCell(r)}</td>`,
            `<td class="tw-td tw-td--num" data-label="Median debt">${this._num(r.debt, money)}</td>`,
            `<td class="tw-td tw-td--num" data-label="Years to repay">${this._num(r.payback, (v) => v.toFixed(1) + " yrs")}</td>`,
            `<td class="tw-td tw-td--num" data-label="Recent completers">${this._num(r.completers, (v) => v.toLocaleString())}</td>`,
          ].join("");
          return `<tr class="tw-tr${suppressed ? " tw-tr--insuf" : ""}">${cells}</tr>`;
        })
        .join("");

      // Progressive tail: when programs remain unloaded, offer a "Show all N" control. Loading them
      // appends to this.rows so sorting and filtering then operate over the complete set.
      const more =
        this.remaining > 0
          ? `<button type="button" class="tw-showall" data-count="${this.remaining}">` +
            `Show all ${this.rows.length + this.remaining} programs</button>`
          : "";

      this.root.innerHTML =
        covLine +
        baseLine +
        this._sortControl() +
        `<div class="tw-table__scroll" tabindex="0" role="region" aria-label="Programs and earnings"><table class="tw-table">` +
        (this.o.caption ? `<caption class="tw-table__caption">${esc(this.o.caption)}</caption>` : "") +
        `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` +
        more +
        `<p class="tw-table__status" role="status" aria-live="polite"></p>`;

      const showAll = this.root.querySelector(".tw-showall");
      if (showAll) {
        showAll.addEventListener("click", async () => {
          showAll.disabled = true;
          showAll.textContent = "Loading...";
          try {
            const extra = await this.o.onMore();
            this.rows = this.rows.concat(extra || []);
            this.remaining = 0;
            this._render();
            const status = this.root.querySelector(".tw-table__status");
            if (status) status.textContent = `All ${this.rows.length} programs shown.`;
          } catch (e) {
            showAll.disabled = false;
            showAll.textContent = "Could not load. Try again";
          }
        });
      }

      this.root.querySelectorAll(".tw-th__sort").forEach((btn) =>
        btn.addEventListener("click", () => {
          const key = btn.dataset.key;
          this._applySort(key);
          // Re-rendering replaces the markup and would drop focus to <body>; restore it to the same
          // sort button so a keyboard or screen-reader user is not thrown back to the page top.
          this._render();
          const restored = this.root.querySelector(`.tw-th__sort[data-key="${key}"]`);
          if (restored) restored.focus();
        }),
      );

      // Mobile sort control. Same focus-restoration reasoning as the header buttons above.
      const sortSel = this.root.querySelector(".tw-sort__select");
      if (sortSel) {
        sortSel.addEventListener("change", () => {
          const key = sortSel.value;
          if (!key) {
            this.sortKey = null;
            this.sortDir = 1;
          } else if (this.sortKey !== key) {
            this.sortKey = key;
            this.sortDir = COLUMNS.find((c) => c.key === key).kind === "num" ? -1 : 1;
          }
          this._render();
          const restored = this.root.querySelector(".tw-sort__select");
          if (restored) restored.focus();
          const status = this.root.querySelector(".tw-table__status");
          if (status) {
            const col = COLUMNS.find((c) => c.key === this.sortKey);
            status.textContent = col ? `Sorted by ${col.label}.` : "Table order restored.";
          }
        });
      }
      const sortDir = this.root.querySelector(".tw-sort__dir");
      if (sortDir) {
        sortDir.addEventListener("click", () => {
          this.sortDir *= -1;
          this._render();
          const restored = this.root.querySelector(".tw-sort__dir");
          if (restored) restored.focus();
        });
      }
    }
  }

  const api = { ProgramTable, COLUMNS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.TWTable = api;
})(typeof window !== "undefined" ? window : globalThis);
