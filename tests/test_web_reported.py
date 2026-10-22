"""Seen recently in the UK on the answer page (_reported_slot.html, /answers/{id}/reported):
GBIF's UK records of the plant's pests, then news headlines about them, loaded after the page
opens, hidden when off, empty or failed, and never part of the rater text. Stubs stand in for
GBIF and Tavily: no live calls."""

import json
import re
from datetime import date

from herbtwin.reported import Reported
from herbtwin.schemas import Location
from herbtwin.sightings import Sighting
from herbtwin.web.answer_text import plan_text
from tests.fakes import follow
from tests.test_reported import StubTavily, _hit
from tests.test_web import ADV, JPEG, OBS, _client

LINK = (
    "https://www.gbif.org/occurrence/search?taxon_key=3277292&country=GB"
    "&event_date=2026-08-23%2C2026-10-22&license=CC0_1_0&license=CC_BY_4_0"
)
MILDEW_SEEN = Sighting(
    "basil downy mildew",
    "Basil downy mildew",
    "Peronospora belbahrii",
    7,
    date(2026, 10, 3),
    LINK,
)
NEWS = _hit(
    "Basil downy mildew found in UK gardens | RHS",
    "https://www.rhs.org.uk/news/basil-downy-mildew-2026",
    snippet="Spray with copper...",  # the page's own words: never shown
)
GBIF_LINE = (
    "Records of these pests anywhere in the UK, not on your plant and not near you, from GBIF.org:"
    " CC0 and CC BY datasets only. Records reach"
    " GBIF a few weeks late."
)
NEWS_LINE = "Found with Tavily. Headlines only; check the page before acting."


class StubSightings:
    def __init__(self, seen=(), fail=False):
        self.seen_list, self.fail, self.asked = list(seen), fail, []

    def seen(self, problems):
        self.asked.append(tuple(problems))
        if self.fail:
            raise RuntimeError("boom")
        return list(self.seen_list)


def _answer(tmp_path, seen=None, hits=None, fail=False, obs=OBS):
    """seen: GBIF's lines (None: GBIF off); hits: Tavily's (None: Tavily off)."""
    tmp_path.mkdir(exist_ok=True)
    c = _client(tmp_path, [json.dumps(obs)], [json.dumps(ADV)] * 3)
    c.app.state.sightings = StubSightings(seen, fail=fail) if seen is not None else None
    c.app.state.reported = (
        Reported(StubTavily(hits, fail=fail), today=lambda: date(2026, 10, 22))
        if hits is not None
        else None
    )
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r"/answers/([0-9a-f]{32})", str(page.url))[1]
    return c, page.text, rid


def test_the_slot_waits_hidden_under_keep_an_eye_on_and_loads_after_the_page(tmp_path):
    _, page, rid = _answer(tmp_path, [MILDEW_SEEN])
    slot = page.split('<section class="reported" id="reported"', 1)[1].split("</section>", 1)[0]
    assert f'data-src="/answers/{rid}/reported" hidden>' in slot
    assert '<h2 id="reported-h">Seen recently in the UK</h2>' in slot
    assert "Looking" not in slot and "nothing" not in slot.lower()  # no empty box, no "none"
    script = page.split('<section class="reported"', 1)[1].split("</script>", 1)[0]
    assert "s.hidden = false;" in script and "if (!html.trim()) return;" in script
    assert script.index("if (!html.trim()) return;") < script.index("s.hidden = false;")
    # under Keep an eye on, before the by-part view and What next
    assert page.index('id="reported"') < page.index('class="next-step ink"')
    if 'id="watch"' in page:
        assert page.index('id="watch"') < page.index('id="reported"')


