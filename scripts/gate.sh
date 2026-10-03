#!/bin/bash
# The full Truewise gate: run before every commit, and commit only if it prints GATE PASSED.
#   ./scripts/gate.sh
# Each step's own exit code is checked; nothing is piped into tail, because a pipe returns the last
# command's status and that is how a failing check once slipped through twice.
set -u
cd "$(dirname "$0")/.."
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
ci_copy() {
  ( dir="$log_dir/truewise-ci-copy" && rm -rf "$dir" && mkdir -p "$dir" \
    && { git ls-files -z; git ls-files -z --others --exclude-standard; } | tar --null -T - -cf - | tar -xf - -C "$dir" \
    && cd "$dir" && python3 -m pytest -q -p no:cacheprovider )
}
run pytest_clean ci_copy
run components   python3 -m pipeline.build_components --check
run tokens       python3 -m pipeline.build_tokens --check
for s in components_smoke table_smoke ui_smoke integration_smoke profile_smoke compare_smoke search_smoke embed_smoke search_gold value_check_states k12_compare_states careers_states layout_shot_smoke; do
  run "$s" node "tests/$s.js"
done
if [ $fail -eq 0 ]; then echo "GATE PASSED"; else echo "GATE FAILED"; exit 1; fi
