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

It sends the project's own agent, does not retry, and does not impersonate a browser. It reports
each request's method, URL, final URL, status and any error, then whether the page answered a GET
and the file a HEAD. A HEAD answers only for HEAD: a success does not show that a GET would download
a valid workbook, and 405 or 501 means HEAD is unsupported, not that downloads are refused. It never
reports the list as unchanged: a probe that cannot reach a source must never say so.

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
    page = probe("announcement", ANNOUNCEMENT)
    file_ = probe("latest list", LATEST_LIST, method="head")
    # Every endpoint's outcome is printed in full, whatever the verdict, so the run's log is the
    # record even when another step has turned the run red.
    for r in (page, file_):
        mark = "ok  " if r.get("ok") else "FAIL"
        print(f"[{mark}] {r['label']:<13} {r['method']:<4} status={r.get('status')}")
        print(f"         url       {r['url']}")
        if r.get("final_url") and r.get("final_url") != r["url"]:
            print(f"         final url {r['final_url']}")
        if r.get("error"):
            print(f"         error     {r['error']}")
        if r.get("server") or r.get("edge"):
            print(f"         server={r.get('server', '')} {r.get('edge', '')}".rstrip())
        print()
    print("-" * 72)
    if not page["reached_host"] and not file_["reached_host"]:
        print("COULD NOT ASK. Neither request reached fsapartners.ed.gov: this machine's network")
        print("refused the connection, which says nothing about what ED would answer.")
        sys.exit(2)
    # HEAD answers only about HEAD. 405 or 501 means the method is not supported, not that a
    # download is refused; a 2xx means a HEAD succeeded, not that a GET would return a valid
    # workbook. A monitor would need its own GET and a check of what came back.
    head_unsupported = file_.get("status") in (405, 501)
    print(f"page (GET)  : {'answered' if page['ok'] else 'refused or failed'}")
    if head_unsupported:
        print("file (HEAD) : HEAD is not supported here; this says nothing about a GET")
    else:
        print(f"file (HEAD) : {'answered' if file_['ok'] else 'refused or failed'}")
    print()
    print("A HEAD that succeeds does not show that a GET would download a valid workbook, and this")
    print("probe never reports the list as unchanged. Designing a monitor needs a separate GET and")
    print("content check.")
    sys.exit(0 if page["ok"] and (file_["ok"] or head_unsupported) else 1)


if __name__ == "__main__":
    main()