def test_the_fragment_lists_gbif_records_with_their_link_and_credit(tmp_path):
    c, _, rid = _answer(tmp_path, [MILDEW_SEEN])
    got = c.get(f"/answers/{rid}/reported")
    assert got.status_code == 200
    line = (
        f'<a href="{LINK.replace("&", "&amp;")}" rel="noopener noreferrer" target="_blank">'
        "Basil downy mildew: 7 UK records in the last 60 days, latest 3 Oct 2026</a>"
        ' <span class="muted">(<i>Peronospora belbahrii</i>)</span>'
    )
    assert line in got.text
    said = " ".join(re.sub(r"<[^>]+>", "", got.text).split())
    assert GBIF_LINE in said
    assert "In the news" not in got.text and NEWS_LINE not in said  # Tavily off: no news part
    # the plant's listed problems are what GBIF is asked about
    assert c.app.state.sightings.asked == [
        ("aphids", "basil downy mildew", "grey mould", "powdery mildew", "slugs and snails")
    ]


def test_the_news_headlines_sit_under_the_records(tmp_path):
    c, _, rid = _answer(tmp_path, [MILDEW_SEEN], [NEWS])
    got = c.get(f"/answers/{rid}/reported").text
    link = (
        '<a href="https://www.rhs.org.uk/news/basil-downy-mildew-2026" rel="noopener noreferrer"'
        ' target="_blank">Basil downy mildew found in UK gardens</a> — RHS, 7 Oct 2026'
    )
    assert link in got and '<h3 class="reported-news">In the news this month</h3>' in got
    assert got.index("UK records") < got.index("In the news this month") < got.index(link)
    assert NEWS_LINE in " ".join(got.split())
    assert "Spray" not in got  # the page's own advice never shows
    # news alone, with GBIF off, still shows
    c, _, rid = _answer(tmp_path / "b", None, [NEWS])
    got = c.get(f"/answers/{rid}/reported").text
    assert link in got and "GBIF" not in got


def test_text_from_outside_is_escaped(tmp_path):
    title = '<script>alert(1)</script> Basil downy mildew "alert" & more'
    odd = Sighting("x", "<b>Basil</b>", "<i>x</i>", 2, None, 'https://www.gbif.org/"><script>')
    c, _, rid = _answer(tmp_path, [odd], [_hit(title, "https://www.rhs.org.uk/news/x")])
    got = c.get(f"/answers/{rid}/reported").text
    assert "<script>" not in got and "<b>Basil" not in got
    assert (
        "&lt;script&gt;alert(1)&lt;/script&gt; Basil downy mildew &#34;alert&#34; &amp; more" in got
    )
    assert 'href="https://www.gbif.org/&#34;&gt;&lt;script&gt;"' in got


def test_off_there_is_no_slot_and_nothing_is_asked(tmp_path):
    c, page, rid = _answer(tmp_path)  # GBIF switched off, Tavily off
    assert 'id="reported"' not in page
    assert c.get(f"/answers/{rid}/reported").status_code == 204


def test_nothing_found_or_a_failure_is_a_204_and_the_slot_stays_hidden(tmp_path):
    c, _, rid = _answer(tmp_path, [], [])
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    c, _, rid = _answer(tmp_path / "b", [MILDEW_SEEN], [NEWS], fail=True)
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    c, _, rid = _answer(tmp_path / "c", [MILDEW_SEEN])

    class Boom:
        def reports(self, subject):
            raise RuntimeError("boom")

    c.app.state.reported = Boom()  # the news breaking leaves the records showing
    assert c.get(f"/answers/{rid}/reported").status_code == 200
    c.app.state.sightings = StubSightings(fail=True)
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    assert c.get("/answers/not-an-id/reported").status_code == 204


def test_no_plant_identified_asks_nothing(tmp_path):
    c, _, rid = _answer(tmp_path, [MILDEW_SEEN], [NEWS])
    c.app.state.answers.get_for(rid, None).latest.observation.species = []
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    assert c.app.state.reported._tavily.asked == [] and c.app.state.sightings.asked == []


