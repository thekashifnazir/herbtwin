import json
from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin import voice
from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from tests.test_web import ADV, OBS, OCT_4, SAMPLE, _first

KEY = "test-eleven-key"
SAID = "Give me a drink today, please. My soil is dry and no rain is due."


def _rec(name="Ocimum basilicum", common="basil", because="the soil is dry and no rain is due"):
    do = SimpleNamespace(
        when="today",
        action="water",
        because=because,
        if_you_do="it perks up",
        if_you_do_from="plant_model",
    )
    answer = SimpleNamespace(headline="Water it today", do=[do], dont=None, dont_if_dry=False)
    obs = SimpleNamespace(species=[SimpleNamespace(name=name, common_name=common)])
    return SimpleNamespace(record_id="r1", observation=obs, answer=answer)


class _Raises(MockAdapter):
    def complete(self, system, user, *, max_tokens=1024):
        raise AdapterError("down")


def test_a_clean_line_passes_the_check():
    assert voice.checked(f'"{SAID}"', _rec()) == SAID


@pytest.mark.parametrize(
    "line",
    [
        "Water me 3 times today.",  # a number the answer does not hold
        "Water me on Thursday, when it's dry.",  # a day the answer does not name
        "Water me tonight.",  # a time the answer does not give
        "Give me ten minutes of water.",  # a count spelled out
        "**Water me** today.",  # markdown is not spoken
        "(sighs) Water me today.",  # a stage direction
        "word " * (voice.MAX_WORDS + 1),
        "",
    ],
)
def test_lines_that_add_or_cannot_be_spoken_fail_the_check(line):
    assert voice.checked(line, _rec()) is None


def test_a_number_and_day_the_answer_holds_may_be_said():
    rec = _rec(because="2 mm of rain is due on Thursday")
    assert voice.checked("Hold off: 2 mm of rain comes Thursday.", rec)


def test_a_number_inside_a_longer_one_is_not_the_same_number():
    rec = _rec(because="it is 10 degrees at night")
    assert voice.checked("It's 1 degree at night.", rec) is None


def test_the_rosemary_beetle_is_not_the_plant_in_the_third_person():
    rec = _rec("Salvia rosmarinus", "rosemary", because="the photo looks like rosemary beetle")
    assert voice.checked("I think the rosemary beetle has found me.", rec)


def test_the_model_line_is_used_when_it_passes():
    assert voice.line_for(MockAdapter([SAID]), _rec()) == SAID


def test_a_line_that_invents_is_asked_for_again():
    assert voice.line_for(MockAdapter(["Water me 3 litres on Friday.", SAID]), _rec()) == SAID


def test_lines_that_keep_failing_fall_back_to_the_answer_itself():
    bad = "Water me 3 litres on Friday."
    got = voice.line_for(MockAdapter([bad] * voice.TRIES + [SAID]), _rec())
    assert got == "Water me today. The soil is dry and no rain is due."


@pytest.mark.parametrize("line", ["My sweet basil is thirsty.", "Your basil needs a drink."])
def test_the_plant_never_talks_about_itself_as_someone_elses(line):
    assert voice.checked(line, _rec()) is None


def test_the_plant_speaks_as_itself_without_naming_itself():
    # naming itself was allowed until 16 Oct, when every line opened "I am Basil."
    assert voice.checked("My soil is dry, so I need a drink.", _rec())


def test_a_model_failure_falls_back_to_the_answer_itself():
    assert voice.line_for(_Raises([]), _rec()).startswith("Water me today.")


@pytest.mark.parametrize(
    ("name", "common", "persona"),
    [
        ("Ocimum basilicum", "basil", voice.BASIL),
        ("Salvia rosmarinus", "rosemary", voice.WISE),
        ("Petroselinum crispum", "parsley", voice.PARSLEY),
        ("Coriandrum sativum", "coriander", voice.CORIANDER),
        ("Mentha spicata", "spearmint", voice.HARDY),
        ("Allium schoenoprasum", "chives", voice.CHIVES),
        ("Ficus elastica", "rubber plant", voice.CALM),
    ],
)
def test_the_voice_follows_the_kind_of_plant(name, common, persona):
    assert voice.persona_for(_rec(name, common)) == persona


