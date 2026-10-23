"""22 Oct, a gardener asked how we tell light levels indoors. We can't: the photo's exposure
is measured against the open sky, so indoors there is no reading (light.read_light), and the
page said nothing about it. One plain line by "How sure we are" says so, and asks which
window it's by, until that is told."""

from herbtwin.schemas import AnalysisRecord, Told
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render, _unsure_record

LINE = "We can't measure light indoors from a photo."
ASK = '<a href="#refine">Tell us which window it\'s by</a>'


class _ToldWindow(Told):
    """A stand-in for the window answer (the "Where is it?" question adds `Told.window` in its
    own PR): a real Told, so the page's other uses of it still work."""

    window: str | None = None


def _indoor(rec: AnalysisRecord) -> AnalysisRecord:
    assert rec.observation is not None and rec.answer is not None
    rec.observation.setting = "indoor"
    rec.answer.compare = []
    return rec


def _main(page: str) -> str:
    return page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]


def test_an_indoor_answer_says_light_is_not_measured_and_asks_for_the_window(tmp_path):
    for i, make in enumerate((_full_plan, _unsure_record)):
        (tmp_path / str(i)).mkdir()
        page = _render(_indoor(make(tmp_path / str(i))))
        main = _main(page)
        assert f'<p class="note indoor-light">{LINE} {ASK}.</p>' in main, make.__name__
        # by How sure we are: after its line, before the sources (under the card since 23 Oct)
        assert main.index('<p class="sure">') < main.index("indoor-light")
        assert page.index("indoor-light") < page.index('<p class="sources-line">')
        assert page.count("indoor-light") == 1
        # the link opens the folded Tell us more, as the Make this surer buttons do
        assert "document.querySelectorAll('a[href=\"#refine\"]')" in page


def test_the_line_goes_once_the_window_is_told(tmp_path):
    rec = _indoor(_full_plan(tmp_path))
    rec.told = _ToldWindow(window="south_close")
    page = _render(rec)
    assert "indoor-light" not in page and "measure light indoors" not in page
    # a told answer without a window still asks
    rec.told = _ToldWindow(soil_feel="dry")
    assert "indoor-light" in _render(rec)
    rec.told = Told(soil_feel="dry")  # no window field at all yet: still asks
    assert "indoor-light" in _render(rec)


def test_an_outdoor_answer_has_no_light_line(tmp_path):
    for setting in ("outdoor", "unknown"):
        (tmp_path / setting).mkdir()
        rec = _full_plan(tmp_path / setting)
        assert rec.observation is not None
        rec.observation.setting = setting
        page = _render(rec)
        assert "indoor-light" not in page and "measure light indoors" not in page, setting


def test_the_rater_text_is_unchanged_by_the_line(tmp_path):
    # the line is about what we can't measure, not advice: raters never read it
    rec = _indoor(_full_plan(tmp_path))
    asked = _render(rec)
    assert "indoor-light" in asked
    rec.told = _ToldWindow(window="south_close")
    told = _render(rec)
    assert "indoor-light" not in told
    assert plan_text(asked) == plan_text(told)
    assert "measure light" not in plan_text(asked) and "window" not in plan_text(asked)


def test_no_window_ask_beside_a_retake_or_a_no_cure_answer(tmp_path):
    # review: "Send a sharper photo" or a remove-it answer is not helped by the window
    from herbtwin.answer import NO_CURE_HEADLINE

    rough = _indoor(_unsure_record(tmp_path))
    rough.answer.photo_issue = "blurry"
    assert "indoor-light" not in _render(rough)
    (tmp_path / "gone").mkdir()
    gone = _indoor(_full_plan(tmp_path / "gone"))
    gone.answer.headline = NO_CURE_HEADLINE
    assert "indoor-light" not in _render(gone)


def test_the_link_lands_inside_the_tell_us_more_fold(tmp_path):
    page = _render(_indoor(_full_plan(tmp_path)))
    fold = page.split('<details class="tell-more"', 1)[1].split("</details>", 1)[0]
    assert 'id="refine"' in fold
