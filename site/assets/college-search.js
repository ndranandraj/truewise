/* Shared search matching for Truewise.
 *
 * Architecture (Stage 0.2 decision): one accessible search *interface* is shared across Value Check,
 * Compare and K-12, but the *matching* is domain specific. Colleges rank on name, aliases, city,
 * state, control and size; K-12 needs name plus state and district because 194 schools are called
 * some variant of "Central High School". Wrapping one matcher around both datasets would make each
 * worse, so this file exposes two providers behind one contract:
 *
 *   provider.search(query, { data, limit, state }) -> [{ id, title, meta, why, raw }]
 *
 * `why` names the field that caused the match, so the interface can tell a person why a result
 * appeared (an alias, a city) rather than looking arbitrary.
 *
 * Ranking notes for colleges, all driven by the versioned gold set in tests/search_gold_set.json:
 *   - Points, not tiers. The old tier system ranked "Berkeley City College" above "University of
 *     California-Berkeley" because the former's FIRST word matched, and no amount of size could
 *     overcome a better name position. Now a word-boundary hit scores the same wherever it sits in
 *     the name, and prominence breaks the tie, which matches what people mean by "berkeley".
 *   - Substring matching requires 4+ characters. "uva" used to match "N-uva-ni Institute".
 *   - Typo tolerance uses Damerau-Levenshtein distance 1 on tokens of 6+ characters, so
 *     "univeristy" finds "university" while "asdfghjkl" still finds nothing.
 */
