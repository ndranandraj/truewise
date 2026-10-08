"""Can a GitHub runner reach ED's FVT/GE reporting list? Asked before any monitor is designed for it.

The FVT/GE finding is built from ED's "List of Institutions That Previously Submitted FVT/GE Data",
a spreadsheet on fsapartners.ed.gov that ED re-publishes as institutions report (11 August, 28
August, 25 September and 8 October 2026 so far). The monthly FVT Monitor does not watch it, and the
Scorecard hosts it does use refuse GitHub's runners (pipeline/reachability_probe.py, 13 September
2026). Whether fsapartners.ed.gov refuses them too is unknown, and it decides whether a monitor for
the list can run from Actions at all.

This asks two things and reports what came back:
  * the announcement page that links each version of the list (a GET; the page is small), and
  * the newest spreadsheet known on 8 October 2026 (a HEAD, so nothing is downloaded).

It sends the project's own agent, does not retry, and does not impersonate a browser. Its only
answers are "reachable", "refused" and "could not ask": a probe that cannot reach a source must
never report that source as unchanged, so it says nothing about whether the list has changed.

    python -m pipeline.fvtge_reachability_probe
"""

from __future__ import annotations

import socket
import sys

from pipeline.download import USER_AGENT
from pipeline.reachability_probe import probe

ANNOUNCEMENT = (
    "https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-08-11/"
    "guidance-fvt/ge-data-reporting-stats-early-implementation-and-next-steps-publication-updated-oct-8-2026"
)
# Hard-coded on purpose, as in reachability_probe: reaching the file must not depend on first
# parsing the page, since the page is one of the things being tested.
LATEST_LIST = (
    "https://fsapartners.ed.gov/sites/default/files/2026-10/FVTGEDataReportingOct082026.xlsx"
)


def main() -> None:
    print(f"agent    : {USER_AGENT}")
    try:
        print(f"hostname : {socket.gethostname()}")
    except OSError:
        pass
    print()
    results = [
        probe("announcement", ANNOUNCEMENT),
        probe("latest list", LATEST_LIST, method="head"),
    ]
    for r in results:
        mark = "ok  " if r.get("ok") else "FAIL"
        print(f"[{mark}] {r['label']:<13} {r['method']:<4} {r.get('status') or r.get('error')}")
        print(f"         {r['url']}")
        if r.get("server") or r.get("edge"):
            print(f"         server={r.get('server', '')} {r.get('edge', '')}".rstrip())
        print()
    print("-" * 72)
    if not any(r["reached_host"] for r in results):
        print(
            "COULD NOT ASK. No request reached fsapartners.ed.gov: this machine's network refused"
        )
        print(
            "the connection, which says nothing about what ED would answer. Run it from a runner."
        )
        sys.exit(2)
    if all(r["ok"] for r in results):
        print(
            "REACHABLE. Both the page and the file answered from here. A monitor for the list could"
        )
        print(
            "run from this address; it would still have to report a failed fetch as a failure, never"
        )
        print("as 'unchanged'.")
        sys.exit(0)
    if not any(r["ok"] for r in results):
        print(
            "REFUSED. fsapartners.ed.gov answered and refused both requests from here. A monitor for"
        )
        print(
            "the list cannot run from this address; checking for new versions stays a manual step."
        )
        sys.exit(1)
    print("MIXED. One request was refused and one was not. Do not design around this until it is")
    print("reproduced: it may be transient, or specific to the page or the file.")
    sys.exit(1)


if __name__ == "__main__":
    main()
