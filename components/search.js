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
 * Enhance mode (November 2026, the homepage): pass `input`, an input already on the page inside a
 * form that works without JavaScript, and the combobox attaches to it instead of building its own
 * label and input. `root` is then the element focus must stay inside (the form), `after` the element
 * the list and status follow (default: the input), and `listLabel` names the list. Enter with no
 * active option is left alone, so the form submits as it would without the script.
 *   data may be a function returning the dataset, or null while it loads (`loadingText`, a string
 *   or a function, is announced; call refresh() when it arrives). `countText(n, limit)` and
 *   `noneText(q)` replace the default status wording. notify(text) sets the status line.
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
      if (this.o.input) {
        this._enhance();
        return;
      }
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

      this._listen();
    }

    // Attach to an input already on the page (see "Enhance mode" above). The label, the input and
    // the form stay as they are; the list, the empty region and the status line follow `after`.
    _enhance() {
      const listId = nextId("tw-listbox");
      const statusId = nextId("tw-status");
      const input = this.o.input;
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-controls", listId);
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("autocomplete", "off");
      const list = document.createElement("ul");
      list.id = listId;
      list.className = "tw-search__list";
      list.setAttribute("role", "listbox");
      list.setAttribute("aria-label", this.o.listLabel || "Suggestions");
      list.hidden = true;
      const empty = document.createElement("div");
      empty.className = "tw-search__empty-region";
      empty.hidden = true;
      const status = document.createElement("p");
      status.id = statusId;
      status.className = "tw-search__status";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      (this.o.after || input).after(list, empty, status);
      this.input = input;
      this.list = list;
      this.emptyRegion = empty;
      this.status = status;
      this.listId = listId;
      this._listen();
    }

    _listen() {
      this.input.addEventListener("input", () => this._onInput());
      this.input.addEventListener("keydown", (e) => this._onKey(e));
      // Close when focus leaves the whole widget (not on option mousedown, which we preventDefault).
      this.root.addEventListener("focusout", (e) => {
        if (!this.root.contains(e.relatedTarget)) this._close();
      });
    }

    // Set the status line, e.g. when the caller's data failed to load.
    notify(text) {
      this.status.textContent = text;
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
      // data may arrive later (enhance mode loads it on first use): until then, say so.
      const data = typeof this.o.data === "function" ? this.o.data() : this.o.data;
      if (data == null) {
        this.results = [];
        this._close();
        const t = this.o.loadingText;
        this.status.textContent = (typeof t === "function" ? t() : t) || "Loading\u2026";
        return;
      }
      // providerOpts lets a caller pass extra provider arguments (e.g. a K-12 state filter from the
      // state chips) that compose with the query. It can be an object or a function returning one.
      const extra = typeof this.o.providerOpts === "function" ? this.o.providerOpts() : this.o.providerOpts;
      this.results = this.o.provider.search(q, { data, limit: this.o.limit, ...extra }) || [];
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
        this.status.textContent = this.o.noneText ? this.o.noneText(q) : `No results for ${q}`;
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
      this.status.textContent = this.o.countText
        ? this.o.countText(n, this.o.limit)
        : `${n} result${n === 1 ? "" : "s"}${n === this.o.limit ? " or more" : ""}`;
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
