/* Canonical profile progressive enhancement (Stage 4.2).
 *
 * The server ships a static, crawlable program table (the N largest programs) plus a JSON island of
 * that same data and a tail URL for the rest. This script upgrades the static table into the
 * interactive ProgramTable (sortable, with the mobile layout), and wires "Show all N" to fetch the
 * tail and merge it so sorting then covers every program. With JavaScript off, the static table
 * stands on its own; nothing here is required to read the data.
 *
 * Page contract:
 *   <div data-tw-profile data-tail="programs-tail.json" data-remaining="339">
 *     <script type="application/json" class="tw-profile-data">
 *       {"rows":[...150...],"coverage":{"measured":184,"total":489},"baseline":36498,"caption":"..."}
 *     </script>
 *     <div class="tw-profile-static"> ...server-rendered table (replaced on enhance)... </div>
 *   </div>
 */
(function (global) {
  function enhance(root, opts = {}) {
    const dataEl = root.querySelector("script.tw-profile-data");
    if (!dataEl || !global.TWTable) return; // no data or component: leave the static table in place
    let data;
    try {
      data = JSON.parse(dataEl.textContent);
    } catch (e) {
      return; // malformed island: keep the static table
    }
    const tailUrl = root.dataset.tail;
    const remaining = parseInt(root.dataset.remaining || "0", 10);
    const mount = root.querySelector(".tw-profile-static") || root;

    // fetch fn is injectable for testing; defaults to window.fetch.
    const doFetch = opts.fetch || ((u) => global.fetch(u).then((r) => r.json()));

    new global.TWTable.ProgramTable(mount, {
      rows: data.rows || [],
      coverage: data.coverage,
      baseline: data.baseline,
      caption: data.caption,
      remaining: tailUrl ? remaining : 0,
      onMore: tailUrl
        ? async () => {
            const json = await doFetch(new URL(tailUrl, opts.base || location.href).href);
            return json.programs || [];
          }
        : undefined,
    });
  }

  // Enhance every profile block on the page.
  function enhanceAll(opts) {
    document.querySelectorAll("[data-tw-profile]").forEach((el) => enhance(el, opts));
  }

  const api = { enhance, enhanceAll };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.TWProfile = api;
  if (typeof document !== "undefined" && !global.__TW_PROFILE_NO_AUTO) {
    if (document.readyState !== "loading") enhanceAll();
    else document.addEventListener("DOMContentLoaded", () => enhanceAll());
  }
})(typeof window !== "undefined" ? window : globalThis);
