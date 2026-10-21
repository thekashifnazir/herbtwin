from datetime import UTC, datetime, timedelta

from herbtwin.history import (
    Evidence,
    Plant,
    StoredAnswer,
    candidates,
    genus_of,
    last_decline,
    recent_visits,
    trend_line,
)
from herbtwin.schemas import Location, Observation, ProblemSeen, Told

NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)
HERE = Location(lat=51.5, lon=-0.12, source="typed")


def _plant(pid, species="salvia officinalis", lat=51.5, lon=-0.12):
    return Plant(
        id=pid,
        name=pid,
        species=species,
        genus=genus_of(species),
        place_lat=lat,
        place_lon=lon,
        created_at=NOW - timedelta(days=90),
    )


def _obs(stress=1, decline=0, colour="green"):
    return Observation(
        species=[],
        is_plant=True,
        water_stress=stress,
        decline=decline,
        leaf_colour=colour,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="dry",
    )


def _ans(pid, days_ago, **kw):
    when = NOW - timedelta(days=days_ago)
    return StoredAnswer(
        id=f"{pid}-{days_ago}",
        plant_id=pid,
        taken_at=when,
        created_at=when,
        photo_path=None,
        observation=_obs(**kw),
        evidence=Evidence(
            location=HERE,
            taken_at_source="exif",
            environment=None,
            pack=None,
            season=None,
            notes=[],
            failures=[],
            season_missing=None,
            weather_missing=None,
        ),
        answer=None,
        told=Told(soil_feel="damp"),
    )


def test_genus_of():
    assert genus_of("Salvia officinalis") == "salvia" and genus_of("") == ""


def test_two_sages_in_one_trough_are_both_offered_newest_first():
    plants = [_plant("s1"), _plant("s2"), _plant("mint", species="mentha spicata")]
    latest = {"s1": _ans("s1", 20), "s2": _ans("s2", 3), "mint": _ans("mint", 1)}
    got = candidates(
        plants,
        latest,
        species="salvia officinalis",
        genus="salvia",
        unsure=False,
        place=HERE,
        now=NOW,
    )
    assert [p.id for p in got] == ["s2", "s1"]


def test_other_place_old_visit_or_no_visit_is_not_offered():
    plants = [_plant("far", lat=52.0), _plant("old"), _plant("never")]
    latest = {"far": _ans("far", 1), "old": _ans("old", 61)}
    assert (
        candidates(
            plants,
            latest,
            species="salvia officinalis",
            genus="salvia",
            unsure=False,
            place=HERE,
            now=NOW,
        )
        == []
    )


def test_genus_counts_only_when_the_species_is_unsure():
    plants = [_plant("purple", species="salvia purpurascens")]
    latest = {"purple": _ans("purple", 2)}
    kw = dict(species="salvia officinalis", genus="salvia", place=HERE, now=NOW)
    assert candidates(plants, latest, unsure=False, **kw) == []
    assert [p.id for p in candidates(plants, latest, unsure=True, **kw)] == ["purple"]


def test_no_place_matches_only_plants_with_no_place():
    plants = [_plant("placed"), _plant("loose", lat=None, lon=None)]
    latest = {"placed": _ans("placed", 1), "loose": _ans("loose", 1)}
    got = candidates(
        plants,
        latest,
        species="salvia officinalis",
        genus="salvia",
        unsure=False,
        place=None,
        now=NOW,
    )
    assert [p.id for p in got] == ["loose"]


def test_recent_visits_are_the_last_three_in_sixty_days():
    answers = [_ans("p", d) for d in (1, 5, 10, 30, 70)]
    got = recent_visits(answers, NOW)
    assert [v.taken_at.day for v in got] == [19, 15, 10]
    assert got[0].told == "soil 2 cm down: damp"


def test_trend_line_names_what_moved_since_the_last_visit():
    last = _ans("p", 3, stress=1, decline=1, colour="some_yellow")
    now_obs = _obs(stress=2, decline=1, colour="green")
    assert trend_line(now_obs, last) == "droop worse since 17 Oct; leaves greener since 17 Oct"
    assert trend_line(_obs(stress=1, decline=1, colour="some_yellow"), last) == (
        "no change since 17 Oct"
    )
    unseen = _obs(stress=1, decline=2, colour="not_visible")
    assert trend_line(unseen, last) == "more dead or brown since 17 Oct"


