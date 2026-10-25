"""22 Oct, Kash chose "B2": each shut fold's title says what it found (Perplexity Finance's
finding-as-title), a small label above it says what the fold is, and the shut row carries its
key value (Turo). Every finding comes from the answer's own data; with nothing true to say,
the old category title stays."""

import re
from datetime import date

from herbtwin.answer import NO_CURE_HEADLINE
from herbtwin.fold_titles import (
    NOTHING_ELSE,
    compare_title,
    fold_titles,
    weather_title,
    why_title,
)
from herbtwin.schemas import CompareRow, Factor, KnowledgePack
from herbtwin.stages.twin import simulate
from herbtwin.twin_chart import twin_chart
from tests.test_twin import PACK, _env, _obs
from tests.test_web_answer_page import _card, _render, _unsure_record
from tests.test_web_twin_chart import _record

LABEL = {
    "leave_normal": "Leave it",
    "water": "Water it",
    "shelter": "Protect it (shelter or bring in)",
    "treat_or_remove": "Treat it",
}
START = date(2026, 10, 19)
HARDY = PACK.model_copy(update={"frost_damage_c": -5.0, "frost_severe_c": -10.0})


def _twin(tmp_path, cold_days=(3, 4, 9), pack: KnowledgePack = PACK):
    """A healthy outdoor basil whose twin ran on a fortnight with these cold nights."""
    rec = _record(tmp_path)
    env = _env(t_min=11.0, start=START)
    for i in cold_days:
        env.days[i].t_min, env.days[i].t_max = -9.0 if pack is HARDY else 3.0, 9.0
    rec.pack, rec.environment = pack, env
    rec.state = simulate(_obs(0), env, pack, on=START)
    rec.observation.setting = "outdoor"
    return rec


# ---------- the evidence fold: what we went on, led by what the weather holds ----------


def test_the_fold_counts_cold_spells_as_the_chart_marks_them(tmp_path):
    # site walk 2 (22 Oct): r2's title said "11 cold nights" while its chart marked 3 ❄︎.
    # Nights 3, 4 and 9 are two runs: two snowflakes on the chart, so "2 cold spells"
    rec = _twin(tmp_path)
    rec.answer.compare = _rows(("leave_normal", "same"), ("shelter", "better"))
    t = weather_title(rec)
    assert t.found and t.title == "2 cold spells in 2 weeks"
    chart = twin_chart(rec, LABEL)
    assert chart is not None
    left = next(ln for ln in chart.lines if ln.action == "leave_normal")
    assert t.title.startswith(f"{len(left.marks)} cold spells")


def test_a_hardy_plant_counts_frost_and_says_when_there_is_none(tmp_path):
    assert weather_title(_twin(tmp_path, (5,), HARDY)).title == "1 frosty spell in 2 weeks"
    assert weather_title(_twin(tmp_path, (), HARDY)).title == "No frost in 2 weeks"
    assert weather_title(_twin(tmp_path, ())).title == "No cold nights in 2 weeks"
    assert weather_title(_twin(tmp_path, (2, 3, 4, 5))).title == "1 cold spell in 2 weeks"


def test_with_no_twin_the_weather_fold_says_the_rain_due(tmp_path):
    rec = _twin(tmp_path)
    rec.state = None
    for d in rec.environment.days:
        d.rain_mm = 1.5
    # 13 forecast days of 1.5 mm, the first day is the photo's own
    assert weather_title(rec).title == "20 mm of rain due in 13 days"
    for d in rec.environment.days:
        d.rain_mm = 0.0
    assert weather_title(rec).title == "No rain due in 13 days"


def test_no_weather_is_said_once_as_the_title(tmp_path):
    rec = _twin(tmp_path)
    assert weather_title(rec, weather_failed=True).title == "No forecast this time"
    rec.environment = None
    t = weather_title(rec)
    assert t.found and t.title == "No forecast this time" and t.peek == ""


def test_indoors_the_fold_names_what_it_went_on(tmp_path):
    # 25 Oct, Kash: the card's line is the one indoor statement, so the fold no longer says
    # "Indoors: no weather needed"; it names what it went on, and still counts it
    rec = _twin(tmp_path)
    rec.observation.setting = "indoor"
    rec.pack = PACK.model_copy(update={"sources": ["openplantdb:basil"]})
    t = weather_title(rec)
    assert t.title == "Your photo and care facts" and t.kind.startswith("What we went on · ")
    assert "indoor" not in (t.kind + t.title).lower()
    rec.pack = PACK.model_copy(update={"sources": []})
    assert weather_title(rec).title == "Your photo"
    assert "weather" not in t.holds and "season" not in t.holds


