# Review bundle, 9 October 2026

Everything here is a copy, so it can be read without access to the working tree.

## Parser (branch `fvtge-parser`, local, unpushed)

Exact tip for every result below: `3c1097f8e1ed45d5d854ce79afac4497b5c7bd75`.
Commits on top of `main` (`6058655`): `14caf2d` (ruff excludes .review-work), `02160be` (the
parser), `3c1097f` (review changes). See `branch-log.txt`.

| File | What |
|---|---|
| `fvtge-parser-3c1097f.patch` | The whole branch diff against `main` |
| `build_fvtge_source.py`, `test_fvtge_source.py` | The parser and its tests at the tip |
| `parser-tests-3c1097f.txt` | `pytest -v` on the tip: 26 passed. 24 are synthetic and run in CI; the 2 real-file tests ran here because ED's files are present locally, and are skipped in CI |
| `parser-real-files-3c1097f.txt` | Both real releases through the CLI on the tip: input SHA-256s; August equals `published/fvtge_reporting.parquet` in values, column names and types, with no 2026 columns; October 4,674 rows and distinct OPEIDs, 1,396 / 478 / 1,007 / 633; October without `--out` refused before reading; `published/` unchanged |

## Monitor contract (not built)

`fvtge-monitor-contract.md` is version 3: Anand's answers to the four questions (weekly; daily
from 1 to 31 January 2027 and during a review; monthly from February with a 45-day silence
threshold; both cycles reported separately; separate issues), and a watchdog outside GitHub's
schedules. `-v1.md` and `-v2.md` are the earlier versions. The probe record is
`probe-run-37858847524.md`.

## Prototype J, visual recheck

`visual-results.json` and the PNGs: Chromium 153, Firefox 155 and Firefox at native 200% text, 30
of 30 checks, rerun on 9 October against the page now served at
http://localhost:8787/_proto/fvtge/finding.html (served `finding.html` SHA-256 begins `129a5c7e`).
Safari, VoiceOver and real-device checks are not done.
