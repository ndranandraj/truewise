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
