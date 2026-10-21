import uuid
from datetime import UTC, datetime, timedelta

import pytest

from herbtwin.history import (
    AdviceScore,
    ChatMessage,
    Evidence,
    HistoryError,
    HistoryStore,
    MemoryHistory,
    StoredAnswer,
    UserSettings,
)
from herbtwin.schemas import Location, Observation, Prediction, SpeciesCandidate

T0 = datetime(2026, 10, 6, 10, tzinfo=UTC)
# fresh per run: the local database keeps rows from earlier runs
ID0, ID1, ID2, ID3, ID4, REM1, REM2 = (uuid.uuid4().hex for _ in range(7))
# the chat tests' own answers: the local database keeps rows across tests in one run
CHAT1, CHAT2, CHAT3 = (uuid.uuid4().hex for _ in range(3))
PLACE = Location(lat=51.5, lon=-0.12, source="typed", label="London")


def _obs(stress=1, decline=0):
    return Observation(
        species=[SpeciesCandidate(name="Salvia officinalis", common_name="sage", confidence=0.9)],
        is_plant=True,
        water_stress=stress,
        decline=decline,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="dry",
    )


def _answer(aid, plant_id, when=T0, stress=1):
    return StoredAnswer(
        id=aid,
        plant_id=plant_id,
        taken_at=when,
        created_at=when,
        photo_path=None,
        observation=_obs(stress),
        evidence=Evidence(
            location=PLACE,
            taken_at_source="exif",
            environment=None,
            pack=None,
            season=None,
            notes=[],
            failures=[],
            season_missing=None,
            weather_missing="indoors",
        ),
        answer=None,
        told=None,
    )


@pytest.fixture(params=["memory", pytest.param("supabase", marks=pytest.mark.supabase)])
def two_people(request) -> tuple[HistoryStore, HistoryStore]:
    if request.param == "memory":
        hist = MemoryHistory()
        return hist.for_user("user-a"), hist.for_user("user-b")
    from herbtwin.adapters.supabase_store import SupabaseHistoryStore
    from tests.supabase_local import local_env, signed_up

    env = local_env()
    (ta, ua), (tb, ub) = signed_up(env), signed_up(env)
    return (
        SupabaseHistoryStore(env["API_URL"], env["PUBLISHABLE_KEY"], ta, ua),
        SupabaseHistoryStore(env["API_URL"], env["PUBLISHABLE_KEY"], tb, ub),
    )


def test_a_plant_and_its_answers_round_trip(two_people):
    a, _ = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    assert p.place_lat == 51.5 and [x.name for x in a.list_plants()] == ["Sage"]
    a.add_answer(_answer(ID0, p.id, T0 - timedelta(days=3), stress=2))
    a.add_answer(_answer(ID1, p.id, T0, stress=1))
    got = a.answers_for(p.id)
    assert [x.id for x in got] == [ID1, ID0]  # newest first
    assert got[1].observation.water_stress == 2 and got[1].evidence.weather_missing == "indoors"
    assert a.latest_by_plant()[p.id].id == ID1


def test_people_never_see_each_others_plants(two_people):
    a, b = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    a.add_answer(_answer(ID2, p.id))
    assert b.list_plants() == [] and b.get_answer(ID2) is None
    assert b.answers_for(p.id) == [] and b.latest_by_plant() == {}
    b.rename_plant(p.id, "Mine now")
    b.delete_plant(p.id)
    assert a.list_plants()[0].name == "Sage"


def test_update_rename_and_delete(two_people):
    a, _ = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", None)
    a.add_answer(_answer(ID3, p.id))
    from herbtwin.schemas import Told

    a.update_answer(ID3, None, Told(soil_feel="damp"))
    assert a.get_answer(ID3).told.soil_feel == "damp"
    a.rename_plant(p.id, "Trough sage")
    assert a.list_plants()[0].name == "Trough sage"
    path = a.put_photo(ID3, b"jpeg", b"thumb")
    assert path.endswith(ID3 + ".jpg") and a.photo_url(path) is not None
    a.delete_plant(p.id)
    assert a.list_plants() == [] and a.get_answer(ID3) is None
    assert a.photo_url(path) is None  # the plant's photos go with it


def test_an_answer_cannot_hang_off_someone_elses_plant(two_people):
    a, b = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", None)
    with pytest.raises(HistoryError):
        b.add_answer(_answer(ID4, p.id))
    assert a.answers_for(p.id) == []


def test_answer_ids_read_back_in_the_apps_form():
    # Postgres returns a uuid with hyphens; the app's answer ids are 32 hex characters
    a = _answer("11111111-1111-1111-1111-111111111111", "p")
    assert a.id == "1" * 32


def test_chat_round_trips_in_order(two_people):
    a, _ = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    a.add_answer(_answer(CHAT1, p.id))
    a.add_chat(CHAT1, ChatMessage(role="user", content="what if I water it?"))
    tools = [{"name": "run_scenario", "arguments": {"action": "water"}}]
    a.add_chat(CHAT1, ChatMessage(role="assistant", content="Worse.", tools=tools))
    got = a.chat_for(CHAT1)
    assert [(m.role, m.content) for m in got] == [
        ("user", "what if I water it?"),
        ("assistant", "Worse."),
    ]
    assert got[1].tools[0]["name"] == "run_scenario"


