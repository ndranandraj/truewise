"""Prototypes never reach the public site.

site/_proto/ holds local-only review pages. It is gitignored, so a clean CI checkout has none, but
wrangler.jsonc uploads all of ./site, so a deploy from a working tree would publish them. noindex
keeps a page out of search, not off the internet. Two guards, both checked here: Wrangler's
site/.assetsignore excludes _proto, and the deploy workflow stops before uploading if it exists.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assetsignore_excludes_prototypes():
    lines = [
        ln.strip()
        for ln in (ROOT / "site" / ".assetsignore").read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert "_proto" in lines, "site/.assetsignore must exclude _proto from the upload"


def test_deploy_stops_if_a_prototype_is_present():
    wf = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    guard = wf.find("No prototype pages in the upload")
    deploy = wf.find("Deploy to Cloudflare")
    assert guard != -1, "the deploy workflow lost its prototype guard"
    assert guard < deploy, "the prototype guard must run before the upload"
    assert "[ -e site/_proto ]" in wf[guard:deploy]


def test_the_deploy_runs_every_gate_the_preview_says_would_block_it():
    """preview-build.sh called honesty_scan a gate that would block a deploy, and the deploy did not
    run it (found November 2026). The two lists must not drift apart."""
    preview = (ROOT / "preview-build.sh").read_text()
    gates = preview.split('step "Gates that would block a deploy"', 1)[1].split('step "Built"', 1)[
        0
    ]
    deploy = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    commands = [
        ln.replace("$PYTHON -m ", "").strip()
        for ln in gates.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert commands, "no gates found in preview-build.sh"
    for cmd in commands:
        assert cmd in deploy, f"preview-build.sh gate not in the deploy: {cmd}"


def test_the_deploy_publishes_the_checksums_beside_the_datasets():
    deploy = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "cp published/*.parquet published/SHA256SUMS.txt site/data/" in deploy


def test_redirects_are_exact_paths_that_cannot_shadow_a_real_page():
    rules = [
        ln.split()
        for ln in (ROOT / "site" / "_redirects").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert rules, "no redirect rules"
    site = ROOT / "site"
    built = (site / "colleges").is_dir()
    for source, target, status in rules:
        assert "*" not in source and ":" not in source, f"{source} is not an exact path"
        assert status == "301"
        if built and target != "/#data":
            path = target.split("#")[0].lstrip("/")
            assert (site / path / "index.html").exists() or (site / path).is_file(), (
                f"{source} redirects to {target}, which the build does not produce"
            )