(function (global) {
  // Nicknames people type that do not appear in the official name.
  const ALIASES = {
    "ut austin": "the university of texas at austin", "u t austin": "texas at austin",
    "uc berkeley": "university of california berkeley", "cal berkeley": "university of california berkeley",
    "ucla": "university of california los angeles", "uc la": "university of california los angeles",
    "ucsd": "university of california san diego", "uc san diego": "university of california san diego",
    "ucsb": "university of california santa barbara", "uc davis": "university of california davis",
    "uc irvine": "university of california irvine", "uci": "university of california irvine",
    "ucsf": "university of california san francisco", "uc riverside": "university of california riverside",
    "usc": "university of southern california", "nyu": "new york university",
    "mit": "massachusetts institute of technology", "caltech": "california institute of technology",
    "upenn": "pennsylvania", "penn state": "pennsylvania state",
    "psu": "pennsylvania state", "osu": "ohio state",
    "umich": "michigan ann arbor", "u mich": "michigan ann arbor",
    "unc": "north carolina chapel hill", "uconn": "connecticut",
    "umass": "massachusetts amherst", "asu": "arizona state",
    "fsu": "florida state", "lsu": "louisiana state",
    "byu": "brigham young", "smu": "southern methodist",
    "tcu": "texas christian", "ucf": "central florida",
    "usf": "south florida", "vt": "virginia polytechnic",
    "virginia tech": "virginia polytechnic", "georgia tech": "georgia institute of technology",
    "gt": "georgia institute of technology", "texas a&m": "texas a m university",
    "texas a and m": "texas a m university", "a&m": "texas a m university",
    "pitt": "pittsburgh", "cal poly": "california polytechnic",
    "rpi": "rensselaer", "wustl": "washington university st louis",
    // Added after the gold set caught them returning noise or nothing.
    "uva": "university of virginia main campus", "u va": "university of virginia main campus",
    "uw": "university of washington seattle", "cu boulder": "university of colorado boulder",
    "ou": "university of oklahoma norman", "uga": "university of georgia",
    "ufl": "university of florida", "uf": "university of florida",
    "utk": "university of tennessee knoxville", "mizzou": "university of missouri columbia",
    "unl": "university of nebraska lincoln", "ttu": "texas tech university",
    "uh": "university of houston", "vcu": "virginia commonwealth university",
  };

  const normalize = (str) =>
    (str || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  /* Damerau-Levenshtein capped at `max`; returns max+1 when it certainly exceeds it. Used only for
     tokens of 6+ characters where a single typo is plausible, so the cost stays negligible. */
  function editDistance(a, b, max) {
    if (a === b) return 0;
    if (Math.abs(a.length - b.length) > max) return max + 1;
    const prev2 = [], prev = [], cur = [];
    for (let j = 0; j <= b.length; j++) prev[j] = j;
    for (let i = 1; i <= a.length; i++) {
      cur[0] = i;
      let best = cur[0];
      for (let j = 1; j <= b.length; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
        // transposition
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          cur[j] = Math.min(cur[j], prev2[j - 2] + cost);
        }
        if (cur[j] < best) best = cur[j];
      }
      if (best > max) return max + 1;
      for (let j = 0; j <= b.length; j++) { prev2[j] = prev[j]; prev[j] = cur[j]; }
    }
    return prev[b.length];
  }

  const FUZZY_MIN = 6;   // only try typo tolerance on tokens this long
  const SUBSTR_MIN = 4;  // bare substring matching needs at least this many characters

  /* Does `token` match any word in `words`? Returns the match kind, or null. */
  function tokenHit(token, words, haystack) {
    for (const w of words) if (w.startsWith(token)) return "prefix";
    if (token.length >= SUBSTR_MIN && haystack.includes(token)) return "substring";
    if (token.length >= FUZZY_MIN) {
      for (const w of words) {
        if (Math.abs(w.length - token.length) > 1) continue;
        if (editDistance(w, token, 1) <= 1) return "fuzzy";
      }
    }
    return null;
  }

  /* Size is a proxy for "the one most people mean". Log-scaled so a very large school edges out a
     small one with the same name position, without letting size dominate the match itself. */
  const prominence = (n) => (n && n > 0 ? Math.log10(n) * 12 : 0);

  const CollegeSearchProvider = {
    name: "college",
    search(rawQuery, opts = {}) {
      const data = opts.data || [];
      const limit = opts.limit || 25;
      const term = normalize(rawQuery);
      if (term.length < 2) return [];
      const aliased = ALIASES[term];
      const expanded = aliased || term;
      const tokens = expanded.split(" ").filter(Boolean);

      const out = [];
      for (const s of data) {
        const name = normalize(s.name);
        const words = name.split(" ");
        const city = normalize(s.city);
        const state = normalize(s.state);
        const place = (city + " " + state).trim();
        const placeWords = place.split(" ").filter(Boolean);

        // Every token must land somewhere: the name, or the city/state.
        let nameHits = 0, placeHits = 0, fuzzy = false, ok = true;
        for (const t of tokens) {
          const inName = tokenHit(t, words, name);
          if (inName) {
            nameHits++;
            if (inName === "fuzzy") fuzzy = true;
            continue;
          }
          const inPlace = tokenHit(t, placeWords, place);
          if (inPlace) { placeHits++; continue; }
          ok = false;
          break;
        }
        if (!ok) continue;

        let score = 0;
        let why = aliased ? "alias" : "name";
        if (name === expanded) score = 1000;
        // "Starts with" only earns a bonus for multi-word queries, where it signals a real prefix
        // phrase. For a single word it would rank "Berkeley City College" above "University of
        // California-Berkeley" purely for word order, which is not what people mean by "berkeley";
        // single-word queries fall through to the word-boundary tier and let prominence decide.
        else if (tokens.length > 1 && name.startsWith(expanded)) score = 500;
        // A word-boundary hit counts the same wherever it appears, so "Berkeley" in
        // "University of California-Berkeley" is not punished for being last.
        else if (tokens.every((t) => words.some((w) => w.startsWith(t)))) score = 300;
        else if (nameHits === tokens.length) score = 200;
        else score = 120;                       // matched partly on city or state
        if (placeHits && !nameHits) why = "city";
        else if (placeHits) why = why === "alias" ? "alias" : "name and city";
        if (fuzzy) { score -= 40; why = "close spelling"; }

        out.push({ s, score: score + prominence(s.enrollment) });
      }

      out.sort((a, b) => b.score - a.score || (a.s.name || "").localeCompare(b.s.name || ""));
      return out.slice(0, limit).map(({ s, score }) => ({
        id: s.unitid,
        title: s.name,
        meta: [s.city, s.state].filter(Boolean).join(", "),
        why: score >= 1000 ? "name" : undefined,
        raw: s,
      }));
    },
  };

  const K12SearchProvider = {
    name: "k12",
    /* K-12 names repeat heavily (194 "Central High School"), so state and district are first-class
       filters rather than afterthoughts, and the caller can narrow instead of scrolling. */
    search(rawQuery, opts = {}) {
      const data = opts.data || [];
      const limit = opts.limit || 25;
      const term = normalize(rawQuery);
      if (term.length < 3) return [];
      const tokens = term.split(" ").filter(Boolean);

      const out = [];
      for (const s of data) {
        if (opts.state && s.s !== opts.state) continue;
        if (opts.district && normalize(s.d) !== normalize(opts.district)) continue;
        const name = normalize(s.n);
        const words = name.split(" ");

        // Name only. District is a FILTER, never free-text match territory: letting query tokens
        // match the district inflated "central high school" from 194 to 696 results, because New
        // York alone has hundreds of "... Central School District" districts whose schools then
        // matched "central". Narrowing belongs to opts.state / opts.district.
        let ok = true;
        for (const t of tokens) {
          if (!tokenHit(t, words, name)) { ok = false; break; }
        }
        if (!ok) continue;

        const score = name === term ? 1000 : name.startsWith(term) ? 500 : 300;
        out.push({ s, score, why: "name" });
      }
      out.sort((a, b) => b.score - a.score || (a.s.n || "").localeCompare(b.s.n || ""));
      return out.slice(0, limit).map(({ s, why }) => ({
        id: s.k,
        title: s.n,
        meta: [s.d, s.s].filter(Boolean).join(", "),
        why,
        raw: s,
      }));
    },

    /* States present in a result set, so the interface can offer narrowing. */
    statesFor(rawQuery, opts = {}) {
      const hits = this.search(rawQuery, { ...opts, limit: 1e6 });
      const counts = {};
      hits.forEach((h) => { counts[h.raw.s] = (counts[h.raw.s] || 0) + 1; });
      return Object.entries(counts).sort((a, b) => b[1] - a[1]);
    },
  };

  // Backwards compatible shim: the shipped pages still call searchSchools(list, query) and expect
  // raw school objects. They migrate to the provider contract when the shared UI lands (Stage 5).
  const searchSchools = (schools, raw) =>
    CollegeSearchProvider.search(raw, { data: schools, limit: 25 }).map((r) => r.raw);

  const api = { normalize, ALIASES, searchSchools, CollegeSearchProvider, K12SearchProvider, editDistance };
  if (typeof module !== "undefined" && module.exports) module.exports = api; // node tests
  global.TWSearch = api;
})(typeof window !== "undefined" ? window : globalThis);
