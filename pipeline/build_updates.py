"""Generate /updates/: the public, verifiable log of the FVT Monitor.

Truewise claims it checks the Department of Education's transparency data monthly. This page
is the evidence: one entry per dated snapshot, with the exact source URLs, when it was fetched,
the file size, and a SHA-256 checksum anyone can recompute. Where two consecutive snapshots
both carry a rebuilt dataset, it also reports what actually changed between them.

Nothing here is written by hand. Every entry is read from archive/fvt/<date>/, so the page
cannot claim a check that did not happen.

Usage:
    python -m pipeline.build_updates
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import duckdb

from pipeline.build_college_pages import BASE, BEACON, FOOTER, esc, head
from pipeline.config import ROOT

SITE = ROOT / "site"
ARCHIVE = ROOT / "archive" / "fvt"
SNAPSHOT = "value_check_snapshot.parquet"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_source(d: Path) -> dict:
    """Parse the SOURCE.txt provenance file written when the snapshot was taken."""
    meta = {}
    src = d / "SOURCE.txt"
    if src.exists():
        for line in src.read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta


def collect_snapshots() -> list[dict]:
    """One record per dated snapshot directory, newest first."""
    if not ARCHIVE.is_dir():
        return []
    out = []
    for d in sorted(ARCHIVE.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = _read_source(d)
        pq = d / SNAPSHOT
        rec = {
            "date": meta.get("snapshot_date") or d.name,
            "fetched": meta.get("downloaded_utc"),
            "field_of_study": meta.get("field_of_study"),
            "institution": meta.get("institution"),
            "has_dataset": pq.exists(),
            "sha256": _sha256(pq) if pq.exists() else None,
            "size_mb": round(pq.stat().st_size / 1e6, 2) if pq.exists() else None,
            "path": pq,
        }
        if pq.exists():
            con = duckdb.connect()
            rec["rows"] = con.sql(f"SELECT count(*) FROM read_parquet('{pq}')").fetchone()[0]
        out.append(rec)
    return out


def diff_between(newer: Path, older: Path) -> dict | None:
    """What changed between two rebuilt snapshots, using the shipped diff logic."""
    try:
        from pipeline.monitor_diff import compute_diff
    except Exception:
        return None
    con = duckdb.connect()
    try:
        con.execute(f"CREATE OR REPLACE TABLE old AS SELECT * FROM read_parquet('{older}')")
        con.execute(f"CREATE OR REPLACE TABLE new AS SELECT * FROM read_parquet('{newer}')")
        d = compute_diff(con)
    except Exception:
        return None
    return {k: (len(v) if hasattr(v, "__len__") else v) for k, v in d.items()}


def render(snaps: list[dict]) -> str:
    canonical = f"{BASE}/updates/"
    title = "Update log: every check of the federal data"
    desc = (
        "Truewise snapshots the Department of Education's program-level transparency data and "
        "keeps the history. Every check is logged here with its source, timestamp, and a SHA-256 "
        "checksum you can verify yourself."
    )
    p = [head(title, desc, canonical)]
    p.append('  <main class="wrap pg">\n')
    p.append('    <nav class="crumbs">Updates</nav>\n')
    p.append("    <h1>Update log</h1>\n")
    p.append(
        '    <div class="verdict">We say Truewise checks the federal data monthly. This page is the '
        "evidence, not the claim: one entry per snapshot, each with the exact files fetched, when they "
        "were fetched, and a checksum anyone can recompute. The Department of Education publishes only "
        "the current release, so this archive is the history it does not keep.</div>\n"
    )

    if not snaps:
        p.append(
            '    <p class="idline">No snapshots recorded yet. The monitor runs on the 8th of each '
            "month and will log its first entry here.</p>\n"
        )
    else:
        with_data = [s for s in snaps if s["has_dataset"]]
        p.append(
            f'    <p class="idline">{len(snaps)} snapshot{"" if len(snaps) == 1 else "s"} recorded, '
            f"{len(with_data)} with a rebuilt dataset attached.</p>\n"
        )
        for i, s in enumerate(snaps):
            p.append('    <div class="upd">\n')
            p.append(f'      <h2 class="sec">{esc(s["date"])}</h2>\n')
            if s.get("fetched"):
                p.append(f'      <p class="upd-meta">Fetched {esc(s["fetched"])}</p>\n')
            if s["has_dataset"]:
                p.append(
                    f'      <p class="upd-meta">Rebuilt dataset: {s["rows"]:,} program rows, '
                    f'{s["size_mb"]} MB<br /><span class="mono">SHA-256 {esc(s["sha256"])}</span></p>\n'
                )
                # Report the change against the previous snapshot that also has a dataset.
                prev = next((x for x in snaps[i + 1 :] if x["has_dataset"]), None)
                if prev:
                    d = diff_between(s["path"], prev["path"])
                    if d:
                        p.append(
                            f'      <p class="upd-meta">Compared with {esc(prev["date"])}: '
                            f"<b>{d.get('newly_failing', 0):,}</b> programs newly fell short, "
                            f"<b>{d.get('newly_passing', 0):,}</b> newly cleared the bar, "
                            f"<b>{d.get('added', 0):,}</b> added, <b>{d.get('removed', 0):,}</b> removed, "
                            f"<b>{d.get('earnings_revised', 0):,}</b> had earnings revised.</p>\n"
                        )
            else:
                p.append(
                    '      <p class="upd-meta">Source files archived; no rebuilt dataset attached to '
                    "this entry.</p>\n"
                )
            for label, key in (
                ("Field of study", "field_of_study"),
                ("Institution", "institution"),
            ):
                if s.get(key):
                    p.append(
                        f'      <p class="upd-src">{label}: <span class="mono">{esc(s[key])}</span></p>\n'
                    )
            p.append("    </div>\n")

    p.append('    <h2 class="sec">Verify a snapshot yourself</h2>\n')
    p.append(
        '    <p class="src">Every snapshot lives in <span class="mono">archive/fvt/&lt;date&gt;/</span> '
        'in the <a href="https://github.com/ndranandraj/truewise">public repository</a>, next to a '
        '<span class="mono">SOURCE.txt</span> recording where it came from. To check one, download it '
        'and run <span class="mono">shasum -a 256 value_check_snapshot.parquet</span>; the result should '
        "match the checksum above. The diff logic is "
        '<span class="mono">pipeline/monitor_diff.py</span>.</p>\n'
    )
    p.append(
        '    <p class="src">Counts describe programs in the Department of Education\'s published data '
        "between two snapshot dates. A program can move because ED revised its earnings figure, because "
        "suppression changed, or because the program was added or withdrawn, so a change here is a "
        'signal to look, not a judgment about a school. Method: <a href="/methodology/">methodology</a>.</p>\n'
    )
    p.append("  </main>\n")
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


def stamp_last_verified(snaps: list[dict]) -> str | None:
    """Replace the homepage footer's freshness label with the real date of the newest check.

    The footer used to read "checked monthly", which is a promise about cadence rather than a
    statement of fact: if a monitor run is missed, the badge silently becomes untrue (an audit
    caught it reading "checked monthly" 32 days after the last recorded fetch). Stamping the
    actual date from archive/fvt/ means the label can only ever say something we can prove, and
    it degrades honestly on its own when a run is skipped.
    """
    if not snaps:
        return None
    newest = snaps[0].get("date")
    home = SITE / "index.html"
    # The homepage is absent in unit tests that render the log into a temp tree; stamping is a
    # side effect of the real build, not a precondition for producing the log.
    if not newest or not home.exists():
        return None
    html = home.read_text()
    new = re.sub(
        r'(<a href="/updates/">)(?:checked monthly|last verified [0-9]{4}-[0-9]{2}-[0-9]{2})(</a>)',
        rf"\1last verified {newest}\2",
        html,
    )
    if new != html:
        home.write_text(new)
    return newest


def main() -> None:
    snaps = collect_snapshots()
    out = SITE / "updates"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(snaps))
    verified = stamp_last_verified(snaps)
    print(
        f"updates: {len(snaps)} snapshot(s) -> {out}"
        + (f" | last verified {verified}" if verified else "")
    )


if __name__ == "__main__":
    main()
