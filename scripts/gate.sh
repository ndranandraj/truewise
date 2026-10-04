#!/bin/bash
# The full Truewise gate: run before every commit, and commit only if it prints GATE PASSED.
#   ./scripts/gate.sh
# Each step's own exit code is checked; nothing is piped into tail, because a pipe returns the last
# command's status and that is how a failing check once slipped through twice.
# The browser layout check is not part of this gate. It is a separate release check for page changes:
#   ./preview-build.sh && node tests/layout_check.js
set -u
cd "$(dirname "$0")/.." || { echo "gate: cannot change to the repository root"; exit 1; }
fail=0
log_dir="${TMPDIR:-/tmp}"
run() {
  local name="$1"; shift
  if "$@" >"$log_dir/gate_$name.log" 2>&1; then echo "  ok    $name"
  else echo "  FAIL  $name"; tail -8 "$log_dir/gate_$name.log"; fail=1; fi
}
# Ruff from the project's .venv when it is there, else a Python module, else PATH. Nothing is
# installed: with no ruff anywhere the gate fails and says how to get one.
if [ -x .venv/bin/ruff ]; then ruff=(.venv/bin/ruff)
elif python3 -m ruff --version >/dev/null 2>&1; then ruff=(python3 -m ruff)
elif command -v ruff >/dev/null 2>&1; then ruff=(ruff)
else ruff=()
fi
if [ ${#ruff[@]} -eq 0 ]; then
  echo "  FAIL  ruff"
  echo "        ruff not found: create .venv (python3 -m venv .venv && .venv/bin/pip install ruff) or put ruff on PATH"
  fail=1
else
  run ruff_check   "${ruff[@]}" check .
  run ruff_format  "${ruff[@]}" format --check .
fi
run pytest       python3 -m pytest -q
# CI runs on a clean checkout with no built site/. Tests that pass locally only because site/college/
# exists failed in CI twice, so the suite also runs on a copy holding tracked and new files only
# (gitignored build output excluded), which is what the runner sees.
# Every step of the copy is checked before pytest runs: a failed file listing or archive must fail
# this step, never leave pytest passing on a partial copy. Each run gets its own scratch directory.
ci_copy() {
  local dir list rc
  dir="$(mktemp -d "$log_dir/truewise-ci-copy.XXXXXX")" || { echo "cannot create a scratch directory"; return 1; }
  list="$(mktemp "$log_dir/truewise-ci-files.XXXXXX")" || { echo "cannot create a file list"; rm -rf "$dir"; return 1; }
  (
    set -o pipefail
    git ls-files -z >"$list" || { echo "git ls-files (tracked) failed"; exit 1; }
    git ls-files -z --others --exclude-standard >>"$list" || { echo "git ls-files (new files) failed"; exit 1; }
    [ -s "$list" ] || { echo "no files listed to copy"; exit 1; }
    tar --null -T "$list" -cf - | tar -xf - -C "$dir" || { echo "copying the files failed"; exit 1; }
    cd "$dir" || { echo "cannot change to $dir"; exit 1; }
    python3 -m pytest -q -p no:cacheprovider
  )
  rc=$?
  rm -rf "$dir" "$list"
  return $rc
}
run pytest_clean ci_copy
run components   python3 -m pipeline.build_components --check
run tokens       python3 -m pipeline.build_tokens --check
for s in components_smoke table_smoke ui_smoke integration_smoke profile_smoke compare_smoke search_smoke embed_smoke search_gold value_check_states k12_compare_states careers_states layout_shot_smoke layout_enlarged_smoke; do
  run "$s" node "tests/$s.js"
done
if [ $fail -eq 0 ]; then echo "GATE PASSED"; else echo "GATE FAILED"; exit 1; fi