def test_the_sample_plants_each_sound_different():
    # 16 Oct: parsley, both basils and coriander all had one voice
    samples = [("Petroselinum crispum", "parsley"), ("Ocimum basilicum", "basil"),
               ("Salvia rosmarinus", "rosemary"), ("Coriandrum sativum", "coriander")]  # fmt: skip
    ids = [voice.persona_for(_rec(n, c)).voice_id for n, c in samples]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    "line", ["Give me a drink today, love.", "Give me a drink today, darling.",
             "Give me a drink today love.", "Love, give me a drink today.",
             "Give me a drink today, my dear."],
)  # fmt: skip
def test_no_pet_names(line):
    assert "no pet names" in voice.SYSTEM.replace("\n", " ")
    assert voice.checked(line, _rec()) is None


@pytest.mark.parametrize("line", ["I love the sun. Give me a drink today.",
                                  "Give me a drink today, dear plant lover that you are."])  # fmt: skip
def test_love_as_a_word_is_fine(line):
    assert voice.checked(line, _rec()) is not None


def test_no_plant_named_gets_the_calm_voice():
    rec = _rec()
    rec.observation = None
    assert voice.persona_for(rec) == voice.CALM


@respx.mock
def test_speak_sends_the_words_and_returns_the_audio():
    route = respx.post(voice.TTS_URL.format(voice="v1")).mock(
        return_value=httpx.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"})
    )
    assert voice.speak(SAID, "v1", api_key=KEY) == b"ID3mp3"
    sent = route.calls.last.request
    assert sent.headers["xi-api-key"] == KEY
    assert json.loads(sent.content) == {
        "text": SAID,
        "model_id": voice.TTS_MODEL,
        "voice_settings": {"speed": voice.TTS_SPEED},
    }


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"detail": "bad key"}),
        httpx.Response(200, json={"not": "audio"}),
        httpx.ConnectError("no route"),
    ],
)
def test_speak_failures_raise_voice_error(response):
    route = respx.post(voice.TTS_URL.format(voice="v1"))
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    with pytest.raises(voice.VoiceError):
        voice.speak(SAID, "v1", api_key=KEY)


def test_the_cache_keeps_a_voice_for_its_owner_and_its_answer_only():
    cache = voice.SpokenCache(max_entries=2)
    cache.put("a", voice.Spoken("Water it today", "u1", SAID, b"mp3"))
    assert cache.get("a", "Water it today", "u1").audio == b"mp3"
    assert cache.get("a", "Water it today", None) is None  # someone else
    assert cache.get("a", "Leave it", "u1") is None  # the answer changed after a refine
    cache.put("b", voice.Spoken("h", None, "t", b"1"))
    cache.put("c", voice.Spoken("h", None, "t", b"2"))
    assert cache.get("a", None, "u1") is None  # the oldest went first


def _client(tmp_path, advise, key=KEY):
    env = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    if key:
        env["HERBTWIN_ELEVENLABS_API_KEY"] = key
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)]),
        advise_adapter=MockAdapter(advise),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps, clock=lambda: OCT_4))


def _tts(status=200):
    return respx.post(url__startswith="https://api.elevenlabs.io/").mock(
        return_value=httpx.Response(
            status, content=b"ID3mp3", headers={"content-type": "audio/mpeg"}
        )
    )


@respx.mock
def test_no_key_means_no_button_and_no_route(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(ADV)] * 3, key=None)
    rid = _first(c)
    assert 'id="voice"' not in c.get(f"/answers/{rid}").text
    assert c.post(f"/api/answers/{rid}/voice").status_code == 404


