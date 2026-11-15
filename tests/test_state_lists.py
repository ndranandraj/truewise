"""The state lists: named for what they measure, ranked on the exact share, ties shown as ties.

Until November 2026 the 49 lists were titled "Best-value colleges in <state>", ranked on the share
rounded to a whole percentage, numbered tied colleges 1, 2, 3 and cut at 25 inside a tie. Each test
here builds a small state and checks one of those things on the page a reader gets, on its share
card and in its download. The last test recomputes the counts the correction on /updates/ quotes.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
from pathlib import Path

import duckdb
import pytest

import pipeline.build_college_pages as bc
import pipeline.build_lists as bl
import pipeline.og_images as og
from pipeline.build_updates import CORRECTIONS

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL = "passes_earnings_premium", "fails_earnings_premium"
SLUG = "best-value-colleges-ct"
EM_DASH = chr(0x2014)


def _build(tmp_path, monkeypatch, colleges, state="CT", card=None):
    """Build one state's list from (unitid, name, programs above, programs compared, earnings).

    Returns (page html, rows of the page's table, rows of its CSV, share-card calls)."""
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE vc(unitid VARCHAR, inst_name VARCHAR, state VARCHAR, cip_code VARCHAR,
        cip_desc VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, earnings DOUBLE,
        debt_median DOUBLE, debt_payback_years DOUBLE, value_flag VARCHAR)"""
    )
    con.executemany(
        "INSERT INTO vc VALUES (?, ?, ?, ?, ?, '3', 'Bachelor''s Degree', ?, 9000.0, 1.0, ?)",
        [
            (uid, name, state, f"{i:04d}", f"Field {i}", pay, PASS if i < above else FAIL)
            for uid, name, above, compared, pay in colleges
            for i in range(compared)
        ],
    )
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bl, "PARQUET_DIR", pq)
    monkeypatch.setattr(bl, "SITE", tmp_path / "site")
    cards: list[dict] = []

    def record(path, eyebrow, headline, big=None, sub=None):
        cards.append({"path": path, "headline": headline, "sub": sub})
        return card(sub) if card else False

    monkeypatch.setattr(bl, "render_card", record)
    view = duckdb.connect()
    bl._views(view)
    links = {uid: f"school-{uid}" for uid, *_ in colleges}
    pages = {slug: page for slug, _, page in bl.build_state_lists(view, links)}
    slug = f"best-value-colleges-{state.lower()}"
    page = pages[slug]
    table = [
        (int(rank), html.unescape(name), cell)
        for rank, name, cell in re.findall(
            r"<tr><td class='num'>(\d+)</td><td><a [^>]*>(.*?)</a></td><td class='num'>(.*?)</td>",
            page,
        )
    ]
    with (tmp_path / "site" / "data" / "lists" / bl.csv_filename(slug)).open(newline="") as f:
        rows = list(csv.reader(f))
    return page, table, rows, cards


def _text(page: str) -> str:
    """What a reader sees: no markup, no attributes (the address still says best-value)."""
    return html.unescape(re.sub(r"<[^>]*>", " ", page))


# Five colleges with ten or more programs: the fewest a state needs for a list.
PLAIN = [
    ("101", "Alder College", 20, 20, 50000.0),
    ("102", "Birch College", 18, 20, 60000.0),
    ("103", "Cedar College", 16, 20, 70000.0),
    ("104", "Dogwood College", 14, 20, 80000.0),
    ("105", "Elm College", 12, 20, 90000.0),
]


def test_the_rank_is_on_the_exact_share_not_the_rounded_percentage(tmp_path, monkeypatch):
    # 13 of 14 is 92.9% and 14 of 15 is 93.3%. Both round to 93%, and the old order then put the
    # higher earner first: the college with the lower share, ahead of the one with the higher.
    colleges = [
        ("201", "Higher Earner", 13, 14, 90000.0),
        ("202", "Higher Share", 14, 15, 40000.0),
        *PLAIN[2:],
    ]
    _, table, rows, _ = _build(tmp_path, monkeypatch, colleges)
    names = [name for _, name, _ in table]
    assert names.index("Higher Share") < names.index("Higher Earner")
    by_name = {name: (rank, cell) for rank, name, cell in table}
    assert by_name["Higher Share"][0] == 1 and by_name["Higher Earner"][0] == 2
    # The page shows the difference the whole percentage hid.
    assert by_name["Higher Share"][1] == "14 of 15 <span class='ln-pct'>(93.3%)</span>"
    assert by_name["Higher Earner"][1] == "13 of 14 <span class='ln-pct'>(92.9%)</span>"
    assert [r[1] for r in rows[1:3]] == ["Higher Share", "Higher Earner"]


def test_colleges_with_one_share_have_one_rank_and_the_next_rank_skips(tmp_path, monkeypatch):
    colleges = [
        ("301", "Zeta College", 10, 10, 50000.0),
        ("302", "Alpha College", 20, 20, 70000.0),
        # 5 of 5 would be the same share as 20 of 20, on fewer programs than the list accepts.
        ("303", "Mid College", 12, 12, 60000.0),
        ("304", "Lower College", 18, 20, 99000.0),
        ("305", "Lowest College", 10, 20, 99000.0),
    ]
    page, table, rows, _ = _build(tmp_path, monkeypatch, colleges)
    # Three colleges at 100% are all first; the next college is fourth, not second.
    assert [(rank, name) for rank, name, _ in table] == [
        (1, "Alpha College"),
        (1, "Mid College"),
        (1, "Zeta College"),
        (4, "Lower College"),
        (5, "Lowest College"),
    ]
    assert (
        '<p class="ln-tie"><b>3 colleges share first place at 100%.</b> Colleges with the same '
        "share are listed by median earnings, highest first; they keep the same rank.</p>" in page
    )
    # The sentence a reader needs to read the order is above the table, not in the small print.
    assert page.index('class="ln-tie"') < page.index("<table") < page.index('class="src"')
    # The download carries the rank that is printed, not a row number.
    assert [r[0] for r in rows[1:]] == ["1", "1", "1", "4", "5"]


def test_a_tie_at_the_cut_is_kept_whole_and_the_page_says_so(tmp_path, monkeypatch):
    colleges = [
        ("401", "First College", 20, 20, 50000.0),
        ("402", "Tied Low Pay", 18, 20, 40000.0),
        ("403", "Tied High Pay", 9, 10, 80000.0),
        ("404", "Tied Mid Pay", 27, 30, 60000.0),
        ("405", "Below The Cut", 10, 20, 99000.0),
    ]
    monkeypatch.setattr(bl, "TOP_N", 2)
    page, table, _, _ = _build(tmp_path, monkeypatch, colleges)
    # A cut at two rows lands inside three colleges at 90%. All three stay; none is dropped for
    # its earnings or its name.
    assert [(rank, name) for rank, name, _ in table] == [
        (1, "First College"),
        (2, "Tied High Pay"),
        (2, "Tied Mid Pay"),
        (2, "Tied Low Pay"),
    ]
    assert "Below The Cut" not in page
    text = _text(page)
    assert "5 colleges in Connecticut have at least 10 programs that can be compared." in text
    assert (
        "4 are shown, not 2, because the cut would have split colleges with the same share." in text
    )


def test_a_list_that_fits_the_cut_does_not_claim_to_run_past_it(tmp_path, monkeypatch):
    page, table, _, _ = _build(tmp_path, monkeypatch, PLAIN)
    assert [rank for rank, _, _ in table] == [1, 2, 3, 4, 5]
    assert "are shown, not" not in page
    assert (
        '<p class="ln-tie">Colleges with the same share are listed by median earnings, highest '
        "first; they keep the same rank.</p>" in page
    )


def test_when_every_college_shown_ties_the_page_says_the_share_cannot_order_them(
    tmp_path, monkeypatch
):
    colleges = [(uid, name, n, n, pay) for uid, name, _, n, pay in PLAIN]
    page, table, _, cards = _build(tmp_path, monkeypatch, colleges)
    assert {rank for rank, _, _ in table} == {1}
    # Highest earnings first: the only order there is, and the page says so.
    assert [name for _, name, _ in table] == [
        "Elm College",
        "Dogwood College",
        "Cedar College",
        "Birch College",
        "Alder College",
    ]
    assert (
        "<b>All 5 colleges shown have the same share, 100%.</b> The share cannot order them. "
        "Colleges with the same share are listed by median earnings, highest first, and that is "
        "the only order on this page." in page
    )
    # The card names no college as first when five are.
    assert cards[-1]["sub"] == f"{bl.CARD_MEASURE} 5 colleges share first place at 100%."
    assert "#1" not in cards[-1]["sub"]


def test_the_card_names_a_college_only_when_one_is_first_and_keeps_the_measure(
    tmp_path, monkeypatch
):
    _, _, _, cards = _build(tmp_path, monkeypatch, PLAIN)
    assert len(cards) == 1
    assert cards[0]["headline"] == "Colleges in Connecticut"
    assert cards[0]["sub"] == f"{bl.CARD_MEASURE} #1: Alder College."
    assert cards[0]["path"].name == f"{SLUG}.png"


def test_a_card_line_that_would_be_cut_gives_way_to_a_shorter_one(tmp_path, monkeypatch):
    # The renderer reports a cut caption. A name too long for the card is left off; the measure,
    # which says what "first" means, is not.
    _, _, _, cards = _build(tmp_path, monkeypatch, PLAIN, card=lambda sub: "Alder College" in sub)
    assert [c["sub"] for c in cards] == [
        f"{bl.CARD_MEASURE} #1: Alder College.",
        f"{bl.CARD_MEASURE} One college is first.",
    ]


def test_the_build_stops_if_no_card_line_fits(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="no share-card line"):
        _build(tmp_path, monkeypatch, PLAIN, card=lambda sub: True)


def test_the_renderer_reports_a_cut_caption(tmp_path):
    short = og.card(tmp_path / "a.png", "Eyebrow", "Heading", sub="A caption that fits.")
    long = og.card(tmp_path / "b.png", "Eyebrow", "Heading", sub="A caption that runs on. " * 20)
    assert short is False and long is True


def test_the_page_says_what_it_measures_and_is_not_called_best_value(tmp_path, monkeypatch):
    page, _, _, _ = _build(tmp_path, monkeypatch, PLAIN)
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    assert title.startswith(
        "Colleges in Connecticut: how often graduates out-earn a high-school graduate"
    )
    assert (
        "<h1>Colleges in Connecticut whose graduates most often out-earn a high-school "
        "graduate</h1>" in page
    )
    text = _text(page).lower()
    # The address keeps the old words (an address is a contract); nothing a reader sees does.
    for gone in ("best-value", "best value", "clear the bar", "earnings-premium test"):
        assert gone not in text, f"{gone!r} is still on the page"
    assert "ranked by one measure: the share of each college’s programs" in text
    # It counts graduate programs against the high-school line, so it is not the federal test,
    # and the page says so outside any expandable section.
    main = page[page.index("<main") : page.index("</main>")]
    assert "<details" not in main
    assert "not the federal earnings test, which compares graduate programs with bachelor" in text
    assert '<a href="/earnings-test/">What the test is</a>' in page
    assert "middle of the college’s program medians, not the earnings of its typical graduate" in (
        text
    )
    assert EM_DASH not in page and "&mdash;" not in page
    # The address has not moved.
    assert f'<link rel="canonical" href="https://truewise.dev/lists/{SLUG}/"' in page


def test_the_download_gives_the_counts_as_columns_and_agrees_with_the_table(tmp_path, monkeypatch):
    colleges = [("501", "Smith, Jones & Co. College", 14, 15, 41000.0), *PLAIN[1:]]
    _, table, rows, _ = _build(tmp_path, monkeypatch, colleges)
    assert rows[0] == [
        "rank",
        "College",
        "Programs above the line",
        "Programs compared",
        "Share",
        "Median earnings",
    ]
    assert rows[1] == ["1", "Smith, Jones & Co. College", "14", "15", "93.3%", "$41,000"]
    assert len(rows) - 1 == len(table)
    for (rank, name, cell), row in zip(table, rows[1:], strict=True):
        assert [str(rank), name] == row[:2]
        assert cell == f"{row[2]} of {row[3]} <span class='ln-pct'>({row[4]})</span>"


def test_a_share_is_never_rounded_up_to_all_or_down_to_none():
    assert bl.share_text(5, 5) == "100%"
    assert bl.share_text(0, 10) == "0%"
    assert bl.share_text(1, 2) == "50%"
    assert bl.share_text(14, 15) == "93.3%"
    assert bl.share_text(13, 14) == "92.9%"
    # 2,499 of 2,500 is 99.96%. Printed as 100% it would contradict the count beside it.
    assert bl.share_text(2499, 2500) == "99.9%"
    assert bl.share_text(1, 5000) == "0.1%"


def test_every_state_has_a_search_description_that_fits():
    for name in bc.STATE_NAMES.values():
        text = bl.state_description(name)
        assert len(text) <= bl.DESC_MAX, f"{name}: {len(text)} characters"
        assert text.startswith(f"{name} colleges ranked by the share of ")
        assert "Ties are shown as ties." in text


def test_the_tie_line_and_the_quiet_percentage_are_styled():
    # The classes the page uses exist in the stylesheet every generated page loads.
    assert ".ln-tie {" in bc.PG_CSS and "border-left: 3px solid var(--caution)" in bc.PG_CSS
    assert ".ln-pct { color: var(--ink-soft); }" in bc.PG_CSS


def test_value_check_names_the_list_for_what_it_is():
    vc = (ROOT / "site" / "value-check" / "index.html").read_text()
    assert (
        "${esc(nm)} colleges whose graduates most often out-earn a high-school graduate</a>" in vc
    )
    assert "best-value colleges in" not in vc


# published/value_check.parquet as built from the 10 June 2026 College Scorecard release.
JUNE_RELEASE_SHA256 = "bb6e95ca619b625b773afbb9cf7a24284012fbeb8706652349071479fb0bf018"


def test_the_correction_quotes_what_the_june_lists_showed(monkeypatch):
    """The /updates/ entry counts what was wrong on the lists as published. Those counts are
    recomputed here from the committed data, with the old order written out as it was."""
    src = ROOT / "published" / "value_check.parquet"
    if hashlib.sha256(src.read_bytes()).hexdigest() != JUNE_RELEASE_SHA256:
        pytest.skip(
            "the correction describes the lists built from the 10 June 2026 release; published/ "
            "now holds a later release, so its counts cannot be recomputed from it"
        )
    monkeypatch.setattr(bl, "PARQUET_DIR", src.parent)
    con = duckdb.connect()
    bl._views(con)
    states = [
        r[0]
        for r in con.execute(
            f"SELECT st FROM sch WHERE n_dec >= {bl.MIN_SCHOOL_PROGRAMS} AND st IS NOT NULL "
            "GROUP BY st HAVING count(*) >= 5 ORDER BY st"
        ).fetchall()
        if bc.known_state(r[0])
    ]
    # The order as published: on the percentage rounded to a whole number, cut at 25.
    published = f"""SELECT unitid, n_pass, n_dec FROM sch
        WHERE st = ? AND n_dec >= {bl.MIN_SCHOOL_PROGRAMS}
        ORDER BY round(100.0 * n_pass / n_dec) DESC, round(med_earn) DESC, lower(nm), unitid
        LIMIT {bl.TOP_N}"""
    # The same, with only the rounding removed.
    exact = f"""SELECT unitid FROM sch WHERE st = ? AND n_dec >= {bl.MIN_SCHOOL_PROGRAMS}
        ORDER BY n_pass::DOUBLE / n_dec DESC, round(med_earn) DESC, lower(nm), unitid
        LIMIT {bl.TOP_N}"""
    order, shown_set, all_100, numbered_apart, shared_first, past = [], [], [], [], [], {}
    for st in states:
        old = con.execute(published, [st]).fetchall()
        old_ids = [r[0] for r in old]
        new_ids = [r[0] for r in con.execute(exact, [st]).fetchall()]
        shares = [above / compared for _, above, compared in old]
        now = bl.state_ranking(con, st)
        if old_ids != new_ids:
            order.append(st)
        if set(old_ids) != set(new_ids):
            shown_set.append(st)
        if len(old) > 1 and set(shares) == {1.0}:
            all_100.append(st)
        if len(set(shares)) < len(shares):
            numbered_apart.append(st)
        first = {r.unitid for r in now if r.rank == 1}
        # The college the old card called number 1 was always among those first on the share.
        assert old_ids[0] in first
        if len(first) > 1:
            shared_first.append(st)
        if len(now) > bl.TOP_N:
            past[st] = len(now)

    body = next(c["body"] for c in CORRECTIONS if c["title"].startswith("State college lists"))
    assert len(states) == 49 and "The 49 state lists" in body
    assert len(order) == 34 and "changes on 34 of the 49 lists" in body
    assert shown_set == ["FL", "MA", "NC", "VA"]
    assert "on 4 (Florida, Massachusetts, North Carolina and Virginia)" in body
    assert len(numbered_apart) == 47 and "That happened on 47 lists" in body
    assert all_100 == ["CA", "DE", "IL", "NY", "OH", "PA", "TX"]
    assert "on 7 (California, Delaware, Illinois, New York, Ohio, Pennsylvania and Texas)" in body
    assert len(past) == 9 and past["TX"] == 44
    assert "so 9 lists run past 25 rows; Texas shows 44" in body
    assert len(shared_first) == 47 and "On 47 lists that college shared first place" in body
    # The New Mexico example: 13 of 14 was listed ahead of 14 of 15, both shown as 93%.
    nm = con.execute(published, ["NM"]).fetchall()
    pairs = [(above, compared) for _, above, compared in nm]
    assert pairs.index((13, 14)) < pairs.index((14, 15))
    assert round(100 * 13 / 14) == round(100 * 14 / 15) == 93
    assert "13 of 14 programs" in body and "14 of 15" in body and "both showed as 93%" in body
    assert EM_DASH not in body
