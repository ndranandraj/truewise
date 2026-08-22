/* Accessible search combobox shell (Stage 3, component B1).
 *
 * One interaction layer over the two domain providers from Stage 0.2 (CollegeSearchProvider,
 * K12SearchProvider in site/assets/college-search.js). The shell owns ARIA, keyboard, the live
 * region, and result rendering; the provider owns ranking and fields. Nothing here knows whether it
 * is searching colleges or schools.
 *
 * Contract:
 *   new SearchCombobox(root, {
 *     provider,                 // object with .search(q, opts) -> [{id, title, meta, why}]
 *     data,                     // dataset passed to the provider
 *     label,                    // accessible label for the input
 *     placeholder,
 *     onSelect(result),         // required
 *     emptyHTML(query),         // optional: markup for the no-result state
 *     minChars = 2,
 *     limit = 25,
 *   })
 *
 * Implements the WAI-ARIA combobox-with-listbox pattern: focus stays in the input and the active
 * option is tracked with aria-activedescendant, so a screen reader announces the option without
 * moving focus. Keys: Down/Up move, Home/End jump, Enter selects, Escape closes then clears.
 */
(function (global) {
  let _id = 0;
  const nextId = (p) => `${p}-${++_id}`;

  const esc = (s) =>
    (s || "").replace(
      /[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
    );

  class SearchCombobox {
    constructor(root, opts) {
      if (!opts || !opts.provider || typeof opts.onSelect !== "function") {
        throw new Error("SearchCombobox needs a provider and an onSelect callback");
      }
      this.root = root;
      this.o = Object.assign({ minChars: 2, limit: 25 }, opts);
      this.results = [];
      this.active = -1;
      this.open = false;
      this._debounce = null;
      this._build();
    }

    _build() {
      const listId = nextId("tw-listbox");
      const labelId = nextId("tw-label");
      const statusId = nextId("tw-status");
      this.root.classList.add("tw-search");
      this.root.innerHTML = `
        <label id="${labelId}" class="tw-search__label" for="${listId}-input">${esc(this.o.label || "Search")}</label>
        <div class="tw-search__box">
          <svg class="tw-search__icon" width="20" height="20" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
          <input id="${listId}-input" class="tw-search__input" type="text" autocomplete="off"
                 role="combobox" aria-expanded="false" aria-controls="${listId}"
                 aria-autocomplete="list" aria-labelledby="${labelId}"
                 placeholder="${esc(this.o.placeholder || "")}" />
        </div>
        <ul id="${listId}" class="tw-search__list" role="listbox" aria-labelledby="${labelId}" hidden></ul>
        <div class="tw-search__empty-region" hidden></div>
        <p id="${statusId}" class="tw-search__status" role="status" aria-live="polite"></p>`;

      this.input = this.root.querySelector(".tw-search__input");
      this.list = this.root.querySelector(".tw-search__list");
      this.emptyRegion = this.root.querySelector(".tw-search__empty-region");
      this.status = this.root.querySelector(".tw-search__status");
      this.listId = listId;

      this.input.addEventListener("input", () => this._onInput());
      this.input.addEventListener("keydown", (e) => this._onKey(e));
      // Close when focus leaves the whole widget (not on option mousedown, which we preventDefault).
      this.root.addEventListener("focusout", (e) => {
        if (!this.root.contains(e.relatedTarget)) this._close();
      });
    }

    _onInput() {
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => this._run(), 140);
    }

    _run() {
      const q = this.input.value.trim();
      if (q.length < this.o.minChars) {
        this.results = [];
        this._close();
        this.emptyRegion.hidden = true;
        this.emptyRegion.innerHTML = "";
        this.status.textContent = "";
        return;
      }
      // providerOpts lets a caller pass extra provider arguments (e.g. a K-12 state filter from the
      // state chips) that compose with the query. It can be an object or a function returning one.
      const extra = typeof this.o.providerOpts === "function" ? this.o.providerOpts() : this.o.providerOpts;
      this.results =
        this.o.provider.search(q, { data: this.o.data, limit: this.o.limit, ...extra }) || [];
      this.active = -1;
      this._render(q);
    }

    // Re-run the current query, e.g. after a composed filter (state chips) changes providerOpts.
    refresh() {
      this._run();
    }

    _render(q) {
      if (!this.results.length) {
        // The no-results message and its onward links live OUTSIDE the listbox: a link nested inside
        // a role=option (even a disabled one) is a nested-interactive violation and is exposed to
        // assistive tech as disabled. The listbox closes; the empty region opens as a sibling.
        const empty = this.o.emptyHTML ? this.o.emptyHTML(q) : `No matches for "${esc(q)}".`;
        this.list.innerHTML = "";
        this._close();
        this.emptyRegion.innerHTML = `<div class="tw-search__empty">${empty}</div>`;
        this.emptyRegion.hidden = false;
        this.status.textContent = `No results for ${q}`;
        return;
      }
      this.emptyRegion.hidden = true;
      this.emptyRegion.innerHTML = "";
      this.list.innerHTML = this.results
        .map((r, i) => {
          const why = r.why ? ` <span class="tw-search__why">matched on ${esc(r.why)}</span>` : "";
          const meta = r.meta ? ` <span class="tw-search__meta">${esc(r.meta)}</span>` : "";
          return `<li id="${this.listId}-opt-${i}" class="tw-search__opt" role="option" aria-selected="false">
            <span class="tw-search__title">${esc(r.title)}</span>${meta}${why}</li>`;
        })
        .join("");
      // Mouse selection: preventDefault on mousedown so the input keeps focus, then select on click.
      this.list.querySelectorAll(".tw-search__opt").forEach((el, i) => {
        el.addEventListener("mousedown", (e) => e.preventDefault());
        el.addEventListener("click", () => this._select(i));
      });
      const n = this.results.length;
      this.status.textContent = `${n} result${n === 1 ? "" : "s"}${n === this.o.limit ? " or more" : ""}`;
      this._show();
    }

    _show() {
      this.open = true;
      this.list.hidden = false;
      this.input.setAttribute("aria-expanded", "true");
    }

    _close() {
      this.open = false;
      this.list.hidden = true;
      this.input.setAttribute("aria-expanded", "false");
      this.input.removeAttribute("aria-activedescendant");
      this.active = -1;
    }

    _setActive(i) {
      const opts = this.list.querySelectorAll(".tw-search__opt");
      if (!opts.length) return;
      this.active = (i + opts.length) % opts.length;
      opts.forEach((el, idx) => {
        const on = idx === this.active;
        el.setAttribute("aria-selected", on ? "true" : "false");
        el.classList.toggle("is-active", on);
        if (on) {
          this.input.setAttribute("aria-activedescendant", el.id);
        }
      });
      // scrollIntoView is a stub that throws under jsdom; keep it out of the aria loop and never let
      // it break state. Run it after every option's aria is settled.
      if (this.active >= 0) {
        try {
          opts[this.active].scrollIntoView({ block: "nearest" });
        } catch (_) {
          /* not implemented in test env */
        }
      }
    }

    _onKey(e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!this.open) this._run();
        else this._setActive(this.active + 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (this.open) this._setActive(this.active - 1);
      } else if (e.key === "Home" && this.open) {
        e.preventDefault();
        this._setActive(0);
      } else if (e.key === "End" && this.open) {
        e.preventDefault();
        this._setActive(this.list.querySelectorAll(".tw-search__opt").length - 1);
      } else if (e.key === "Enter") {
        if (this.open && this.active >= 0) {
          e.preventDefault();
          this._select(this.active);
        }
      } else if (e.key === "Escape") {
        if (this.open) {
          e.preventDefault();
          this._close();
        } else {
          this.input.value = "";
          this.status.textContent = "";
        }
      }
    }

    _select(i) {
      const r = this.results[i];
      if (!r) return;
      this.input.value = r.title;
      this._close();
      this.o.onSelect(r);
    }
  }

  const api = { SearchCombobox };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.TWSearchUI = api;
})(typeof window !== "undefined" ? window : globalThis);