@respx.mock
def test_the_plant_reads_its_answer_once_then_replays_free(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    tts = _tts()
    c = _client(tmp_path, [json.dumps(ADV)] * 3 + [SAID])  # the last reply is the line
    rid = _first(c)
    assert "Hear it from your basil" in c.get(f"/answers/{rid}").text
    r = c.post(f"/api/answers/{rid}/voice")
    assert r.status_code == 200 and r.json()["text"] == SAID
    audio = c.get(r.json()["audio"])
    assert audio.status_code == 200 and audio.content == b"ID3mp3"
    assert audio.headers["content-type"] == "audio/mpeg"
    again = c.post(f"/api/answers/{rid}/voice")  # the mock has no reply left: no model call
    assert again.json()["text"] == SAID and tts.call_count == 1
    assert tts.calls.last.request.url.path.endswith(voice.BASIL.voice_id)


@respx.mock
def test_a_voice_failure_still_returns_the_words_and_is_not_charged_twice(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    tts = _tts(status=500)
    c = _client(tmp_path, [json.dumps(ADV)] * 3 + [SAID])
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/voice")
    assert r.status_code == 503
    assert r.json() == {"detail": voice.UNAVAILABLE, "text": SAID}
    again = c.post(f"/api/answers/{rid}/voice")  # no model reply left: no second call
    assert again.status_code == 503 and again.json()["text"] == SAID
    assert tts.call_count == 1
    assert c.get(f"/api/answers/{rid}/voice.mp3").status_code == 404


@respx.mock
def test_one_persons_voice_is_not_served_to_another(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(ADV)] * 3)
    rid = _first(c)
    c.app.state.voices.put(rid, voice.Spoken("x", "someone-else", SAID, b"ID3mp3"))
    assert c.get(f"/api/answers/{rid}/voice.mp3").status_code == 404  # signed out here


@respx.mock
def test_another_site_cannot_ask_for_the_voice(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(ADV)] * 3)
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/voice", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_an_unknown_answer_has_no_voice(tmp_path):
    c = _client(tmp_path, [])
    assert c.post("/api/answers/nope/voice").status_code == 404
    assert c.get("/api/answers/nope/voice.mp3").status_code == 404


@pytest.mark.parametrize(
    "line", ["I am Basil. I need shelter.", "I'm sweet basil and I need shelter."]
)
def test_the_plant_never_introduces_itself(line):
    # 16 Oct: "I am rosemary. I have seen many winters." recited the character it was given
    assert voice.checked(line, _rec()) is None
    assert "Never introduce yourself" in voice.SYSTEM


def test_characters_are_adjectives_never_a_story_to_recite():
    for p in (voice.WISE, voice.BASIL, voice.PARSLEY, voice.CORIANDER, voice.HARDY, voice.CHIVES):
        assert " who " not in p.manner and "plant" not in p.manner, p.manner


@pytest.mark.parametrize(
    ("headline", "said"),
    [
        ("Protect it from the weather.", "Protect me from the weather."),
        ("Water it today", "Water me today."),
        ("Treat it.", "Treat me."),
        ("Cut it back.", "Cut me back."),
        # only a job on the plant: these keep the page's own words
        ("Leave it for now and keep an eye on it.", "Leave it for now and keep an eye on it."),
        ("Check first: is it rust?", "Check first: is it rust? "),
        ("Water when it's dry.", "Water when it's dry."),
    ],
)
def test_the_fallback_speaks_as_the_plant_only_where_it_is_safe(headline, said):
    rec = _rec()
    rec.answer.headline = headline
    assert voice.fallback_line(rec).startswith(said)


@pytest.mark.parametrize(
    "line",
    ["I've trimmed the brown stems at the centre.", "I have watered myself today.",
     "I'll water myself.", "I've just snipped a few leafy stems.",
     "I've also pruned my woody stems.",
     "I prune off the few dried brown stems at the centre.", "I'm trimming my tips.",
     "I just water myself when it's dry.", "I trimmed the brown stems.",
     "I always prune my tips.", "I'm gently trimming my tips.", "I'll gently trim myself."],
)  # fmt: skip
def test_the_plant_never_says_it_did_the_job_itself(line):
    # 17 Oct live, parsley: "I've trimmed the brown stems": the person does every job
    assert voice.checked(line, _rec()) is None