def test_outside_the_uk_shows_nothing(tmp_path):
    c, _, rid = _answer(tmp_path, [MILDEW_SEEN])
    entry = c.app.state.answers.get_for(rid, None)
    entry.latest.location = Location(lat=48.85, lon=2.35, source="typed", label="Paris, FR")
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    assert c.app.state.sightings.asked == []


def test_the_rater_text_and_the_one_green_button_are_the_same_with_the_slot(tmp_path):
    _, with_slot, _ = _answer(tmp_path, [MILDEW_SEEN], [NEWS])
    _, without, _ = _answer(tmp_path / "b")
    assert 'id="reported"' in with_slot and 'id="reported"' not in without
    assert plan_text(with_slot) == plan_text(without)
    assert "Seen recently" not in plan_text(with_slot)
    assert with_slot.count("primary") == without.count("primary")
    c, _, rid = _answer(tmp_path / "c", [MILDEW_SEEN], [NEWS])
    got = c.get(f"/answers/{rid}/reported").text
    assert "button" not in got and "primary" not in got  # links only, no new button


def test_the_card_text_is_16px_or_more():
    from herbtwin.web import style

    sheet = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
    rules = re.findall(r"\.answer-page \.reported[^{]*\{([^}]*)\}", sheet)
    assert rules  # the card is styled
    sizes = [int(x) for r in rules for x in re.findall(r"font(?:-size)?:[^;]*?(\d+)px", r)]
    assert sizes and min(sizes) >= 16
    assert any("h3" in r for r in re.findall(r"\.answer-page \.reported[^{]*\{", sheet))
    # the muted lines are <small>, which the site sets at 16px
    assert "small, .small { font-size: 16px; }" in (style.STATIC / "herbtwin.css").read_text(
        "utf-8"
    )


def test_the_privacy_page_says_what_gbif_and_tavily_get(tmp_path):
    c, _, _ = _answer(tmp_path)
    said = " ".join(c.get("/privacy").text.split())
    assert (
        "<strong>GBIF</strong> (the Global Biodiversity Information Facility) gets only the"
        " species of a pest or disease the plant can get and a date range, to count its UK"
        " records from the last 60 days. It is told nothing about you or where you are."
    ) in said
    assert (
        'To show news under "Seen recently in the UK", Tavily gets the name of a pest or disease'
        " the plant can get (for example, rosemary beetle), to find this month's UK reports of"
        " it; nothing about you or where you are goes with it."
    ) in said


def test_the_about_page_credits_gbif_and_its_licences(tmp_path):
    c, _, _ = _answer(tmp_path)
    page = c.get("/about").text
    credits = page.split('<details class="made-credits" id="credits">', 1)[1]
    assert "<dt>Pest and disease sightings</dt>" in credits
    assert '<a href="https://www.gbif.org/" rel="noopener noreferrer">GBIF.org</a>' in credits
    assert ">CC0</a>" in credits and ">CC BY 4.0</a>" in credits


def test_the_card_head_is_not_check_first_amber_and_links_are_not_bold():
    # #388 review: amber means "check first"; a list of bold links read heavy
    from herbtwin.web import style

    css = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
    assert ".answer-page .reported h2 { margin: 0 0 4px; color: var(--primary);" in css
    assert ".answer-page .reported-links a { font-weight: 400; }" in css


def test_a_rough_read_shows_no_pests_for_its_guessed_plant_and_asks_nothing(tmp_path):
    # review of #406 (22 Oct walk): a blurred parsley read as mint must not list mint's
    # pests, nor spend GBIF or Tavily searches on the guess
    blurred = {
        **OBS,
        "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.4}],
        "photo_quality": "poor",
        "quality_note": "heavily blurred",
    }
    c, page, rid = _answer(tmp_path, [MILDEW_SEEN], [NEWS], obs=blurred)
    assert 'id="reported"' not in page
    assert c.get(f"/answers/{rid}/reported").status_code == 204
    assert c.app.state.sightings.asked == []
