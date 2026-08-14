/* Shared college search: one normalized index + alias map for every picker on the site.
 *
 * Both the Value Check search and the Compare picker load this file, so a nickname like
 * "UCLA" resolves identically in both places. Previously each page had its own matcher and
 * Compare had none, so the homepage could advertise "try UCLA" and Compare would return
 * nothing. Keeping the logic here is the single source of truth; a regression test asserts
 * neither page redefines the alias map inline.
 *
 * Exposes window.TWSearch = { normalize, ALIASES, searchSchools(schools, rawQuery) }.
 * searchSchools takes the schools array explicitly so it holds no page state.
 */
(function (global) {
  // People rarely type a school's exact legal name. We tokenize the query, require every
  // token to match somewhere in the name, then RANK (exact, prefix, word-prefix, contains)
  // and break ties by size, so "baylor" surfaces Baylor University over Baylor College of
  // Medicine and "texas austin" finds UT Austin. This map rewrites the nicknames people
  // actually type into words that appear in the official name.
  const ALIASES = {
    "ut austin": "texas at austin", "u t austin": "texas at austin",
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
    "rpi": "rensselaer", "wustl": "washington university st louis"
  };

  const normalize = str => (str || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  function searchSchools(schools, raw) {
    const term = normalize(raw);
    if (!schools || term.length < 2) return [];
    const expanded = ALIASES[term] || term;
    const tokens = expanded.split(" ").filter(Boolean);
    const scored = [];
    for (const s of schools) {
      const name = normalize(s.name);
      const words = name.split(" ");
      // Every query token must prefix-match a word, or appear as a substring of the name.
      if (!tokens.every(t => words.some(w => w.startsWith(t)) || name.includes(t))) continue;
      let sc;
      if (name === expanded) sc = 0;                               // exact
      else if (name.startsWith(expanded)) sc = 1;                  // name starts with query
      else if (words[0] && words[0].startsWith(tokens[0])) sc = 2; // first word starts with first token
      else if (tokens.every(t => words.some(w => w.startsWith(t)))) sc = 3; // all tokens are word-prefixes
      else sc = 4;                                                 // substring only
      scored.push({ s, sc });
    }
    scored.sort((a, b) => a.sc - b.sc
      || (b.s.enrollment || 0) - (a.s.enrollment || 0)
      || (a.s.name || "").localeCompare(b.s.name || ""));
    return scored.map(x => x.s);
  }

  const api = { normalize, ALIASES, searchSchools };
  if (typeof module !== "undefined" && module.exports) module.exports = api; // node tests
  global.TWSearch = api;
})(typeof window !== "undefined" ? window : globalThis);