@pytest.mark.parametrize(
    "line",
    ["I'll need you to trim my brown stems.", "I have dry soil, so water me today.",
     "I have watery leaves, so water me less.", "I'll cover more ground in spring.",
     "I'll pick up once it's warmer.", "I've moved into autumn, so water me less.",
     "I've been covered in frost.", "I'll feed on the sun.",
     "I need you to prune my brown stems.", "I need water today.", "I'm watered enough.",
     "I cover the ground fast.", "I'm cut back to the base, so wait for new shoots."],
)  # fmt: skip
def test_asking_for_the_job_is_fine(line):
    # an answer that names the brown stems: the line may not claim a sign it does not give
    assert voice.checked(line, _rec(because="the soil is dry and some stems are brown"))


def _mildew_rec():
    # sample 6 live, 17 Oct: the answer to treat for downy mildew and not to water
    rec = _rec(because="the photo could show basil downy mildew")
    rec.answer.headline = "Treat it."
    rec.answer.do[0].if_you_do = voice.NO_DATA
    rec.answer.dont = SimpleNamespace(
        action="water", if_you_do="stays moist; extra water risks waterlogged roots"
    )
    return rec


@pytest.mark.parametrize(
    "line",
    ["I’m feeling a bit under the weather, so I’d appreciate a gentle mist of water only "
     "when the soil feels dry to the touch. Please keep me out of any standing moisture.",
     "Please keep me out of any standing moisture and give me a little extra light.",
     "Please give me a spot with good airflow.",
     "Give me a little extra air circulation to help me recover.",
     "Spray me with a fungicide."],
)  # fmt: skip
def test_a_line_that_adds_care_the_answer_never_gave_fails(line):
    # 17 Oct, Nemotron Nano on sample 6: 7 of 8 lines passed the old check while telling a
    # mildewed basil the answer said not to water to have "a gentle mist of water"
    assert voice.checked(line, _mildew_rec()) is None


def test_a_faithful_line_about_the_same_answer_passes():
    line = (
        "I think I may have basil downy mildew, so please treat me carefully. Avoid watering "
        "me now, because too much moisture can waterlog my roots."
    )
    assert voice.checked(line, _mildew_rec()) == line


def test_care_the_answer_does_give_may_be_said():
    rec = _rec(because="it needs more light than that corner gives")
    assert voice.checked("Move me into the light, please.", rec)


def test_an_empty_reply_is_not_asked_for_again():
    # a reasoning model that spends its whole token budget thinking sends "": asking again
    # (live, 17 Oct, local preview) cost two more calls and about 12 s for the same ""
    adapter = MockAdapter(["", SAID])
    assert voice.line_for(adapter, _rec()).startswith("Water me today.")
    assert len(adapter.calls) == 1


def test_a_failing_line_is_asked_for_once_more_at_most():
    bad = "Water me 3 litres on Friday."
    adapter = MockAdapter([bad, bad, SAID])
    assert voice.line_for(adapter, _rec()).startswith("Water me today.")
    assert len(adapter.calls) == 2


def test_the_log_says_which_check_a_line_failed(caplog):
    voice.line_for(MockAdapter(["Water me 3 litres on Friday."] * 2), _rec())
    assert "a number the answer does not hold" in caplog.text


def test_a_number_the_answer_holds_may_be_spelled_out():
    # 17 Oct: "No dry spell or frost in the next two weeks" was refused because the answer
    # said "2 weeks"
    rec = _rec(because="no dry days or frost in the next 2 weeks")
    assert voice.checked("No frost in the next two weeks, so hold off.", rec)
    assert voice.checked("No frost in the next three weeks, so hold off.", rec) is None


@pytest.mark.parametrize(
    "line",
    ["Keep fertilising me every week.", "I'd love some fertilized compost.",
     "Put me under grow lights.", "Keep me in the shades.", "Keep me well aired.",
     "Give me bright, indirect light."],
)  # fmt: skip
def test_every_form_of_added_care_fails(line):
    assert voice.checked(line, _mildew_rec()) is None


@pytest.mark.parametrize(
    "line", ["A light frost won't hurt me.", "Treat me, then give me a light trim later."]
)
def test_light_as_a_plain_word_is_not_care(line):
    assert voice.checked(line, _mildew_rec())


