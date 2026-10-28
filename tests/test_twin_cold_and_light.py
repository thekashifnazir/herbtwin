"""Two things the twin cannot draw or model (23 Oct judge walk of the twin front, #512): a
flowering basil outdoors in October, "Bring it indoors to a bright windowsill.", showed no
twin strip in its card, while the twin's section said "Protecting it beats leaving it. Moving
it to better light does nothing extra; watering makes it worse."

1. The strip draws soil water only. A card whose job wins on the cold (a tender plant brought
   in, a Protect it against cold nights) gets no strip: its two soil-water lines would show
   "Protect it" drier than "Leave it" (indoors, no rain) and never the cold that is the reason.
2. The twin models moving it to better light as a little faster drying, never the light
   itself. Under advice that sends the plant to the light, "does nothing extra" read as
   against it: the finding and the Compare row say the twin can't model light instead, and
   since the 28 Oct live walk (the coriander and rosemary said "Makes no difference") every
   answer does, as do a Move it to better light card and its How sure factor."""

from dataclasses import replace
from datetime import date

from herbtwin.answer import HEADLINES, TENDER_HEADLINE
from herbtwin.confidence import assess
from herbtwin.fold_titles import NO_LIGHT, compare_title, row_why
from herbtwin.plant_model import compare_actions
from herbtwin.schemas import AnalysisRecord, Answer, CompareRow
from herbtwin.stages.twin import simulate
from herbtwin.twin_chart import strip_pick, twin_chart, twin_strip
from herbtwin.web.answer_text import plan_text
from tests.test_answer_twin_front import LABELS, _card, _render, _sec
from tests.test_confidence import BASE
from tests.test_expert_review import _build, _panel
from tests.test_twin import PACK, _env, _obs
from tests.test_web_twin_chart import _record

START = date(2026, 10, 19)  # a Monday in October: a tender basil outdoors comes in


def _basil(tmp_path, *, t_min=3.0, rain=0.0, et0=2.0, primary="shelter") -> AnalysisRecord:
    """A potted basil outdoors in October, its answer built as the live site builds it: the
    twin's own views on this fortnight, three advisors saying `primary`."""
    rec = _record(tmp_path)
    assert rec.observation is not None
    rec.observation.setting = "outdoor"
    rec.pack = PACK  # basil: harmed under 10 C, so tender
    rec.state = simulate(
        _obs(1), _env(t_min=t_min, rain=rain, et0=et0, start=START), PACK, on=START
    )
    views = compare_actions(rec.state, tender=True)
    panel = _panel(primary, primary, primary, answer="Bring it in.")
    rec.answer = _build("ocimum basilicum", 10, panel, views, tender=True, container="pot")
    return rec


def _judge_walk(tmp_path) -> AnalysisRecord:
    """The judge's page: cold nights ahead and a wet fortnight, so the twin rates protecting it
    better, moving it to better light the same and watering worse."""
    rec = _basil(tmp_path, rain=6.0, et0=0.5)
    a = rec.answer
    assert a is not None and a.headline == TENDER_HEADLINE
    verdicts = {r.action: r.vs_leaving_it for r in a.compare}
    assert verdicts == {"leave_normal": "same", "water": "worse", "shelter": "better",
                        "move_light": "same"}  # fmt: skip
    return rec


# ---------- 1. no strip for a job that wins on the cold ----------


def test_bring_it_indoors_gets_no_strip_as_the_strip_draws_no_cold(tmp_path):
    rec = _judge_walk(tmp_path)
    a = rec.answer
    first = a.do[0]
    # every other gate of the strip is open: the card's line is the twin's own cold night,
    # the twin rates protecting it better, and the chart has its line to draw
    assert first.action == "shelter" and first.if_you_do_from == "plant_model"
    assert first.if_you_do.startswith("cold risk Monday")
    chart = twin_chart(rec, LABELS)
    assert chart is not None and strip_pick(chart, a) == "shelter"
    # the reason it is not drawn: soil water alone shows "Protect it" (indoors, no rain)
    # drier than "Leave it", and the cold that is the advice's reason is not on it
    by = {ln.action: ln for ln in chart.lines}
    assert by["leave_normal"].cold and not by["shelter"].cold
    assert twin_strip(chart, a) is None
    page = _render(rec)
    assert '<div class="twin-strip"' not in page
    # the card keeps its twin line in its body; the section keeps its chart and cold nights
    assert '<p class="ifdo">' in _card(page) and "cold risk Monday" in _card(page)
    assert '<figure class="twin-chart"' in _sec(page)


def test_a_protect_it_card_against_cold_nights_gets_no_strip(tmp_path):
    rec = _judge_walk(tmp_path)
    rec.answer.headline = HEADLINES["shelter"]  # not our tender line: the twin's cold alone
    assert twin_strip(twin_chart(rec, LABELS), rec.answer) is None


def test_a_bring_in_with_no_cold_night_ahead_has_no_twin_line_and_no_strip(tmp_path):
    # warm nights: the twin finds no cold to shelter it from, so our tender reason leads with
    # no twin line under it (answer.build_answer), and the card's job is still the cold
    rec = _basil(tmp_path, t_min=14.0)
    a = rec.answer
    assert a.headline == TENDER_HEADLINE and a.do[0].if_you_do_from == "none"
    assert twin_strip(twin_chart(rec, LABELS), a) is None
    assert '<div class="twin-strip"' not in _render(rec)


