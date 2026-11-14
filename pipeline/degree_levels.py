"""Degree levels as the major-and-degree pages name them.

One place for the address part and the three ways a page says a level, so the page builder
(build_major_degree_pages) and the pages that link to it (build_majors_pages) cannot disagree
about where a page lives. Keyed by College Scorecard CREDLEV.

The address part is a URL contract once published: 720 pages and every link to them. Change a
label freely; change a slug only with a redirect.
"""

from __future__ import annotations

from typing import NamedTuple


class Level(NamedTuple):
    slug: str  # the address part: /majors/<major>/<slug>/
    heading: str  # in a heading or a breadcrumb (HTML)
    title: str  # in a page title (plain text, short)
    adjective: str  # "a ... program" (HTML)


DEGREE: dict[str, Level] = {
    "1": Level("certificate", "Undergraduate certificate", "Certificate", "certificate"),
    "2": Level("associates", "Associate&rsquo;s degree", "Associate's", "associate&rsquo;s"),
    "3": Level("bachelors", "Bachelor&rsquo;s degree", "Bachelor's", "bachelor&rsquo;s"),
    "4": Level(
        "post-baccalaureate-certificate",
        "Post-baccalaureate certificate",
        "Post-bacc certificate",
        "post-baccalaureate certificate",
    ),
    "5": Level("masters", "Master&rsquo;s degree", "Master's", "master&rsquo;s"),
    "6": Level("doctoral", "Doctoral degree", "Doctorate", "doctoral"),
    "7": Level(
        "first-professional",
        "First professional degree",
        "Professional degree",
        "first professional",
    ),
    "8": Level(
        "graduate-certificate",
        "Graduate certificate",
        "Graduate certificate",
        "graduate certificate",
    ),
    "99": Level(
        "non-credential", "Non-credential program", "Non-credential program", "non-credential"
    ),
}


def degree_path(major_slug: str, cred: str | None) -> str | None:
    """The page for one major at one degree level, or None for a level with no page."""
    level = DEGREE.get(str(cred))
    return f"/majors/{major_slug}/{level.slug}/" if level else None
