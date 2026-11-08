"""ED's INSTURL is free text, and the profile lookup turns it into a link."""

from __future__ import annotations

import pytest

from pipeline.build_site import clean_school_url


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("www.baylor.edu", "www.baylor.edu"),
        ("www.baylor.edu/", "www.baylor.edu/"),
        ("https://www.sfiec.edu/admissions", "https://www.sfiec.edu/admissions"),
        ("HTTP://Example.EDU/a", "HTTP://Example.EDU/a"),
        # Two addresses, or a sentence after one: the first address is the link.
        (
            "https://www.sfiec.edu/ and https://paulmitchell.edu/sanfrancisco",
            "https://www.sfiec.edu/",
        ),
        (
            "www.brgeneral.org/medical-education/school-of-nursing/ OR school of radiologic technology",
            "www.brgeneral.org/medical-education/school-of-nursing/",
        ),
        # A fragment with spaces in it, from South University's campus links.
        ("www.southuniversity.edu/tampa#location=Tampa, FL", "www.southuniversity.edu/tampa"),
        # A trailing dot on the host.
        ("charlesstuartschool.com./", "charlesstuartschool.com/"),
    ],
)
def test_keeps_a_link_that_reaches_the_school(raw, want):
    assert clean_school_url(raw) == want


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "NA",
        # An email written as a URL: the browser would go to gmail.com.
        "https://imbeautyschool@gmail.com/",
        "javascript:alert(1)",
        "ftp://example.edu/",
        'x"onmouseover="alert(1)',
    ],
)
def test_gives_no_link_rather_than_a_wrong_one(raw):
    assert clean_school_url(raw) is None
