"""Each new test's bad input, given to the parser at 3c1097f: does the old code refuse it?"""
import dataclasses, importlib.util, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
import duckdb
from pipeline import build_fvtge_source as S
import tests.test_fvtge_source as T
spec = importlib.util.spec_from_file_location("old", sys.argv[1]); old = importlib.util.module_from_spec(spec); sys.modules["old"] = old; spec.loader.exec_module(old)

def oldrel(rel, path):
    base = old.OCT if rel.compiled == S.OCT.compiled else old.AUG
    return dataclasses.replace(base, path=path, sha256=S.sha256(path))

def attempt(fn):
    try:
        fn(); return "accepted"
    except SystemExit as e: return f"refused: {e}"
    except Exception as e: return f"error: {type(e).__name__}: {str(e)[:90]}"

results = {}
freq_cases = {c.id: c for c in []}
params = [m for m in T.test_the_frequencies_sheet_has_exactly_the_releases_groups.pytestmark if m.name == "parametrize"][0].args[1]
for i, (rel, edit, message) in enumerate(params):
    d = Path(tempfile.mkdtemp(dir=sys.argv[2]))
    rows = T._oct_rows() if rel is S.OCT else T._aug_rows()
    p = d / "bad.xlsx"; T._book(p, rel, rows, freq_edit=edit)
    out = d / "out.parquet"
    results[f"freq[{i}] expects '{message}'"] = attempt(lambda: old.write(oldrel(rel, p), old.read_rows(oldrel(rel, p)), out))

# type-only mutation
d = Path(tempfile.mkdtemp(dir=sys.argv[2])); p = d / "ok.xlsx"; T._book(p, S.OCT, T._oct_rows())
r = oldrel(S.OCT, p); body = old.read_rows(r); out = d / "out.parquet"; old.write(r, body, out); before = out.read_bytes()
real = duckdb.connect
class Rw:
    def __init__(s, c): s.c = c
    def execute(s, q, *a, **k): return s.c.execute(q.replace("num_miss_prior INTEGER", "num_miss_prior DOUBLE") if q.startswith("CREATE TABLE") else q, *a, **k)
    def __getattr__(s, n): return getattr(s.c, n)
duckdb.connect = lambda *a, **k: Rw(real(*a, **k))
res = attempt(lambda: old.write(r, body, out))
duckdb.connect = real
t = duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()
results["type-only DOUBLE num_miss_prior"] = res + f"; target replaced: {out.read_bytes() != before}; num_miss_prior type now {[x[1] for x in t if x[0]=='num_miss_prior'][0]}"

# quoted paths
for target in ["O'Brien.parquet", "O'Brien's [draft] *1?/out.parquet"]:
    d = Path(tempfile.mkdtemp(dir=sys.argv[2])); p = d / "ok.xlsx"; T._book(p, S.OCT, T._oct_rows())
    r = oldrel(S.OCT, p); body = old.read_rows(r)
    results[f"path {target!r}"] = attempt(lambda: old.write(r, body, d / target))
print(json.dumps(results, indent=1))
