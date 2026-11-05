# Parser fixes for draft PR #17: evidence for `3c3a083`

Branch `fvtge-parser`, commit `3c3a083` on `3c1097f`, pushed to draft PR #17 on 4 November 2026 (still
draft, not merged). This folder is also on the review branch `review/fvtge-parser-evidence`, which is
not for merge. Built and tested in a separate worktree, so the shared checkout (on another session's
branch) was not touched. Tests ran on 11 October 2026 on this Mac: Python 3.14.2, DuckDB 1.5.4,
openpyxl from requirements. `<scratch>` in these files stands for a local temporary folder.

## The three review findings

| Finding | Fix | Tests (each also checks the existing output is unchanged and no temporary file is left) |
|---|---|---|
| 1. Frequency validation could miss a whole group, and a later duplicate overwrote an earlier contradictory one | Each release names its header and counted groups (`freq_header`, `freq_groups`; August has no `control` group, October does). A missing group, an unexpected group, or an outcome listed twice is refused. Identifier rows (N/A, once each) and notes are the only other rows; a note ends a group. Counts must be whole numbers and percentages numbers. | `test_the_frequencies_sheet_has_exactly_the_releases_groups` (12 cases): `program2526`, `control` and August `num_miss` removed; a complete, consistent `control` group added to August; an unknown `num_miss_2027` group; an earlier contradictory `control = Public` (999) and August `total2223 = Submitted`; an identifier with a count; an identifier listed twice; a count as text; N/A in a counted group; an outcome after a note. Also `test_a_changed_frequencies_header_is_refused`. |
| 2. Read-back compared names and values, not types | `schema(release)` gives every output column and type in order; the read-back must match it exactly, and the values must match with their Python types. | `test_a_write_that_does_not_read_back_identically_changes_nothing`: rows lost; `num_miss_prior` written as DOUBLE (0.0 and 7.0); `compiled` written as DATE. |
| 3. An apostrophe in the output path broke the SQL | Paths reach DuckDB only as bound parameters (COPY and both read-backs). The release's extra values are inserted as parameters too, not SQL literals. | `test_any_output_path_works_quotes_and_glob_characters_included`: `O'Brien.parquet`, and `out.parquet` inside `O'Brien's [draft] *1?/`, each written and then replaced. |

Optional hardening, done: the checksum and the parse use one buffer of the file's bytes
(`test_the_checksum_and_the_parse_use_the_same_bytes`).

## Results

- `parser-tests-ci-like.txt`: without ED's files, as CI runs: **42 passed, 2 skipped** (the two
  real-workbook tests).
- `parser-tests-real.txt`: with ED's two registered files present (SHA-256 `7b994e29...` and
  `76b99260...`, matching the registry): **44 passed**. August reproduces
  `published/fvtge_reporting.parquet` (names, types and values); October keeps all 4,674 rows with
  1,396 / 478 / 1,007 / 633.
- `old-code-3c1097f-reproductions.json` (script `old_code_reproductions.py`, run from a checkout of
  `3c3a083` with `3c1097f`'s parser file and a temporary folder as its arguments): each new test's bad
  input given to the parser at `3c1097f`. Accepted by the old code: all three removed groups, both
  unexpected groups, both earlier duplicates, both identifier cases, the outcome after a note, and the
  DOUBLE write (the target was replaced). Both quoted paths raised a DuckDB parser error. Two
  extra-strictness cases (a count written as text, N/A in a counted group) were already refused by
  the old code, under a different rule.
- `cli-quoted-paths.txt`: the command line with real data, October and August, into a folder named
  `O'Brien's [run]` with the file `oct'26.parquet`. Both written.
- `august-output-bytes.txt` (measured 4 November): the August output's bytes differ from the published
  file, but `main`'s own unchanged writer gives the same bytes as `3c3a083`, so this PR does not cause
  it. The cause is not established. Names, types, values and file order match.
- `gate.txt`: **GATE PASSED** on the worktree, after a full `./preview-build.sh` there.

## Not established here

- This is not a fresh earnings-association audit, and not evidence that a GitHub runner can download
  the workbook. The runner GET and content check remain open.
- These results are from 11 October, on a branch from `6058655`. `main` has moved since. PR CI tests
  the merge with current `main`; see the PR for its result. No local gate has run on that merge.