def test_a_water_card_keeps_its_strip(tmp_path):
    # a dry, cold fortnight: watering leads and the twin rates it better. The strip is
    # soil water, so it is drawn, cold nights or not
    rec = _basil(tmp_path, primary="water")
    a = rec.answer
    assert a.do[0].action == "water" and a.do[0].if_you_do_from == "plant_model"
    s = twin_strip(twin_chart(rec, LABELS), a)
    assert s is not None and s.lead == "water"


# ---------- 2. the twin can't model light ----------


def test_the_finding_says_the_twin_cant_model_light_under_a_bright_windowsill(tmp_path):
    a = _judge_walk(tmp_path).answer
    ft = compare_title(a, no_cure=False)
    assert ft.title == "Protecting it beats leaving it"
    # was "Moving it to better light does nothing extra; watering makes it worse"
    assert ft.peek == f"{NO_LIGHT[:1].upper()}{NO_LIGHT[1:]}; watering makes it worse"
    assert NO_LIGHT == "the twin can't model light, so moving it shows no change here"
    assert "nothing extra" not in ft.peek


def test_the_compare_row_says_not_modelled_under_a_bright_windowsill(tmp_path):
    rec = _judge_walk(tmp_path)
    page = _render(rec)
    sec = _sec(page)
    find = sec.split('<p class="ts-find">', 1)[1].split("</p>", 1)[0]
    assert "nothing extra" not in find and "the twin can&#39;t model light" in find.lower()
    table = sec.split('<table class="compare-table">', 1)[1]
    row = table.split('data-line="move_light"', 1)[1].split("</tr>", 1)[0]
    assert "The twin can&#39;t model light, so moving it shows no change here." in row
    # its tag gives no verdict either: "= Same" beside "the twin can't model light" said one
    # (28 Oct), where the chart's caption already gave none
    assert "No difference" not in row and "= Same" not in row.replace("</span> ", " ")
    assert '<span class="verdict unmodelled">Not modelled</span>' in row
    # the other rows keep their verdicts
    water = table.split('data-line="water"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="verdict worse">' in water
    # the other rows keep the twin's own reasons
    assert "Cold could harm it on Monday if left out." in sec
    # the finding and Compare are not advice: the rater text has none of it
    assert "model light" not in plan_text(page)


def test_a_move_light_card_the_twin_rates_the_same_says_it_cant_model_light(tmp_path):
    a = _judge_walk(tmp_path).answer
    a.headline = HEADLINES["move_light"]
    a.do[0].action = "move_light"
    assert compare_title(a, no_cure=False).peek.startswith("The twin can't model light")


def test_every_answer_says_the_twin_cant_model_light(tmp_path):
    # the coriander's and the rosemary's Compare said "Makes no difference" for moving it to
    # better light while the basil's said the twin can't model light (28 Oct live walk): only
    # advice that sent it to the light got the honest line. A Protect it, a treat-it like the
    # rosemary beetle sample: the same line, never "does nothing extra"
    rec = _judge_walk(tmp_path)
    a = rec.answer
    a.headline = HEADLINES["shelter"]
    ft = compare_title(a, no_cure=False)
    assert ft.peek == f"{NO_LIGHT[:1].upper()}{NO_LIGHT[1:]}; watering makes it worse"
    a.headline = "Pick the beetles off by hand."
    a.do[0].action = "treat_or_remove"
    peek = compare_title(a, False).peek.lower()
    assert NO_LIGHT in peek and "nothing extra" not in peek
    row = _render(rec).split('<table class="compare-table">', 1)[1]
    row = row.split('data-line="move_light"', 1)[1].split("</tr>", 1)[0]
    assert "The twin can&#39;t model light, so moving it shows no change here." in row
    assert "no difference" not in row.lower() and "Not modelled</span>" in row
    assert '<span class="verdict same">' not in row


def test_a_move_light_row_says_the_twin_cant_model_light_whatever_the_window():
    # the twin's own reason for a fortnight or for 14 days: never "Makes no difference"
    for why in ("no difference over the next 2 weeks", "no difference over the next 14 days"):
        row = CompareRow(action="move_light", vs_leaving_it="same", why=why)
        a = Answer.model_construct(headline="Leave it.", do=[], compare=[row])
        assert row_why(row, a) == "The twin can't model light, so moving it shows no change here."
    # other choices keep the twin's own reasons in plain words
    water = CompareRow(
        action="water", vs_leaving_it="same", why="no difference over the next 2 weeks"
    )
    assert row_why(water, a) == "Makes no difference in the next 2 weeks."
    # the twin rates moving it worse on the drying it models: that verdict stands
    dries = CompareRow(
        action="move_light", vs_leaving_it="worse", why="dries faster than leaving it"
    )
    a = Answer.model_construct(headline="Leave it.", do=[], compare=[dries])
    assert row_why(dries, a) == "It dries out faster than leaving it."


def test_a_move_light_card_and_its_factor_say_the_twin_cant_model_light(tmp_path):
    # the card's "if you do" line and the How sure factor read the twin's "same" for moving it
    # as "no difference over the next 2 weeks": no verdict on light either
    rec = _basil(tmp_path, rain=6.0, et0=0.5)
    views = compare_actions(rec.state, tender=False)
    assert views["move_light"].vs_leaving_it == "same"
    panel = _panel("move_light", "move_light", "move_light", answer="Move it into more sun.")
    a = _build("ocimum basilicum", 10, panel, views, container="pot")
    card = next(c for c in a.do if c.action == "move_light")
    assert card.if_you_do == NO_LIGHT and card.if_you_do_from == "plant_model"
    sure = assess(replace(BASE, action="move_light", view=views["move_light"]))
    assert next(f for f in sure.factors if f.name == "plant_model").detail == NO_LIGHT