def test_weather_with_no_day_to_count_keeps_the_old_title(tmp_path):
    rec = _twin(tmp_path)
    rec.state = None
    for d in rec.environment.days:
        d.is_forecast = False
    t = weather_title(rec)
    # no weather in the fold, so none in its old title either (site walk 2, 22 Oct)
    assert not t.found and t.title == "What we went on"
    assert t.peek.startswith("What the photo showed") and "weather" not in t.holds


def test_the_label_counts_the_things_the_fold_lists(tmp_path):
    # site walk 2 (22 Oct): "Weather · 3 sources" held the photo, the season, the care facts
    # and the model's assumptions, and counted sources, not those
    rec = _twin(tmp_path)
    rec.pack = PACK.model_copy(update={"sources": ["openplantdb:basil"]})
    t = weather_title(rec)
    assert t.holds == ("photo", "weather", "season", "facts", "assumes")
    assert t.kind == "What we went on · 5 things"
    rec.season, rec.answer.assumptions = None, []
    rec.pack = PACK.model_copy(update={"sources": []})
    t = weather_title(rec)
    assert t.holds == ("photo", "weather") and t.kind == "What we went on · 2 things"
    rec.observation.setting = "indoor"  # no weather indoors: one thing, never "1 things"
    assert weather_title(rec).kind == "What we went on · 1 thing"


def test_the_fold_says_its_weather_finding_inside(tmp_path):
    rec = _twin(tmp_path)
    # the nights too, so a long spell never reads as a short one (r5: 13 nights in a row)
    assert weather_title(rec).weather == "2 cold spells in 2 weeks if left out (3 nights in all)"
    one = weather_title(_twin(_dir(tmp_path, "one"), (5,), HARDY)).weather
    assert one == "1 frosty spell in 2 weeks if left out"
    rec.state = None
    for d in rec.environment.days:
        d.rain_mm = 1.5
    assert weather_title(rec).weather == "20 mm of rain due in 13 days"
    assert weather_title(rec, weather_failed=True).weather == ""


# ---------- the why fold: how many advisors said the plan ----------


def test_the_why_fold_says_all_the_advisors_agreed(tmp_path):
    rec = _twin(tmp_path)  # three advisors, each "water"
    t = why_title(rec, LABEL)
    assert t.found and t.title == "3 advisors agreed: water it"
    assert t.kind == "Why it's our best read"


def test_a_split_says_how_many_said_the_plan(tmp_path):
    rec = _unsure_record(tmp_path)  # two said leave it, one water
    t = why_title(rec, LABEL)
    assert t.title == "2 of 3 advisors said: leave it" and t.kind == "Why we're not sure"


def test_the_plan_reads_without_its_bracket(tmp_path):
    rec = _twin(tmp_path)
    rec.answer.do = [_card("shelter", "today")]
    for r in rec.answer.runs:
        r.primary = "shelter"
    assert why_title(rec, LABEL).title == "3 advisors agreed: protect it"


def test_one_advisor_is_the_advisor(tmp_path):
    rec = _twin(tmp_path)
    rec.answer.runs = rec.answer.runs[:1]
    assert why_title(rec, LABEL).title == "The advisor said: water it"


