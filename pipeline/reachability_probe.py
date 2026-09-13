"""Ask each Scorecard host what it returns, from wherever this runs.

The monthly refresh fails on 403 from the data home page. Two hypotheses were live and one is now
dead: an honest user agent naming the project, the site and the repository is refused exactly as the
default `python-requests` one was, so the block is not about identity. The same code from a home
network downloads fine, which points at the address rather than the agent, though that is support
rather than proof.

What nobody has tested is the scope. The page lives on `collegescorecard.ed.gov`; the zips live on
`ed-public-download.scorecard.network`. Every failed run died on the page and never reached a zip, so
the zip host's behaviour from a GitHub runner is unknown, and it is the unknown that decides whether
the Monitor can be repaired or has to be redesigned.

Run it anywhere and compare:

    python -m pipeline.reachability_probe

This sends the project's own agent, downloads nothing, and reports what came back. It does not
retry, does not follow a block with a second attempt under a different name, and does not
impersonate a browser. If a host refuses us, the useful output is the refusal.
"""

from __future__ import annotations

import socket
import sys

import requests

from pipeline.config import SCORECARD_DATA_HOME
from pipeline.download import HEADERS, USER_AGENT

# The zip host, taken from the URLs the data home actually served on 2026-09-11. Hard-coded on
# purpose: the point is to reach this host WITHOUT first parsing the page, since parsing the page is
# the step that fails.
ZIP_HOST = "https://ed-public-download.scorecard.network/downloads/"
KNOWN_ZIP = ZIP_HOST + "Most-Recent-Cohorts-Field-of-Study_06102026.zip"


def probe(label: str, url: str, method: str = "get") -> dict:
    """One request, reported whatever happens. A HEAD on the zip, so a 17 MB file is not pulled just
    to learn whether the host would have allowed it."""
    row = {"label": label, "url": url, "method": method.upper()}
    try:
        fn = requests.head if method == "head" else requests.get
        resp = fn(url, headers=HEADERS, timeout=30, allow_redirects=True)
        row["status"] = resp.status_code
        row["final_url"] = resp.url
        row["server"] = resp.headers.get("server", "")
        # A WAF usually names itself somewhere. Worth capturing: it distinguishes "the origin said
        # no" from "something in front of the origin said no", which are different problems.
        for h in ("cf-ray", "x-amz-cf-id", "x-akamai-request-id", "x-iinfo"):
            if h in resp.headers:
                row["edge"] = f"{h}={resp.headers[h]}"
                break
        row["ok"] = resp.status_code < 400
    except requests.RequestException as exc:
        row["status"] = None
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["ok"] = False
        # A transport failure is NOT the host refusing us. This probe reported "both blocked" on its
        # first run inside a restricted sandbox whose own proxy declined to open a tunnel: the
        # request never reached ED at all, and calling that a block would have been a conclusion
        # about a server nothing had spoken to. Same failure as rendering unknown as a value, and
        # the probe exists precisely to stop that happening to the Monitor.
        row["reached_host"] = not isinstance(
            exc, (requests.exceptions.ProxyError, requests.exceptions.ConnectionError)
        )
    else:
        row["reached_host"] = True
    return row


def main() -> None:
    print(f"agent    : {USER_AGENT}")
    try:
        print(f"hostname : {socket.gethostname()}")
    except OSError:
        pass
    print()

    results = [
        probe("data home page", SCORECARD_DATA_HOME),
        probe("zip host root", ZIP_HOST),
        probe("a known zip", KNOWN_ZIP, method="head"),
    ]

    for r in results:
        status = r.get("status")
        mark = "ok  " if r.get("ok") else "FAIL"
        print(f"[{mark}] {r['label']:<16} {r['method']:<4} {status if status else r.get('error')}")
        print(f"         {r['url']}")
        if r.get("server") or r.get("edge"):
            print(f"         server={r.get('server', '')} {r.get('edge', '')}".rstrip())
        print()

    page_ok = results[0]["ok"]
    zip_ok = results[2]["ok"]
    reached = [r for r in results if r["reached_host"]]

    print("-" * 72)
    if not reached:
        print("INCONCLUSIVE. No request reached either host.")
        print()
        print("Every attempt failed at the transport layer, which means this machine's own network")
        print(
            "refused to make the connection. That says nothing about what ED would have answered."
        )
        print("Run this from a GitHub runner, which is the address in question, or from a network")
        print("with open egress. A restricted sandbox cannot answer this.")
        sys.exit(2)
    if page_ok and zip_ok:
        print("Both reachable. The block is not present from here, so this address is not the")
        print("problem and the refresh should work unchanged.")
    elif not page_ok and zip_ok:
        print("The PAGE is blocked and the ZIPS are not.")
        print()
        print("The Monitor survives. It can fetch the zips directly when the release is unchanged,")
        print(
            "and keep parsing the page on the runs where the page is reachable, so a layout change"
        )
        print(
            "is still detected rather than assumed away. Pinning a URL permanently would trade one"
        )
        print("silent failure for another.")
    elif not page_ok and not zip_ok:
        print("BOTH are blocked from here.")
        print()
        print("Monthly refresh from this address is not available. The honest response is to stop")
        print("the schedule claiming otherwise: refresh by hand, commit, and reduce the job to")
        print("verifying and diffing what is committed. A scheduled job that cannot do its job is")
        print("worse than no schedule, because it looks like coverage.")
    else:
        print("The page is reachable and the zip is not, which is the reverse of the failure seen")
        print("so far. Do not design around this until it is reproduced: it may be transient.")

    # A mixed result is a useful answer rather than a failure, so it exits 0. Exit 1 means both
    # hosts were spoken to and both refused; exit 2, above, means the question was never asked.
    sys.exit(0 if (page_ok or zip_ok) else 1)


if __name__ == "__main__":
    main()
