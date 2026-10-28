"""The cost section's starting years, and that two builds of the same data agree on them.

Found 11 October 2026: when two undergraduate credentials were listed in equal numbers, the default
went to whichever credential a Python set yielded first. That follows the per-process string hash
(PYTHONHASHSEED), so on the 249 profiles with such a tie two clean builds of one commit could
differ, only in the selected years and the total line. The rule now settles ties by reported completions, then the shorter
credential (pipeline/profile_layout.py, default_years).
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
from pathlib import Path

from pipeline.profile_layout import cost_section, default_years

ROOT = Path(__file__).resolve().parent.parent

CERT = "Undergraduate Certificate or Diploma"
ASSOC = "Associate's Degree"
BACH = "Bachelor's Degree"
NONCRED = "Non-Credential Program (Preparatory Coursework/Teacher Certification)"
NET_PRICE = {"avg": 12076, "brackets": [11000, 11500, 12500, 14000, 16000]}


def row(credential: str, completers=None, grad: bool = False) -> dict:
    return {"credential": credential, "completers": completers, "grad": grad}


def test_the_most_listed_credential_sets_the_years():
    assert default_years([row(CERT), row(CERT), row(ASSOC)]) == 1
    assert default_years([row(ASSOC), row(ASSOC), row(BACH)]) == 2
    # Bachelor's is named, not reached by a fallback.
    assert default_years([row(BACH), row(BACH), row(CERT)]) == 4


def test_a_tie_goes_to_the_credential_with_more_completions():
    assert default_years([row(CERT, 12), row(ASSOC, 92)]) == 2
    assert default_years([row(CERT, 19), row(ASSOC, 80), row(BACH, 3)]) == 2
    assert default_years([row(ASSOC, 5), row(BACH, 20)]) == 4
    # Completions add up across a credential's programs.
    assert default_years([row(CERT, 30), row(CERT, 30), row(ASSOC, 50), row(ASSOC, 0)]) == 1


def test_equal_completions_go_to_the_shorter_credential():
    assert default_years([row(ASSOC, 40), row(BACH, 40)]) == 2
    assert default_years([row(CERT, 7), row(ASSOC, 7), row(BACH, 7)]) == 1


def test_a_missing_count_is_not_read_as_zero():
    # Read as zero, the bachelor's side would win with 30. The certificate count is not published,
    # so the comparison cannot be made and the shorter credential is used.
    assert default_years([row(CERT, None), row(BACH, 30)]) == 1
    # One unpublished program is enough: a partial count never settles a tie.
    assert default_years([row(ASSOC, 50), row(ASSOC, None), row(BACH, 10), row(BACH, 10)]) == 2


def test_a_zero_count_is_a_real_count():
    assert default_years([row(CERT, 0), row(ASSOC, 5)]) == 2


def test_non_credential_and_unknown_labels_bring_no_length():
    # Left out, the certificate is the usual credential; they used to fall through to 4 years.
    assert default_years([row(NONCRED), row(CERT, 3)]) == 1
    assert default_years([row(NONCRED), row(NONCRED), row(ASSOC)]) == 2
    assert default_years([row("Some new ED label"), row("Some new ED label"), row(CERT)]) == 1
    # With no credential of set length the total equals the yearly price, never 4 years.
    assert default_years([row(NONCRED), row(NONCRED)]) == 1
    assert default_years([]) == 1


def test_graduate_programs_do_not_count():
    rows = [row("Master's Degree", 100, grad=True)] * 5 + [row(ASSOC, 1)]
    assert default_years(rows) == 2


def test_row_order_does_not_change_the_years():
    rows = [row(CERT, 19), row(ASSOC, 80), row(BACH, None), row(NONCRED), row(CERT, 4)]
    rows += [row(ASSOC, None), row(BACH, 2)]
    assert len({default_years(list(p)) for p in itertools.permutations(rows)}) == 1


def test_the_cost_section_starts_at_the_default_years():
    html = cost_section({}, [row(CERT, 41), row(ASSOC, 0)], NET_PRICE)
    assert '<option value="1" selected>1 year</option>' in html
    assert "About $12,076 over 1 year, if price and aid stay the same." in html
    html = cost_section({}, [row(CERT, 12), row(ASSOC, 92)], NET_PRICE)
    assert '<option value="2" selected>2 years</option>' in html
    assert "About $24,152 over 2 years, if price and aid stay the same." in html


# Rendered in a fresh interpreter per hash seed. On Python 3.14 the old expression,
# max(set(ug), key=ug.count), chose the certificate, the associate's or the bachelor's for this
# three-way tie depending on the seed among 0 to 5 (and CI's Python hashes strings differently),
# so several seeds are used rather than two.
_RENDER = f"""
from pipeline.profile_layout import cost_section
np_ = {NET_PRICE!r}
two = [{{"credential": {CERT!r}, "completers": 41}}, {{"credential": {ASSOC!r}, "completers": None}}]
three = [{{"credential": c, "completers": n}} for c, n in (({CERT!r}, 19), ({ASSOC!r}, 80), ({BACH!r}, 0))]
print(cost_section({{}}, two, np_))
print(cost_section({{}}, three, np_))
"""


def test_two_builds_with_different_hash_seeds_render_the_same_cost_section():
    outputs = {}
    for seed in ("0", "1", "2", "3", "4", "5"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", _RENDER],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, out.stderr
        outputs[seed] = out.stdout
    assert len(set(outputs.values())) == 1, "the cost section depends on the string hash seed"
    html = outputs["0"]
    assert "About $12,076 over 1 year," in html
    assert "About $24,152 over 2 years," in html
