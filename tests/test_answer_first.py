"""Design wave 1, A and D (Kash, 19 Oct: "go with whatever you recommend"): the answer comes
first, with the common name big, the process note folded away, and a "What next" step at the
end of the plan."""

import pytest
import respx

from herbtwin.species import name_parts


@pytest.mark.parametrize(
    ("name", "common", "parts"),
    [
        ("Ocimum basilicum", "basil", ("Basil", "Ocimum basilicum")),
        ("Ocimum basilicum (basil)", "basil", ("Basil", "Ocimum basilicum")),
        ("Mentha", "", ("Mentha", "")),
        ("Rosemary", "rosemary", ("Rosemary", "")),
        # review: a common name with its own brackets never lands in the Latin line
        ("Mentha spicata", "mint (spearmint)", ("Mint (spearmint)", "Mentha spicata")),
        ("", "basil (sweet)", ("Basil (sweet)", "")),
        ("Basil", "sweet basil", ("Sweet basil", "")),  # a common name in the Latin slot
    ],
)
def test_the_big_name_is_the_common_one_and_the_latin_goes_under_it(name, common, parts):
    assert name_parts(name, common) == parts


def _page(tmp_path):
    from tests.test_web_answer_page import _answer

    return _answer(tmp_path)


def test_the_band_leads_with_the_common_name_and_keeps_the_latin_under_it(tmp_path):
    page = _page(tmp_path)
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert "<h1>Basil</h1>" in band
    h1, latin = (
        band.index("<h1>Basil</h1>"),
        band.index('<p class="latin"><i>Ocimum basilicum</i></p>'),
    )
    assert h1 < latin < band.index('<p class="where">')


def test_the_process_note_is_folded_into_how_we_worked_it_out(tmp_path):
    from tests.test_answer_walk_fixes import _render

    rec = _rec_with_note(tmp_path)
    page = _render(rec)
    band = page.split('<div class="page-band">', 1)[1].split('id="main-action"', 1)[0]
    assert "The advisors led with" not in band
    details = page.split('<h2 id="details">How we worked it out</h2>', 1)[1]
    assert '<p class="note how-led">The advisors led with cutting it back' in details


def _rec_with_note(tmp_path):
    from tests.test_web_twin_chart import _record

    rec = _record(tmp_path)
    rec.notes = ["The advisors led with cutting it back; a tender plant left out from October "
                 "to March is protected first, so that leads."]  # fmt: skip
    return rec


def test_what_next_ends_the_plan_and_holds_i_did_it(tmp_path):
    page = _page(tmp_path)
    plan_end = page.index('<h2 id="watch">Keep an eye on</h2>')
    nxt = page.index('<h2 id="next-step">What next</h2>')
    assert plan_end < nxt < page.index('<h2 id="refine">')
    card = page[nxt:].split("</section>", 1)[0]
    assert 'id="i-did"' in card and "In a few days, send a new photo of the same plant" in card
    assert "compare" not in card  # a comparison needs a kept plant and a rule window (review)
    # "Done it?" sits inside the scripted block: no script, no button to point at
    assert card.index('id="i-did"') < card.index("Done it? Tell us.")
    main = page.split('id="main-action"', 1)[1].split("</section>", 1)[0]
    assert 'id="i-did"' not in main  # out of the main card: the reader has the whole plan first


def test_the_rater_text_leaves_what_next_out(tmp_path):
    from herbtwin.web.answer_text import plan_text

    text = plan_text(_page(tmp_path))
    assert "What next" not in text and "I did it" not in text


@respx.mock
def test_every_note_a_rule_writes_is_folded_down(tmp_path):
    # review: the real notes from decide(), not hand-written ones, so a wording change shows
    import json

    import httpx

    from herbtwin.pipeline import analyse, how_led
    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.test_expert_review import OBS
    from tests.test_pipeline import JPEG, SAMPLE, WHEN, _deps

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    cut = {"actions": ["prune", "shelter"], "primary": "prune",
           "answer": "Prune off the flower spikes.", "confidence": "high"}  # fmt: skip
    leave = {"actions": ["leave_normal"], "primary": "leave_normal",
             "answer": "Leave it.", "confidence": "high"}  # fmt: skip
    shelter = {"actions": ["shelter"], "primary": "shelter",
               "answer": "Cold nights are coming. Bring it in.", "confidence": "high"}  # fmt: skip
    for advice in ([cut] * 3, [leave, shelter, leave]):  # tender_first, follow_the_twin
        rec = analyse(_deps(tmp_path, [json.dumps(OBS)], [json.dumps(x) for x in advice]),
                      JPEG, "image/jpeg", received=WHEN)  # fmt: skip
        assert rec.notes and all(how_led(n) for n in rec.notes), rec.notes


def test_a_context_note_stays_in_the_band(tmp_path):
    # "Answering for the basil you tapped" tells the reader which plant: it stays up top
    from herbtwin.pipeline import how_led

    assert not how_led("Answering for the basil you tapped.")
    assert how_led("1 of 3 advisors said to protect it; the 2-week forecast backs them.")
    assert how_led("The advisors led with feeding it; for this plant that waits.")


def test_after_i_did_it_the_question_goes_too(tmp_path):
    page = _page(tmp_path)
    script = page.split('id="i-did"', 1)[1].split("</script>", 1)[0]
    assert 'box.querySelector(".done-it").hidden = true' in script