def _long_treat_rec():
    # live, 17 Oct rev 00030, sample 6: a multi-step treat answer; Nano recited all of it
    # (median 59 words over 10 lines, whether asked for under 50 or about 35) and failed
    rec = _mildew_rec()
    rec.answer.do[0].because = (
        "Remove and bin the leaves with grey-purple fuzz underneath, keep the plant apart from "
        "other basil, water only at the base in the morning, and improve airflow around the "
        "pot so the leaves dry quickly"
    )
    return rec


def test_the_plant_is_given_a_short_version_of_a_long_answer():
    said = voice._voice_text(_long_treat_rec())
    assert said.startswith("Treat it. Remove and bin the leaves with grey-purple fuzz underneath.")
    assert "Don't water it" in said
    assert "airflow" not in said  # the later steps stay on the page
    assert len(said.split()) <= 25


def test_the_short_version_goes_to_the_model_and_the_check_still_knows_the_rest():
    rec = _long_treat_rec()
    adapter = MockAdapter(["Please bin my fuzzy leaves and keep me away from other basil."])
    assert voice.line_for(adapter, rec).startswith("Please bin my fuzzy leaves")
    assert "airflow" not in adapter.calls[0]["prompt"]
    # a step left out of the prompt is still the answer's own, so saying it is not invented
    assert voice.checked("Give me better airflow, please.", rec)


@pytest.mark.parametrize(
    ("line", "spoken"),
    [
        ("I'm feeling a bit under the weather, love. Water me today.",
         "I'm feeling a bit under the weather. Water me today."),
        ("Water me today, my dear!", "Water me today!"),
        ("Water me today, darling, the soil is dry.", "Water me today, the soil is dry."),
    ],
)  # fmt: skip
def test_a_pet_name_is_taken_out_rather_than_asked_for_again(line, spoken):
    # 17 Oct: with the shorter block, 5 of 10 Nano lines added "love" or "dear"; taking the
    # word out adds nothing to what the answer says, so it costs no second call
    adapter = MockAdapter([line])
    assert voice.line_for(adapter, _rec()) == spoken
    assert len(adapter.calls) == 1


def test_a_pet_name_inside_the_line_is_still_refused():
    # "love" as a word of the line, not an address, is fine; one the cut cannot remove is not
    assert voice.checked("Love, water me today.", _rec()) is None


@pytest.mark.parametrize(
    ("because", "first"),
    [
        ("If the leaves are fuzzy, bin them, then keep it apart from other basil",
         "If the leaves are fuzzy, bin them."),
        ("Only when the top 2 cm are dry, water at the base; never wet the leaves",
         "Only when the top 2 cm are dry, water at the base."),
        ("Not yet: wait until the frost has passed, then cut back", "Not yet: wait until the frost has passed."),
        ("Cut back the woody stems by a third and then feed lightly unless growth is already "
         "soft and leggy", "Cut back the woody stems by a third and then feed lightly."),
    ],
)  # fmt: skip
def test_the_first_step_keeps_its_action(because, first):
    # review, 17 Oct: a condition alone ("If the leaves are fuzzy.") would tell the person
    # nothing to do; and a cut must not end on "unless"
    rec = _rec(because=because)
    assert voice._voice_text(rec).split(". ", 1)[1].startswith(first)


def _treated(because="the photo shows downy mildew on the leaves"):
    rec = _rec(because=because)
    rec.answer.headline = "Treat it."
    rec.answer.do[0].action, rec.answer.do[0].if_you_do = "treat_or_remove", "it stops spreading"
    return rec


@pytest.mark.parametrize(
    "line",
    [
        "I'm looking a bit wilted, so please treat me.",  # a sign the photo did not show
        "Treat me, and avoid watering until the soil feels dry.",  # care the answer lacks
        "My leaves are drooping, so treat me.",
    ],
)
def test_signs_and_watering_the_answer_does_not_give_fail_the_check(line):
    # 18 Oct judge walk: a basil answer with droop 0/3 that never mentioned watering was
    # voiced as "I'm looking a bit wilted" and "avoid watering until the soil feels dry"
    assert voice.checked(line, _treated()) is None
    assert voice.checked("Treat me, please: there's downy mildew on my leaves.", _treated())


