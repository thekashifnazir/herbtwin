"""22 Oct, a gardener asked how we tell light levels indoors. We can't: the photo's exposure
is measured against the open sky, so indoors there is no reading (light.read_light), and the
page said nothing about it. 25 Oct, Kash, for consistency with outdoor: one honest line on
every indoor answer, with no question, and the window asked in Tell us more, under Where it
is, as outdoors asks which way it faces."""

from herbtwin.schemas import AnalysisRecord, Told
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render, _unsure_record

LINE = "Indoor herbs get a simpler answer: there's no weather to test choices against."
ASKS = ["soil_feel", "last_watered", "window", "question"]  # asks.questions_for, indoors


def _indoor(rec: AnalysisRecord) -> AnalysisRecord:
    assert rec.observation is not None and rec.answer is not None
    rec.observation.setting = "indoor"
    rec.answer.compare = []
    return rec


def _main(page: str) -> str:
    return page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]


def _where(page: str) -> str:
    form = page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    return form.split('<div class="part where', 1)[1].split('<div class="part ', 1)[0]


def test_an_indoor_answer_says_once_why_it_is_simpler(tmp_path):
    for i, make in enumerate((_full_plan, _unsure_record)):
        (tmp_path / str(i)).mkdir()
        page = _render(_indoor(make(tmp_path / str(i))), asks=ASKS)
        main = _main(page)
        assert f'<p class="note indoor-light">{LINE}</p>' in main, make.__name__
        # by How sure we are: after its line, before the sources (under the card since 23 Oct)
        assert main.index('<div class="sure">') < main.index('class="note indoor-light"')
        assert page.index('class="note indoor-light"') < page.index('<p class="sources-line">')
        # one statement, no question, nothing to press in the card
        assert page.count(LINE) == 1 and "Indoors: advice for room" not in page
        assert "no weather needed" not in page  # the evidence fold's title went too (25 Oct)
        assert "Which window" not in main and 'name="window"' not in main


def test_the_window_is_asked_under_where_it_is_like_the_direction(tmp_path):
    page = _render(_indoor(_full_plan(tmp_path)), asks=ASKS)
    where = _where(page)
    assert where.startswith('"><h3>Where it is</h3>') or "<h3>Where it is</h3>" in where[:40]
    # set out as the compass: the question in bold, then the picks, one radio a window
    assert '<div class="compass window-q"><p><strong>Which window is it by?</strong></p>' in where
    assert where.index("Which window is it by?") < where.index('<fieldset class="picks">')
    assert where.count('type="radio" name="window"') == 4 and " checked" not in where
    assert page.count("Which window is it by?") == 1


def test_a_told_window_shows_picked_and_the_line_stays_the_same(tmp_path):
    rec = _indoor(_full_plan(tmp_path))
    rec.told = Told(window="south_close")
    page = _render(rec, asks=ASKS)
    where = _where(page)
    assert 'value="south_close" checked' in where and where.count(" checked") == 1
    assert page.count(LINE) == 1 and "leans on your photo" not in page


def test_make_this_surer_counts_the_open_window(tmp_path):
    # as outdoors counts the direction: the untold window is one quick question, and the
    # card points to it even on an answer we are sure of (the card no longer asks it)
    rec = _indoor(_full_plan(tmp_path))
    rec.answer.level, rec.answer.tell_me = "sure", None
    page = _render(rec, asks=ASKS)
    assert "Make this surer: answer 3 quick questions" in _main(page)
    page = _render(rec, asks=["window", "question"])
    assert "Make this surer: answer 1 quick question<" in _main(page)
    rec.told = Told(window="south_close")
    page = _render(rec, asks=["window", "question"])
    assert "Make this surer: answer" not in page


def test_an_outdoor_answer_has_no_indoor_line(tmp_path):
    for setting in ("outdoor", "unknown"):
        (tmp_path / setting).mkdir()
        rec = _full_plan(tmp_path / setting)
        assert rec.observation is not None
        rec.observation.setting = setting
        page = _render(rec)
        assert 'class="note indoor-light"' not in page and LINE not in page, setting


def test_the_rater_text_is_unchanged_by_the_line(tmp_path):
    # the line is about what we can't test, not advice: raters never read it
    rec = _indoor(_full_plan(tmp_path))
    indoor = _render(rec, asks=ASKS)
    assert LINE in indoor
    rec.observation.setting = "outdoor"
    assert plan_text(indoor) == plan_text(_render(rec, asks=ASKS))
    assert "simpler answer" not in plan_text(indoor)


def test_a_retake_or_no_cure_says_it_once_too_and_asks_no_window(tmp_path):
    # the line has no question now, so it holds on a retake or a remove-it answer as well;
    # the window is not asked there (asks.questions_for), so the fold has no window picks
    from herbtwin.answer import NO_CURE_HEADLINE

    rough = _indoor(_unsure_record(tmp_path))
    rough.answer.photo_issue = "blurry"
    (tmp_path / "gone").mkdir()
    gone = _indoor(_full_plan(tmp_path / "gone"))
    gone.answer.headline = NO_CURE_HEADLINE
    for rec in (rough, gone):
        page = _render(rec, asks=["question"])
        assert page.count(LINE) == 1 and "Indoors: advice for room" not in page
        assert 'name="window"' not in page


def test_the_link_lands_inside_the_tell_us_more_fold(tmp_path):
    page = _render(_indoor(_full_plan(tmp_path)), asks=ASKS)
    fold = page.split('<details class="tell-more"', 1)[1].split("</details>", 1)[0]
    assert 'id="refine"' in fold and "Which window is it by?" in fold


def test_indoors_the_assumptions_are_ours_not_a_plant_models(tmp_path):
    # 25 Oct real-upload render: no plant model runs indoors, so its heading can't name one;
    # outdoors it stays as it was
    rec = _full_plan(tmp_path)
    assert rec.answer.assumptions  # the fold lists them
    outdoor = _render(rec, asks=ASKS)
    assert (
        '<summary class="fold-label went-assumed">What the plant model assumes</summary>' in outdoor
    )
    assert "What we assumed" not in outdoor
    indoor = _render(_indoor(rec), asks=ASKS)
    assert '<summary class="fold-label went-assumed">What we assumed</summary>' in indoor
    assert "plant model assumes" not in indoor