def test_trend_line_sees_a_problem_that_came_or_went():
    # 19 Oct walk: a healthy basil, then a mildewed one, read "no change since 18 Oct"
    mildew = ProblemSeen(name="basil downy mildew", looks_like="grey fuzz", source="u")
    healthy = _ans("p", 3)
    sick = healthy.model_copy(
        update={"evidence": healthy.evidence.model_copy(update={"problem": mildew})}
    )
    assert trend_line(_obs(), healthy, mildew) == "signs of basil downy mildew, new since 17 Oct"
    unsure = mildew.model_copy(update={"sure": False})
    assert trend_line(_obs(), healthy, unsure) == "possible basil downy mildew, new since 17 Oct"
    assert trend_line(_obs(), sick, mildew) == "no change since 17 Oct"
    # no finding now may only mean the second look did not run: never "it went"
    assert trend_line(_obs(), sick) == "no change since 17 Oct"


def test_trend_line_says_when_the_overall_look_moved_with_nothing_else():
    fine = _ans("p", 3)
    fine.observation.fine_leave_it = True
    assert trend_line(_obs(), fine) == "looks less healthy since 17 Oct"
    assert trend_line(_obs(stress=2), fine) == "droop worse since 17 Oct"  # the reason given
    well = _obs()
    well.fine_leave_it = True
    assert trend_line(well, _ans("p", 3)) == "looks healthier since 17 Oct"


def test_last_decline_uses_only_the_last_thirty_days():
    assert last_decline([_ans("p", 40, decline=0)], NOW) is None
    assert last_decline([_ans("p", 2, decline=1), _ans("p", 9, decline=0)], NOW) == 1


def test_a_photo_time_without_a_zone_compares_with_stored_times():
    # EXIF times carry no zone; Postgres hands back zoned ones. Both are read as UTC.
    naive_now = NOW.replace(tzinfo=None)
    answers = [_ans("p", 2, decline=1)]
    assert [v.taken_at.day for v in recent_visits(answers, naive_now)] == [18]
    assert last_decline(answers, naive_now) == 1
    plants = [_plant("p")]
    got = candidates(
        plants,
        {"p": answers[0]},
        species="salvia officinalis",
        genus="salvia",
        unsure=False,
        place=HERE,
        now=naive_now,
    )
    assert [p.id for p in got] == ["p"]
    naive = _ans("p", 3).model_copy(
        update={"taken_at": (NOW - timedelta(days=3)).replace(tzinfo=None)}
    )
    assert StoredAnswer.model_validate(naive.model_dump()).taken_at.tzinfo is not None


def test_recent_visits_carry_the_score_line_of_the_answer_it_was_asked_under():
    newer = _ans("p", 2)
    older = _ans("p", 5)
    visits = recent_visits(
        [newer, older], NOW, lines={newer.id: "Last advice: water (you did it)."}
    )
    assert visits[0].scored == "Last advice: water (you did it)." and visits[1].scored == ""


def test_the_chat_history_trend_uses_the_answers_own_finding():
    # web/followup._history: the chat's HISTORY compares the stored answer's own finding
    from herbtwin.history import MemoryHistory
    from herbtwin.web.accounts import Person
    from herbtwin.web.followup import _history

    store = MemoryHistory().for_user("u1")
    mildew = ProblemSeen(name="basil downy mildew", looks_like="grey fuzz", source="u")
    pid = store.create_plant("Basil", "ocimum basilicum", "ocimum", HERE).id
    healthy, now = _ans(pid, 3), _ans(pid, 0)
    now = now.model_copy(update={"evidence": now.evidence.model_copy(update={"problem": mildew})})
    store.add_answer(healthy)
    store.add_answer(now)
    h = _history(Person("u1", "a@b.co", store), now)
    assert h is not None and h.trend == "signs of basil downy mildew, new since 17 Oct"
