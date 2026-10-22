"""22 Oct, Kash chose "B2": each shut fold's title says what it found (Perplexity Finance's
finding-as-title), a small label above it says what the fold is, and the shut row carries its
key value (Turo). Every finding comes from the answer's own data; with nothing true to say,
the old category title stays."""

from datetime import date

from herbtwin.answer import NO_CURE_HEADLINE
from herbtwin.fold_titles import compare_title, fold_titles, weather_title, why_title
from herbtwin.schemas import CompareRow, Factor, KnowledgePack
from herbtwin.stages.twin import simulate
from tests.test_twin import PACK, _env, _obs
from tests.test_web_answer_page import _card, _render, _unsure_record
from tests.test_web_twin_chart import _record

LABEL = {
    "leave_normal": "Leave it",
    "water": "Water it",
    "shelter": "Protect it (shelter or bring in)",
    "treat_or_remove": "Treat it",
}
NAMES = {"rhs.org.uk": "RHS"}
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


# ---------- the sources fold: what the weather holds ----------


def test_the_weather_fold_counts_the_twins_cold_nights(tmp_path):
    t = weather_title(_twin(tmp_path), NAMES)
    assert t.found and t.title == "3 cold nights in 2 weeks"


def test_a_hardy_plant_counts_frost_and_says_when_there_is_none(tmp_path):
    assert weather_title(_twin(tmp_path, (5,), HARDY), NAMES).title == "1 frosty night in 2 weeks"
    assert weather_title(_twin(tmp_path, (), HARDY), NAMES).title == "No frost in 2 weeks"
    assert weather_title(_twin(tmp_path, ()), NAMES).title == "No cold nights in 2 weeks"


def test_with_no_twin_the_weather_fold_says_the_rain_due(tmp_path):
    rec = _twin(tmp_path)
    rec.state = None
    for d in rec.environment.days:
        d.rain_mm = 1.5
    # 13 forecast days of 1.5 mm, the first day is the photo's own
    assert weather_title(rec, NAMES).title == "20 mm of rain due in 13 days"
    for d in rec.environment.days:
        d.rain_mm = 0.0
    assert weather_title(rec, NAMES).title == "No rain due in 13 days"


def test_no_weather_is_said_once_as_the_title(tmp_path):
    rec = _twin(tmp_path)
    assert weather_title(rec, NAMES, weather_failed=True).title == "No forecast this time"
    rec.environment = None
    t = weather_title(rec, NAMES)
    assert t.found and t.title == "No forecast this time" and t.peek == ""


def test_indoors_the_fold_says_no_weather_is_needed(tmp_path):
    rec = _twin(tmp_path)
    rec.observation.setting = "indoor"
    t = weather_title(rec, NAMES)
    assert t.title == "Indoors: no weather needed" and t.kind.startswith("Photo and sources")


def test_weather_with_no_day_to_count_keeps_the_old_title(tmp_path):
    rec = _twin(tmp_path)
    rec.state = None
    for d in rec.environment.days:
        d.is_forecast = False
    t = weather_title(rec, NAMES)
    assert not t.found and t.title == "Weather, forecast and sources"
    assert t.peek.startswith("What the photo showed")


def test_the_label_counts_sources_as_the_fold_names_them(tmp_path):
    rec = _twin(tmp_path)
    rec.season = None
    rec.pack = PACK.model_copy(
        update={
            "sources": [
                "https://www.rhs.org.uk/herbs/basil",
                "https://www.rhs.org.uk/herbs/basil/grow",  # RHS again: one source
                "docs/reference/herb-care-packs.md",
            ]
        }
    )
    assert weather_title(rec, NAMES).kind == "Weather · 2 sources"
    rec.pack = PACK  # none named: no count, never "0 sources"
    assert weather_title(rec, NAMES).kind == "Weather"


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
    page = _render(rec).replace("&#39;", "'")
    why = _summary(page, "why fold")
    assert '<span class="fold-kind">Why it\'s our best read</span>' in why
    assert '<span class="fold-title">3 advisors agreed: water it</span>' in why
    compare = _summary(page, "compare fold")
    assert compare.startswith(' fold-twin" open>')  # the twin ran: Compare stays open
    assert '<span class="fold-title">Protecting it beats leaving it</span>' in compare
    assert '<span class="fold-peek">Watering does nothing extra</span>' in compare
    weather = _summary(page, "evidence fold")
    assert '<span class="fold-kind">Weather' in weather
    assert '<span class="fold-title">3 cold nights in 2 weeks</span>' in weather
    # the folds keep their order: why, Compare, then the sources
    assert page.index('class="why fold') < page.index('class="compare fold')
    assert page.index('class="compare fold') < page.index('class="evidence fold')


def test_a_fold_with_nothing_found_shows_its_old_title_and_no_label(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.do = [_card("shelter", "today")]
    rec.answer.factors = [f for f in rec.answer.factors if f.name != "advisor"]
    rec.answer.compare = _rows(("leave_normal", "same"))
    page = _render(rec).replace("&#39;", "'")
    why = _summary(page, "why fold")
    assert "fold-kind" not in why
    assert '<span class="fold-title">Why we\'re not sure</span>' in why
    compare = _summary(page, "compare fold")
    assert "fold-kind" not in compare
    assert '<span class="fold-title">Compare all choices (next 2 weeks)</span>' in compare
    assert "None beat leaving it, tested on your plant's twin" in compare


def test_fold_titles_gives_every_fold_its_title(tmp_path):
    rec = _twin(tmp_path)
    got = fold_titles(rec, LABEL, NAMES)
    assert set(got) == {"weather", "why", "compare"}
    rec.answer = None
    assert set(fold_titles(rec, LABEL, NAMES)) == {"weather", "why"}
