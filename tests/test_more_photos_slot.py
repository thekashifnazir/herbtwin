"""Kash's live look at rev 00049 (21 Oct): "not an option in the results screen to ask us for
more photos". What next offers 1 or 2 more photos of the same plant for a surer answer; the
form posts to devpost-submission's route, which sets `more_photos_on` (default off)."""

import re

from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render, _unsure_record


def _form(page: str) -> str:
    m = re.search(r'<form class="more-photos".*?</form>', page, flags=re.S)
    assert m, "no more-photos form"
    return m.group(0)


def test_what_next_offers_more_photos_when_the_route_is_live(tmp_path):
    rec = _full_plan(tmp_path)
    page = _render(rec, more_photos_on=True)
    nxt = page.split('id="next-step"', 1)[1].split("</section>", 1)[0]
    form = _form(nxt)
    assert f'action="/answers/{rec.record_id}/photos"' in form
    assert 'method="post"' in form and 'enctype="multipart/form-data"' in form
    assert re.search(r'<input type="file" name="more" accept="image/jpeg,image/png" multiple', form)
    assert "Add 1 or 2 more photos of the same plant" in nxt
    assert (
        '<button type="submit" class="quiet">Check with these photos</button>' in form
    )  # one main button a page


def test_no_offer_until_the_route_exists(tmp_path):
    assert 'class="more-photos"' not in _render(_full_plan(tmp_path))


def test_the_fresh_answer_keeps_what_they_told_us(tmp_path):
    from herbtwin.schemas import Told

    rec = _unsure_record(tmp_path)
    rec.told = Told(soil_feel="dry", question="Is it too cold?", setting="outdoor")
    form = _form(_render(rec, more_photos_on=True))
    for name, value in (
        ("soil_feel", "dry"),
        ("question", "Is it too cold?"),
        ("setting", "outdoor"),
    ):
        assert f'<input type="hidden" name="{name}" value="{value}">' in form, name


def test_the_rater_text_never_reads_the_offer(tmp_path):
    rec = _full_plan(tmp_path)
    assert plan_text(_render(rec, more_photos_on=True)) == plan_text(_render(rec))


def test_a_direction_or_a_compass_reading_rides_along(tmp_path):
    # the heading branch is where this copy could drift from the refine form's (review)
    from herbtwin.schemas import HeadingTap, Told

    (tmp_path / "a").mkdir()
    rec = _unsure_record(tmp_path / "a")
    rec.told = Told(heading=HeadingTap(direction="S"), squeeze="gritty", last_watered="today")
    form = _form(_render(rec, more_photos_on=True))
    assert (
        '<input type="hidden" name="direction" value="S">' in form and 'name="heading"' not in form
    )
    assert '<input type="hidden" name="squeeze" value="gritty">' in form
    (tmp_path / "b").mkdir()
    rec = _unsure_record(tmp_path / "b")
    rec.told = Told(heading=HeadingTap(heading=90))
    form = _form(_render(rec, more_photos_on=True))
    assert '<input type="hidden" name="heading" value="90.0">' in form
    assert '<input type="hidden" name="pitch" value="">' in form


def test_what_they_typed_is_escaped_in_the_hidden_field(tmp_path):
    from herbtwin.schemas import Told

    rec = _unsure_record(tmp_path)
    rec.told = Told(question='He said "hi" <b>')
    form = _form(_render(rec, more_photos_on=True))
    assert 'value="He said &#34;hi&#34; &lt;b&gt;"' in form