def test_the_fallback_passes_the_same_check_or_says_only_the_headline():
    # the advisor's reason can say "your basil", which the plant must not say of itself
    rec = _treated(because="your basil has downy mildew on its leaves")
    assert voice.checked(voice.fallback_line(rec), rec) == "Treat me."
    bad = "I'm looking a bit wilted, so please treat me."
    assert voice.line_for(MockAdapter([bad] * voice.TRIES), rec) == "Treat me."


@pytest.mark.parametrize(
    "line", ["Please move me to a brighter spot today.", "A crisp night is coming, so move me."]
)
def test_honest_lines_near_the_sign_words_still_pass(line):
    rec = _rec(because="it needs more light before a cold night")
    rec.answer.headline, rec.answer.do[0].action = "Move it to better light.", "move_light"
    assert voice.checked(line, rec)


@pytest.mark.parametrize(
    "opening",
    [
        "I'm worried about you.",  # 18 Oct re-walk: the plant is the one in trouble
        "I am so concerned for you.",
        "I am worried about me.",  # 19 Oct: what the prompt fix for it produced
        "I'm worried about myself.",
    ],
)
def test_a_worry_pointed_at_someone_fails(opening):
    faithful = (
        "I think I may have basil downy mildew, so please treat me carefully. Avoid watering "
        "me now, because too much moisture can waterlog my roots."
    )
    assert voice.checked(f"{opening} {faithful}", _mildew_rec()) is None
    unwell = f"I'm not well. {faithful}"
    assert voice.checked(unwell, _mildew_rec()) == unwell
    assert "worry" not in voice.SYSTEM  # the prompt line that produced "worried about me"


def _no_cure_rec(problem=True):
    from herbtwin.answer import NO_CURE_BECAUSE, NO_CURE_HEADLINE
    from herbtwin.schemas import ProblemSeen

    rec = _rec(because=NO_CURE_BECAUSE)
    rec.answer.headline = NO_CURE_HEADLINE
    rec.answer.do[0].action = "treat_or_remove"
    rec.answer.do[0].if_you_do = (
        "There is no known cure: harvest unaffected leaves to use at once, then pull out, bag "
        "and bin infected plants."
    )
    rec.problem = (
        ProblemSeen(name="basil downy mildew", looks_like="x", source="https://x")
        if problem
        else None
    )
    return rec


def test_a_plant_with_no_cure_says_so_in_its_own_voice_without_a_model_call():
    # 19 Oct final look: "I am worried about me." then "Remove it. There is no cure for
    # this.", the plant telling you to bin it in the answer's third person
    rec, m = _no_cure_rec(), MockAdapter([])
    said = (
        "I'm not well: I think it's basil downy mildew. There's no cure, so pick my good "
        "leaves and pull me out."
    )
    assert voice.line_for(m, rec) == said and m.calls == []
    assert voice.fallback_line(rec) == said
    assert voice.rejection(said, rec) is None  # the same check every line passes
    plain = "I'm not well. There's no cure, so pick my good leaves and pull me out."
    assert voice.line_for(m, _no_cure_rec(problem=False)) == plain


def test_leave_it_but_protect_it_is_said_whole_in_the_plants_voice():
    # never a bare "leave me": the protect half is the point (19 Oct)
    rec = _rec(because="a cold night is coming")
    rec.answer.headline = "Leave it, but protect it before the cold night on Saturday."
    line = voice.fallback_line(rec)
    assert line.startswith("Leave me be, but protect me before the cold night on Saturday.")
    assert voice.rejection(line, rec) is None


def test_the_plant_never_speaks_a_web_pages_quote_as_its_own():
    rec = _rec()
    rec.answer.do[0].if_you_do = "Remove leaves with grey mould at once."
    rec.answer.do[0].if_you_do_from = "web_search"
    assert "grey mould" not in voice._answer_text(rec)
    rec.answer.do[0].if_you_do_from = "outcome_table"
    assert "grey mould" in voice._answer_text(rec)