def test_a_plan_our_rules_chose_says_so(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.headline = NO_CURE_HEADLINE
    rec.answer.do = [_card("treat_or_remove", "today")]
    assert why_title(rec, LABEL).title == "Our rules chose: remove it"


def test_advisors_who_said_treat_it_never_agreed_on_remove_it(tmp_path):
    # site walk 2, r5: "3 advisors agreed: remove it" over three "treat it" asks; the no-cure
    # rule chose Remove it, and the fold says our rules did
    rec = _unsure_record(tmp_path)
    rec.answer.headline = NO_CURE_HEADLINE
    rec.answer.do = [_card("treat_or_remove", "today")]
    rec.answer.runs = [r.model_copy(update={"primary": "treat_or_remove"}) for r in rec.answer.runs]
    assert len(rec.answer.runs) == 3
    assert why_title(rec, LABEL).title == "Our rules chose: remove it"


def test_a_plan_no_advisor_said_keeps_the_old_title(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.do = [_card("shelter", "today")]
    rec.answer.factors = [f for f in rec.answer.factors if f.name != "advisor"]
    t = why_title(rec, LABEL)
    assert not t.found and t.title == "Why we're not sure"
    rec.answer.runs = []
    assert why_title(rec, LABEL).title == "Why we're not sure"
    rec.answer.factors.append(Factor(name="advisor", effect="lowers", detail="x"))
    assert not why_title(rec, LABEL).found


# ---------- the Compare fold: what beat leaving it ----------


def _rows(*rows):
    return [CompareRow(action=a, vs_leaving_it=v, why="w") for a, v in rows]


def test_compare_says_what_beats_leaving_it_and_what_did_nothing(tmp_path):
    a = _unsure_record(tmp_path).answer
    a.compare = _rows(("leave_normal", "same"), ("shelter", "better"), ("water", "same"))
    t = compare_title(a, no_cure=False)
    assert t.title == "Protecting it beats leaving it"
    assert t.peek == "Watering does nothing extra"
    assert t.kind == "Compare all choices · next 2 weeks"


def test_compare_with_nothing_better_says_so_and_names_what_harms(tmp_path):
    a = _unsure_record(tmp_path).answer
    a.compare = _rows(("leave_normal", "same"), ("water", "worse"), ("feed", "worse"))
    t = compare_title(a, no_cure=False)
    assert t.title == "Nothing beats leaving it"
    assert t.peek == "Watering and feeding make it worse"


def test_a_pest_job_the_twin_cannot_weigh_never_reads_leave_it_alone(tmp_path):
    # 23 Oct Toloka study: under "Pick the beetles off by hand", "Nothing beats leaving it"
    # read as the answer; 3 of 11 workers gave a watering instruction instead of the job
    a = _unsure_record(tmp_path).answer
    a.do = [_card("treat_or_remove", when="today")]
    a.compare = _rows(("leave_normal", "same"), ("water", "worse"), ("shelter", "same"))
    t = compare_title(a, no_cure=False)
    assert t.title == NOTHING_ELSE == "Nothing else is needed for water or frost"
    assert t.peek == "Protecting it does nothing extra; watering makes it worse"
    page = _render(_unsure_record_with(tmp_path, a))
    what = page.split('<p class="ts-what">', 1)[1].split("</p>", 1)[0]
    assert what.endswith(
        "It can't model pests or diseases, so it only checks water and frost around the job above."
    )
    assert "<strong>Nothing beats leaving it.</strong>" not in page


def _unsure_record_with(tmp_path, a):
    rec = _unsure_record(tmp_path)
    rec.answer = a
    return rec


def test_compare_names_a_second_better_choice_under_the_title(tmp_path):
    a = _unsure_record(tmp_path).answer
    a.compare = _rows(("shelter", "better"), ("move_light", "better"), ("water", "same"))
    t = compare_title(a, no_cure=False)
    assert t.title == "Protecting it beats leaving it"
    assert t.peek == "Moving it to better light helps too; watering does nothing extra"


def test_compare_under_no_cure_says_the_choices_dont_apply(tmp_path):
    a = _unsure_record(tmp_path).answer
    a.compare = []
    t = compare_title(a, no_cure=True)
    assert t.found and t.title == "No cure, so the choices don't apply"


def test_compare_with_no_verdict_keeps_the_old_title(tmp_path):
    a = _unsure_record(tmp_path).answer
    for rows in ([], _rows(("leave_normal", "same")), _rows(("water", "unknown"))):
        a.compare = rows
        t = compare_title(a, no_cure=False)
        assert not t.found and t.title == "Compare all choices (next 2 weeks)", rows


# ---------- the page ----------


def _summary(page: str, cls: str) -> str:
    return page.split(f'<details class="{cls}', 1)[1].split("</summary>", 1)[0]


def test_the_page_shows_each_finding_under_its_label(tmp_path):
    rec = _twin(tmp_path)
    rec.answer.compare = _rows(("leave_normal", "same"), ("shelter", "better"), ("water", "same"))
    rec.pack = PACK.model_copy(update={"sources": ["openplantdb:basil"]})
    page = _render(rec).replace("&#39;", "'")
    why = _summary(page, "why fold")
    assert '<span class="fold-kind">Why it\'s our best read</span>' in why
    assert '<span class="fold-title">3 advisors agreed: water it</span>' in why
    # Compare's finding heads the twin's section after the card, Compare's home since 23 Oct
    find = page.split('<p class="ts-find">', 1)[1].split("</p>", 1)[0]
    assert find == "<strong>Protecting it beats leaving it.</strong> Watering does nothing extra."
    assert '<details class="compare' not in page
    weather = _summary(page, "evidence fold")
    assert '<span class="fold-kind">What we went on · 5 things</span>' in weather
    assert '<span class="fold-title">2 cold spells in 2 weeks</span>' in weather
    body = page.split('<details class="evidence fold">', 1)[1].split("</summary>", 1)[1]
    said = "2 cold spells in 2 weeks if left out (3 nights in all), from Open-Meteo"
    assert f"<p>Weather: {said}</p>" in body
    # the folds keep their order: why, then the sources; the twin's section before both
    assert page.index('<section class="twin-sec"') < page.index('class="why fold')
    assert page.index('class="why fold') < page.index('class="evidence fold')


def test_a_fold_with_nothing_found_shows_its_old_title_and_no_label(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.do = [_card("shelter", "today")]
    rec.answer.factors = [f for f in rec.answer.factors if f.name != "advisor"]
    rec.answer.compare = _rows(("leave_normal", "same"))
    page = _render(rec).replace("&#39;", "'")
    why = _summary(page, "why fold")
    assert "fold-kind" not in why
    assert '<span class="fold-title">Why we\'re not sure</span>' in why
    # no verdict: the twin's section says none beat leaving it, its old fold's line
    find = page.split('<p class="ts-find">', 1)[1].split("</p>", 1)[0]
    assert find == "<strong>None beat leaving it.</strong>"


def test_fold_titles_gives_every_fold_its_title(tmp_path):
    rec = _twin(tmp_path)
    got = fold_titles(rec, LABEL)
    assert set(got) == {"weather", "why", "compare"}
    rec.answer = None
    assert set(fold_titles(rec, LABEL)) == {"weather", "why"}


def test_compare_never_leads_with_watering_under_another_job(tmp_path):
    # site walk 2 (22 Oct), r3: "Pick the beetles off by hand." under a Compare titled
    # "Watering beats leaving it": the main job is not one the twin compares, so a better
    # choice there is an extra, said as one
    a = _unsure_record(tmp_path).answer
    a.do[0] = a.do[0].model_copy(update={"action": "treat_or_remove"})
    a.compare = _rows(("leave_normal", "same"), ("water", "better"), ("shelter", "same"))
    t = compare_title(a, no_cure=False)
    assert "beats leaving it" not in t.title
    assert t.title == "Watering helps too"
    assert t.peek == "Protecting it does nothing extra"
    a.compare = _rows(("water", "better"), ("move_light", "better"))
    assert (
        compare_title(a, no_cure=False).title == "Watering and moving it to better light help too"
    )
    # a job the twin compares keeps the plain title
    a.do[0] = a.do[0].model_copy(update={"action": "water"})
    assert compare_title(a, no_cure=False).title == "Watering beats leaving it"


def _listed(page: str) -> tuple[int, int]:
    """The evidence fold walked as rendered: (the N its label says, the things it lists).
    A thing is a plain line or the model's assumptions; failure notes and the Ref are not."""
    fold = page.split('<details class="evidence fold">', 1)[1]
    head, body = fold.split("</summary>", 1)
    body = body.split('<p class="record">', 1)[0]
    body = re.sub(r'<details class="assumptions">.*?</details>', "<assumes/>", body, flags=re.S)
    said = re.search(r'<span class="fold-kind">What we went on · (\d+) things?</span>', head)
    assert said, head
    return int(said.group(1)), len(re.findall(r"<p>|<assumes/>", body))


def _dir(tmp_path, name):
    (tmp_path / name).mkdir()
    return tmp_path / name


def test_the_label_counts_exactly_what_the_rendered_fold_lists(tmp_path):
    from herbtwin.schemas import ProblemSeen

    cases = []
    rec = _twin(_dir(tmp_path, "a"))
    rec.answer.compare = _rows(("leave_normal", "same"), ("shelter", "better"))
    cases.append(rec)
    rec = _twin(_dir(tmp_path, "b"))
    rec.pack = PACK.model_copy(update={"sources": ["https://www.rhs.org.uk/herbs/basil"]})
    rec.problem = ProblemSeen(
        name="basil downy mildew",
        looks_like="grey fuzz under the leaves",
        source="https://www.rhs.org.uk/disease/basil-downy-mildew",
    )
    cases.append(rec)
    rec = _twin(_dir(tmp_path, "c"))
    rec.observation.setting = "indoor"  # r4: was "1 source" over two lines
    rec.pack = PACK.model_copy(update={"sources": ["openplantdb:basil"]})
    cases.append(rec)
    rec = _twin(_dir(tmp_path, "d"))
    rec.state = None  # the rain line instead of the cold one
    rec.season = None
    cases.append(rec)
    for rec in cases:
        n, listed = _listed(_render(rec))
        assert n == listed and n >= 2, (n, listed)
