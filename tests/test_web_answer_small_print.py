"""19 Oct small-print plan, PR 2: the answer and spot pages keep their information but say
it once, shorter, with the credits one tap away."""

import re

import respx

from herbtwin.answer import NO_CURE_HEADLINE
from herbtwin.confidence import UNSAID, load_weights
from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.web.app import TEMPLATES
from tests.fakes import follow
from tests.test_answer_walk_fixes import _render
from tests.test_web_answer_page import _card, _full_plan
from tests.test_web_spot import JPEG, _archive
from tests.test_web_spot import _client as _spot_client

TWIN_LEAD = "Tested on your plant&#39;s twin:"


def _source() -> str:
    return TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]


def test_the_twin_lead_is_said_once_then_a_twin_chip(tmp_path):
    rec = _full_plan(tmp_path)  # main card, Also do and Don't: all "from the twin"
    page = _render(rec)
    assert page.count(TWIN_LEAD) == 1
    assert page.count('<span class="tag twin-chip">Twin</span>') >= 1
    assert page.index(TWIN_LEAD) < page.index('class="tag twin-chip"')  # in full first


def test_the_twin_picture_note_is_short_and_links_its_credits():
    src = _source()
    assert "Illustration for our sample photo, not a prediction. · " in src
    assert '<a href="/about#credits">Photo credits</a>' in src and "twin.pair.credit" not in src


def test_how_sure_is_listed_once(tmp_path):
    rec = _full_plan(tmp_path)
    assert rec.answer is not None and rec.answer.factors
    page = _render(rec)
    evidence = page.split('<details class="evidence fold">', 1)[1]
    evidence = evidence.split("</details>", 1)[0]
    evidence = evidence.split('<details class="assumptions">', 1)[0]
    why = page.split('<details class="why fold', 1)[1].split("</details>", 1)[0]
    shown_once = {"advisor"}  # "the advisor was sure" goes when "N of 3 agree" says it
    weights = load_weights()["factors"]
    said = " ".join(w for c in rec.answer.chips for w in c.why)
    for f in rec.answer.factors:
        assert f.detail not in evidence, f.detail  # said once, under "Why we're …"
        lowered = f.effect == "lowers" and weights.get(f.name, {}).get("lowers", 0.0) < 0
        if f.name not in shown_once | UNSAID and (lowered or f.detail in said):
            # nothing lost: a reason that lowered it is always there (one row per chip, its
            # net effect, since 22 Oct; only a reason the other way under Lowered it goes)
            assert f.detail in why.replace("&#39;", "'"), f.detail


def test_the_twin_lead_falls_to_the_picture_when_the_main_card_is_not_the_twin(tmp_path):
    from herbtwin.twin_bank import TwinFigure, TwinPair

    rec = _full_plan(tmp_path)
    assert rec.answer is not None
    main_card = rec.answer.do[0]
    main_card.if_you_do, main_card.if_you_do_from = "it recovers in a week", "outcome_table"
    pair = TwinPair(do="d.jpg", dont="n.jpg", credit="c", care="water")
    twin = TwinFigure(
        pair=pair,
        model_line="watering keeps it moist",
        do_label="If you water it",
        dont_label="If you don't",
    )
    page = TEMPLATES.get_template("result.html").render(
        rec=rec, failed={}, asks=["question"], choices={}, max_question=500, chat=[],
        max_chat=500, check=None, reminder=None, compass_first="", spot_on=False,
        signed_in=False, accounts=False, twin=twin,
    )  # fmt: skip
    main = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert "From gardening sources:" in main and "Twin</span>" not in main
    pic = page.split('<section class="twin"', 1)[1].split("</section>", 1)[0]
    assert "Tested on your plant's twin: watering keeps it moist." in pic
    lead = page.count("Tested on your plant's twin:") + page.count(TWIN_LEAD)
    assert lead == 1


def test_the_header_and_reference_are_short(tmp_path):
    rec = _full_plan(tmp_path)
    rec.taken_at_source = "assumed"
    page = _render(rec)
    where = page.split('<p class="where">', 1)[1].split("</p>", 1)[0]
    assert "no date in the photo" not in where and ", GB" not in where
    assert f'<p class="record">Ref {rec.record_id}</p>' in page and "quote it" not in page


def test_the_chart_caption_and_hints_are_one_short_line():
    src = _source()
    cap = src.split('<span id="twin-chart-cap">', 1)[1].split("</span>", 1)[0]
    assert (
        cap
        == "Soil water over 2 weeks. Dashed: leaving it. Blue: cold nights. Tap a choice to draw it."
    )
    # the two buttons' names say what each does: no explainer line (21 Oct, Kash)
    assert "we redo the advice" not in src


def test_a_no_cure_card_does_not_also_say_less_sure(tmp_path):
    rec = _full_plan(tmp_path)
    assert rec.answer is not None
    card = _card("treat_or_remove", "today", "this disease has no cure.")
    card.if_you_do, card.if_you_do_from, card.less_sure = (
        "no known cure: bag and bin it.",
        "outcome_table",
        True,
    )
    rec.answer.do, rec.answer.headline = [card], NO_CURE_HEADLINE
    main = _render(rec).split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert "From gardening sources:" in main and "(less sure)" not in main


def test_sources_read_by_who_wrote_them_once_each(tmp_path):
    rec = _full_plan(tmp_path)
    assert rec.pack is not None
    rec.pack.sources = [
        "https://www.rhs.org.uk/a", "docs/reference/herb-care-packs.md",
        "https://archive.ahdb.org.uk/b", "https://www.rhs.org.uk/c",
    ]  # fmt: skip
    page = _render(rec)
    line = page.split("<p>Care facts: ", 1)[1].split("</p>", 1)[0]
    assert re.sub(r"<[^>]+>", "", line) == "RHS, our care notes, AHDB"


@respx.mock
def test_the_spot_page_marks_differing_timing_once(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    climate._cache.clear()
    assert "sources differ on timing" not in page.split("visually-hidden")[0]
    assert page.count('<p class="note differ-key">') == 1
    marker = page.split('<details class="differ">', 1)[1].split("</details>", 1)[0]
    assert re.search(r"<summary><span aria-hidden=\"true\">±</span> RHS: [A-Z]", marker)
    assert "<p>Garden Organic: " in marker
    # the full fence note moved to "Where this comes from"; the sun row says it short
    assert "assumes a typical 1.8 m fence about 5 m away" in page


def test_an_rhs_page_tavily_found_says_so(tmp_path):
    rec = _full_plan(tmp_path)
    assert rec.pack is not None
    rec.pack.sources = ["https://www.rhs.org.uk/a"]
    rec.pack.found_with = "tavily"
    line = _render(rec).split("<p>Care facts: ", 1)[1].split("</p>", 1)[0]
    assert re.sub(r"<[^>]+>", "", line) == "RHS (found with Tavily)"
    rec.pack.sources.append("openplantbook: x")
    line = _render(rec).split("<p>Care facts: ", 1)[1].split("</p>", 1)[0]
    assert re.sub(r"<[^>]+>", "", line) == "RHS, Open Plantbook (the RHS page found with Tavily)"
    rec.pack.sources = ["https://www.rhs.org.uk/a"]
    rec.pack.found_with = "tinyfish"
    line = _render(rec).split("<p>Care facts: ", 1)[1].split("</p>", 1)[0]
    assert re.sub(r"<[^>]+>", "", line) == "RHS"
