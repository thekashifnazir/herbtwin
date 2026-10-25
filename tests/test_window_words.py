"""The window answer indoors, said one way in each place from one source (22 Oct): the chip
("South window, close"), the "You told us" echo ("by a south window, close") and the How sure
and advisor form ("a south-facing window, close to it") were three dicts that could drift.
And with the advice reading the window (#456), it counts as a quick question. 25 Oct, Kash on
the live page: a tap on a window sent the form at once; like the compass, it is pick, then
"Check the advice again"."""

from herbtwin import light, note_facts
from herbtwin.schemas import WINDOW, WINDOW_TEXT, Told
from tests.test_web_answer_page import _render, _unsure_record

KINDS = ("south_close", "east_west_close", "north_or_far", "no_window")


def test_one_source_holds_every_form_of_each_window_answer():
    assert tuple(WINDOW) == KINDS
    assert WINDOW["south_close"].label == "South window, close"
    assert WINDOW["south_close"].echo == "by a south window, close"
    assert WINDOW["south_close"].how_sure == "a south-facing window, close to it"
    # the chips, the How sure detail and the advisor all read it, never a copy
    assert WINDOW_TEXT == {k: w.label for k, w in WINDOW.items()}
    assert light.WINDOW_TEXT == {k: w.how_sure for k, w in WINDOW.items()}
    assert not hasattr(note_facts, "_WINDOW_SAID")
    for k in KINDS:
        assert WINDOW[k].echo in note_facts.told_echo(Told(window=k))


def _indoor(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "indoor"
    rec.answer.tell_me_key = rec.answer.tell_me = None
    return rec


def _asking(path):
    rec = _indoor(path)
    rec.answer.tell_me_key, rec.answer.tell_me = "soil_feel", "Push a finger 2 cm into the soil."
    return rec


def test_the_window_counts_as_a_quick_question(tmp_path):
    asks = ["window", "soil_feel", "last_watered", "question"]
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    assert "Make this surer: answer 3 quick questions" in _render(
        _asking(tmp_path / "a"), asks=asks
    )
    told = _asking(tmp_path / "b")
    told.told = Told(window="south_close")  # a told window is no longer open
    assert "Make this surer: answer 2 quick questions" in _render(told, asks=asks)


def test_a_window_tap_picks_and_check_the_advice_again_sends(tmp_path):
    # as the compass's direction: a tap picks a window and "Check the advice again" sends,
    # never the tap itself, alone or with other answer chips (25 Oct, Kash)
    for i, asks in enumerate(
        (["window", "question"], ["window", "soil_feel", "last_watered", "question"])
    ):
        (tmp_path / str(i)).mkdir()
        page = _render(_asking(tmp_path / str(i)), asks=asks, spot_on=True)
        form = page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
        assert '<fieldset class="picks"><legend>Pick the nearest</legend>' in form
        assert form.count('type="radio" name="window"') == 4  # radios: no script, no send
        assert "data-picks" not in form, asks
        assert (
            '<div class="actions send">\n        <button class="primary big" type="submit">Check the advice again</button>'
            in form
        )


def test_a_window_tap_does_not_send_while_the_place_box_shares_the_section(tmp_path):
    # review: with the place box beside the chips ("Where it is" asks the town too), a tap
    # on the window must not send before the town is typed
    rec = _indoor(tmp_path)
    rec.answer.tell_me_key, rec.answer.tell_me = "location", "Add a town for the weather."
    page = _render(rec, asks=["window", "question"], spot_on=True)
    form = page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert '<fieldset class="picks"><legend>Pick the nearest</legend>' in form
    assert "data-picks" not in form