def test_nobody_chats_on_someone_elses_answer(two_people):
    a, b = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    a.add_answer(_answer(CHAT2, p.id))
    with pytest.raises(HistoryError):
        b.add_chat(CHAT2, ChatMessage(role="user", content="hi"))
    a.add_chat(CHAT2, ChatMessage(role="user", content="mine"))
    assert b.chat_for(CHAT2) == []


def test_deleting_a_plant_deletes_its_chat(two_people):
    a, _ = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    a.add_answer(_answer(CHAT3, p.id))
    a.add_chat(CHAT3, ChatMessage(role="user", content="hi"))
    a.delete_plant(p.id)
    assert a.chat_for(CHAT3) == []


SC1, SC2, SC3, SC4, SC5, SC6 = (uuid.uuid4().hex for _ in range(6))
PRED = Prediction(
    action="water", signal="posture", expected="less", window_days=(1, 7), before=2, source="t"
)


def _score(plant_id, earlier, later, result="improved"):
    return AdviceScore(
        plant_id=plant_id,
        earlier_answer_id=earlier,
        later_answer_id=later,
        prediction=PRED,
        did_it="yes",
        result=result,
        scored_at=T0 + timedelta(days=2),
    )


def _two_visits(store, first, second):
    p = store.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    store.add_answer(_answer(first, p.id))
    store.add_answer(_answer(second, p.id, when=T0 + timedelta(days=2)))
    return p


def test_scores_are_kept_per_plant_and_private(two_people):
    a, b = two_people
    p = _two_visits(a, SC1, SC2)
    a.add_score(_score(p.id, SC1, SC2))
    [s] = a.scores_for(p.id)
    assert (s.earlier_answer_id, s.later_answer_id, s.result) == (SC1, SC2, "improved")
    assert s.prediction.signal == "posture"
    assert b.scores_for(p.id) == []


def test_a_score_cannot_hang_off_someone_elses_answers(two_people):
    a, b = two_people
    p = _two_visits(a, SC3, SC4)
    with pytest.raises(HistoryError):
        b.add_score(_score(p.id, SC3, SC4))


def test_a_pair_is_scored_once_and_goes_with_the_plant(two_people):
    a, _ = two_people
    p = _two_visits(a, SC5, SC6)
    a.add_score(_score(p.id, SC5, SC6))
    with pytest.raises(HistoryError):
        a.add_score(_score(p.id, SC5, SC6, result="worse"))
    a.delete_plant(p.id)
    assert a.scores_for(p.id) == []


def test_a_photo_reads_back_for_its_owner_only(two_people):
    a, b = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", PLACE)
    aid = uuid.uuid4().hex
    a.add_answer(_answer(aid, p.id))
    path = a.put_photo(aid, b"\xff\xd8\xffjpeg", b"\xff\xd8\xffthumb")
    assert a.get_photo(path) == b"\xff\xd8\xffjpeg"
    try:
        theirs = b.get_photo(path)
    except HistoryError:
        theirs = None
    assert theirs is None


def test_settings_default_to_not_sharing_and_never_asked(two_people):
    a, _ = two_people
    assert a.get_settings() == UserSettings()


def test_the_sharing_choice_is_kept_changed_and_private(two_people):
    a, b = two_people
    a.set_sharing(True, T0)
    assert a.get_settings() == UserSettings(share_scored_pairs=True, asked_at=T0)
    later = T0 + timedelta(hours=1)
    a.set_sharing(False, later)
    assert a.get_settings() == UserSettings(share_scored_pairs=False, asked_at=later)
    assert b.get_settings() == UserSettings()


def _reminder(aid, plant_id):
    from herbtwin.reminders import Reminder

    return Reminder(
        answer_id=aid,
        plant_id=plant_id,
        plant_name="Sage",
        action="water it",
        taken_at=T0,
        due_on=(T0 + timedelta(days=4)).date(),
        last_on=(T0 + timedelta(days=7)).date(),
    )


def test_a_reminder_is_kept_read_back_and_removed(two_people):
    a, _ = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", None)
    a.add_answer(_answer(REM1, p.id))
    assert a.get_reminder(REM1) is None
    a.set_reminder(REM1, _reminder(REM1, p.id))
    a.set_reminder(REM1, _reminder(REM1, p.id))  # ticking twice keeps one
    got = a.get_reminder(REM1)
    assert got is not None and got.answer_id == REM1 and got.due_on == _reminder(REM1, p.id).due_on
    assert got.sent_at is None and got.off_at is None
    a.set_reminder(REM1, None)
    assert a.get_reminder(REM1) is None


def test_a_reminder_is_private_and_cannot_hang_off_someone_elses_answer(two_people):
    a, b = two_people
    p = a.create_plant("Sage", "salvia officinalis", "salvia", None)
    a.add_answer(_answer(REM2, p.id))
    a.set_reminder(REM2, _reminder(REM2, p.id))
    assert b.get_reminder(REM2) is None
    with pytest.raises(HistoryError):
        b.set_reminder(REM2, _reminder(REM2, p.id))
    b.set_reminder(REM2, None)  # deleting someone else's reminder does nothing
    assert a.get_reminder(REM2) is not None
