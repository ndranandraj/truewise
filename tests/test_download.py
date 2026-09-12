"""Guard the Scorecard downloader's network behaviour.

The 2026-09-08 monthly refresh failed with `403 Forbidden` on the data home. The page served fine
to an ordinary client and was unchanged, so it was a client block on the default
"python-requests/x.y" agent from a shared CI address, not a missing file or a layout change.

These tests use a stubbed transport: the point is the retry, identity and error-message behaviour,
which is what turned a one-line traceback into a two-month silence nobody was told about.
"""

from __future__ import annotations

import pytest
import requests

from pipeline import download as dl


class _Resp:
    def __init__(self, status=200, text=""):
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def test_the_request_says_who_it_is(monkeypatch):
    """A public site that refuses an anonymous agent can allow, throttle or contact a named one.
    Impersonating a browser would hide us instead, which is the opposite of the fix."""
    seen = {}

    def fake_get(url, **kw):
        seen.update(kw.get("headers") or {})
        return _Resp(200, "ok")

    monkeypatch.setattr(dl.requests, "get", fake_get)
    dl.fetch("https://example.invalid/")
    ua = seen.get("User-Agent", "")
    assert "Truewise" in ua, "the agent must name the project"
    assert "truewise.dev" in ua and "github.com" in ua, "and give two ways to reach us"
    for browser in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert browser not in ua, f"must not impersonate a browser ({browser})"


def test_a_403_explains_itself_rather_than_raising_a_bare_httperror(monkeypatch):
    """The original failure surfaced as `raise_for_status` deep inside requests, which says nothing
    about what to do. A block and a missing file need different responses from whoever reads it."""
    monkeypatch.setattr(dl.requests, "get", lambda url, **kw: _Resp(403))
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit) as err:
        dl.fetch("https://example.invalid/")
    msg = str(err.value)
    assert "403" in msg and "client block" in msg
    assert "impersonating a browser" in msg, "the message must rule out the wrong fix"


def test_transient_failure_is_retried_but_a_404_is_not(monkeypatch):
    calls = {"n": 0}

    def flaky(url, **kw):
        calls["n"] += 1
        return _Resp(200, "ok") if calls["n"] > 2 else _Resp(503)

    monkeypatch.setattr(dl.requests, "get", flaky)
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)
    assert dl.fetch("https://example.invalid/").text == "ok"
    assert calls["n"] == 3, "a 5xx should be retried"

    calls["n"] = 0
    monkeypatch.setattr(
        dl.requests, "get", lambda url, **kw: (calls.update(n=calls["n"] + 1), _Resp(404))[1]
    )
    with pytest.raises(requests.HTTPError):
        dl.fetch("https://example.invalid/")
    assert calls["n"] == 1, "a 404 is real; retrying it just delays the error"


def test_a_layout_change_is_reported_as_a_layout_change():
    """find_bulk_urls fails differently from a block, and says which link it could not find."""
    with pytest.raises(SystemExit) as err:
        dl.find_bulk_urls("<html>no downloads here</html>")
    assert "download link" in str(err.value) and "layout may have changed" in str(err.value)
