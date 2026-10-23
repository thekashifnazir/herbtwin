"""The quick questions on the wait page (21 Oct, Kash: "use the wait"): a reply before the
advice goes into this answer; one after it is checked again on "See your answer"."""

import json
import re

import httpx
import pytest
import respx

from herbtwin.schemas import Told
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import waiting
from herbtwin.web.progress import ASKED_LATER, ASKED_NOW, DROP_ASKS, asks_card
from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

WID = "a" * 32


def test_a_reply_counts_now_until_the_advice_starts_then_later():
    w = waiting.Waits()
    w.start(WID, None, Told(question="why yellow?"))
    assert w.reply(WID, None, Told(soil_feel="dry")) == "now"
    took = w.take(WID, Told(question="why yellow?"))
    assert took == Told(question="why yellow?", soil_feel="dry")
    assert w.reply(WID, None, Told(last_watered="today")) == "later"
    w.finish(WID, "/answers/" + "b" * 32)
    target, told = w.late(WID, None)
    assert target == "/answers/" + "b" * 32
    assert told == Told(question="why yellow?", soil_feel="dry", last_watered="today")
    assert w.late(WID, None) == ("/answers/" + "b" * 32, None)  # refined once, never twice


def test_nothing_late_means_no_refine_and_a_reply_after_the_read_counts_later():
    w = waiting.Waits()
    w.start(WID, None, None)
    w.reply(WID, None, Told(soil_feel="wet"))
    w.take(WID, None)
    w.finish(WID, "/answers/x")
    assert w.late(WID, None) == ("/answers/x", None)
    w2 = waiting.Waits()
    w2.start(WID, None, None)
    w2.finish(WID, "/answers/x")  # a replayed answer: no advice ran at all
    assert w2.reply(WID, None, Told(soil_feel="wet")) == "later"


def test_a_wait_is_its_owners_and_does_not_last():
    now = [0.0]
    w = waiting.Waits(ttl_s=60, max_entries=2, clock=lambda: now[0])
    w.start(WID, "user-1", None)
    assert w.reply(WID, None, Told(soil_feel="dry")) == "gone"  # not signed in as them
    assert w.reply(WID, "user-1", Told(soil_feel="dry")) == "now"
    now[0] = 61
    assert w.reply(WID, "user-1", Told(soil_feel="dry")) == "gone"
    w.start("1" * 32, None, None)
    w.start("2" * 32, None, None)
    w.start("3" * 32, None, None)  # bounded: the oldest goes first
    assert w.reply("1" * 32, None, Told(soil_feel="dry")) == "gone"


def test_the_card_is_script_only_and_sends_each_tap():
    card = asks_card(WID)
    assert (
        f'<form class="tray wait-asks" id="wait-asks" method="post" action="/waits/{WID}/told" hidden>'
        in card
    )
    assert "Push a finger 2 cm into the soil. How does it feel?" in card
    assert '<input type="radio" name="soil_feel" value="dry"> Dry</label>' in card
    assert '<input type="radio" name="last_watered" value="1_2_days"> 1–2 days ago</label>' in card
    assert '<p class="sent" role="status"></p>' in card  # each reply is said once
    script = card.split("<script>", 1)[1]
    assert "f.hidden=false" in script and "f.addEventListener('change'" in script
    assert f'window.herbtwinSee="/waits/{WID}/see"' in script
    assert json.dumps(ASKED_NOW) in script and json.dumps(ASKED_LATER) in script


def test_the_questions_go_when_the_read_stops_at_the_photo_or_fails():
    from tests.test_web_progress import _collect

    stopped = "".join(_collect(lambda say: (say("This doesn't look like a plant"), "/a")[1]))
    assert DROP_ASKS in stopped

    def broken(say):
        raise RuntimeError("boom")

    assert DROP_ASKS in "".join(_collect(broken))


def _with_reply(c, told, times=99):
    """A reply that lands while the photo is read: added the moment the wait starts (for
    the first `times` uploads)."""
    waits = c.app.state.waits
    start, left = waits.start, [times]

    def started(wait_id, owner, base):
        start(wait_id, owner, base)
        c.wait_id = wait_id
        if left[0] > 0:
            left[0] -= 1
            waits.reply(wait_id, owner, told)

    waits.start = started


@pytest.mark.usefixtures("open_meteo_down")
def test_a_reply_during_the_photo_read_goes_into_this_answer(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _with_reply(c, Told(soil_feel="dry"))
    page = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert f'action="/waits/{c.wait_id}/told"' in page
    assert "<li>Using what you told us</li>" in page
    answer = re.search(r'<a id="next" href="([^"]+)"', page)[1]
    entry = c.app.state.answers.get_for(answer.rsplit("/", 1)[1], None)
    assert entry.latest.told == Told(soil_feel="dry")


@pytest.mark.usefixtures("open_meteo_down")
def test_a_reply_after_the_advice_is_checked_again_on_see_your_answer(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    _with_reply(c, Told(soil_feel="dry"))
    page = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    answer = re.search(r'<a id="next" href="([^"]+)"', page)[1]
    later = c.post(f"/waits/{c.wait_id}/told", data={"last_watered": "today"})
    assert later.json() == {"counted": "later"}
    seen = c.post(f"/waits/{c.wait_id}/see")
    assert seen.json() == {"go": answer}
    entry = c.app.state.answers.get_for(answer.rsplit("/", 1)[1], None)
    assert entry.latest.told == Told(soil_feel="dry", last_watered="today")
    assert entry.latest.refined_from is not None  # the answer says it was checked again
    assert c.post(f"/waits/{c.wait_id}/see").json() == {"go": answer}  # once only


@pytest.mark.usefixtures("open_meteo_down")
def test_a_reply_from_another_site_or_to_no_wait_is_refused(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _with_reply(c, Told(soil_feel="dry"))
    c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    other = {"origin": "https://evil.example"}
    r = c.post(f"/waits/{c.wait_id}/told", data={"soil_feel": "wet"}, headers=other)
    assert r.status_code == 404
    assert c.post("/waits/not-an-id/told", data={"soil_feel": "wet"}).status_code == 404
    assert c.post(f"/waits/{'c' * 32}/see").status_code == 404
    bad = c.post(f"/waits/{c.wait_id}/told", data={"soil_feel": "soggy"})
    assert bad.status_code == 400


def test_a_reply_after_a_photo_asks_which_plant_is_asked_again_under_the_answer():
    w = waiting.Waits()
    w.start(WID, None, None)
    w.reply(WID, None, Told(soil_feel="dry"))
    assert w.take(WID, None, answering=False) == Told(soil_feel="dry")  # kept with the tap
    assert w.reply(WID, None, Told(last_watered="today")) == "below"
    w.finish(WID, "/taps/" + "b" * 32)
    assert w.late(WID, None) == ("/taps/" + "b" * 32, None)


@respx.mock
def test_a_photo_of_several_plants_keeps_the_replies_so_far_for_its_tap(tmp_path):
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED)], [])
    _with_reply(c, Told(soil_feel="dry"))
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    assert c.app.state.taps.get(tap).told == Told(soil_feel="dry")
    later = c.post(f"/waits/{c.wait_id}/told", data={"last_watered": "today"}).json()
    assert later == {"counted": "below"}


@respx.mock
def test_signed_in_a_reply_during_the_read_goes_into_the_stored_answer(tmp_path):
    from tests.test_web_history import SAGE, _signed_in

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 6)
    _with_reply(c, Told(soil_feel="wet"))
    page = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}).text
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    assert hist.for_user("u1").get_answer(answer).told == Told(soil_feel="wet")
    assert c.post(f"/waits/{c.wait_id}/told", data={"last_watered": "today"}).json() == {
        "counted": "later"
    }
    assert c.post(f"/waits/{c.wait_id}/see").json() == {"go": f"/answers/{answer}"}
    told = c.app.state.answers.get_for(answer, "u1").latest.told
    assert told == Told(soil_feel="wet", last_watered="today")


@pytest.mark.usefixtures("open_meteo_down")
def test_an_answer_made_with_replies_is_never_replayed_to_the_same_photo_alone(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)] * 2, [json.dumps(ADV)] * 6)
    _with_reply(c, Told(soil_feel="dry"), times=1)
    files = {"photo": ("b.jpg", JPEG, "image/jpeg")}
    c.post("/analyse", files=files)
    again = c.post("/analyse", files=files).text
    assert "Same photo as earlier today" not in again and "Using what you told us" not in again


def test_see_your_answer_sends_a_waiting_reply_first_and_never_waits_for_ever():
    from herbtwin.web.progress import SEE_WAIT_S, _done

    card = asks_card(WID).split("<script>", 1)[1]
    # the reply is marked as sent before it is, so a quick tap on the button still checks
    # a typed place waits for its button (22 Oct phone walk): its letters are not replies
    change = card.split("f.addEventListener('change',e=>{if(e.target===pi)return;", 1)[1]
    assert change.startswith(f'window.herbtwinSee="/waits/{WID}/see";')
    assert "t=setTimeout(send,400)" in change  # arrow keys send only where they stop
    assert "window.herbtwinFlush=()=>t?(clearTimeout(t),send()):last" in card
    click = _done("/answers/abc").split("n.addEventListener('click',e=>{", 1)[1]
    assert "Promise.resolve(window.herbtwinFlush&&window.herbtwinFlush())" in click
    assert f"setTimeout(go,{SEE_WAIT_S}e3)" in click and "if(!gone){gone=1;" in click
    assert "if(w)w.textContent=" in click  # the status line says it is checking


def test_each_reply_line_is_announced_even_the_first_and_a_repeat():
    # #335 review: an empty live region with display:none may not be announced by VoiceOver
    from herbtwin.web.style import CSS

    assert ".wait-asks .sent:empty { display: none; }" not in CSS
    assert ".wait-asks .sent:empty { margin: 0; }" in CSS
    card = asks_card(WID).split("<script>", 1)[1]
    assert "const say=m=>{p.textContent='';setTimeout(()=>{p.textContent=m},60)}" in card
    assert "p.textContent=said" not in card  # every line goes through say()


def test_soil_has_not_sure_too_and_it_clears_an_earlier_soil_reply():
    # 21 Oct, Kash's live look: "Not sure" was only on the watering question
    card = asks_card(WID)
    assert '<input type="radio" name="soil_feel" value="not_sure"> Not sure</label>' in card
    w = waiting.Waits()
    w.start(WID, None, None)
    w.reply(WID, None, Told(soil_feel="dry", last_watered="today"))
    w.reply(WID, None, Told(), frozenset({"soil_feel"}))
    assert w.take(WID, None) == Told(last_watered="today")


@pytest.mark.usefixtures("open_meteo_down")
def test_not_sure_on_the_soil_is_accepted_and_sends_no_soil(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _with_reply(c, Told(soil_feel="dry"))
    c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    r = c.post(f"/waits/{c.wait_id}/told", data={"soil_feel": "not_sure"})
    # the answer already used "dry" and nothing is left to check again with: said so
    assert r.status_code == 200 and r.json() == {"counted": "kept"}
    assert c.app.state.waits._items[c.wait_id].replies is None  # no soil reading kept
    assert c.post(f"/waits/{c.wait_id}/see").json()["go"].startswith("/answers/")
    for junk in ({"soil_feel": "maybe"}, {"soil_feel": "not_sure", "last_watered": "junk"}):
        assert c.post(f"/waits/{c.wait_id}/told", data=junk).status_code == 400


def test_a_reply_says_which_question_it_answered_and_a_tap_does_nothing_else():
    # Kash: "seemed to run from that after I just clicked not sure only": a tap sends a
    # reply and says which one, never submits, jumps or reveals the answer
    card = asks_card(WID)
    assert "Thanks: we'll use your answer about {what}." in card
    assert '{"soil_feel": "the soil", "last_watered": "watering", "place": "where it is"}' in card
    # the questions actually sent, both when both were tapped; "not sure" on either says so
    assert "u=n.filter(q=>d.get(q)==='not_sure'),k=n.filter(q=>d.get(q)!=='not_sure')" in card
    assert "w=k.map(q=>whats[q]).join(' and ')" in card
    assert "Fine: we'll go without {none}." in card and '"soil_feel": "a soil reading"' in card
    script = card.split("<script>", 1)[1]
    # never leaves the page; the place's button or Enter sends it (22 Oct phone walk)
    assert "f.addEventListener('submit',e=>{e.preventDefault();" in script
    assert "location" not in script and "#next" not in script and ".click(" not in script


def test_not_sure_on_the_soil_before_the_advice_just_clears_it():
    w = waiting.Waits()
    w.start(WID, None, Told(question="why?"))
    w.reply(WID, None, Told(soil_feel="dry"))
    assert w.reply(WID, None, Told(), frozenset({"soil_feel"})) == "now"
    assert w.take(WID, Told(question="why?")) == Told(question="why?")
    # after the advice, with the upload's own question still there, it is checked again
    w2 = waiting.Waits()
    w2.start(WID, None, Told(question="why?"))
    w2.reply(WID, None, Told(soil_feel="dry"))
    w2.take(WID, Told(question="why?"))
    assert w2.reply(WID, None, Told(), frozenset({"soil_feel"})) == "later"
    w2.finish(WID, "/answers/x")
    assert w2.late(WID, None) == ("/answers/x", Told(question="why?"))


def test_not_sure_after_the_advice_says_kept_only_when_the_answer_used_a_soil_reply():
    # #358 review: a soil reply that came after the advice started was never used
    w = waiting.Waits()
    w.start(WID, None, None)
    w.take(WID, None)  # the advice starts with no replies
    w.reply(WID, None, Told(soil_feel="dry"))  # too late for it
    assert w.reply(WID, None, Told(), frozenset({"soil_feel"})) == "later"  # "no soil reading"
    w.finish(WID, "/answers/x")
    assert w.late(WID, None) == ("/answers/x", None)  # nothing to check again


def test_the_questions_say_the_read_has_started_and_a_reply_still_counts():
    # 21 Oct, Kash on rev 00050: the steps moved before the second question, and it read as
    # if the answer had started without them. Nothing waits on them, and the page says so
    card = asks_card(WID)
    # 22 Oct site walk: said in one short line, so the questions start higher on a phone
    assert '<p class="muted">Optional. Your answers make the advice closer.</p>' in card
    assert "They make the advice surer" not in card and "We've started" not in card


@pytest.mark.usefixtures("open_meteo_down")
def test_not_sure_on_watering_is_said_plainly_and_sends_no_watering(tmp_path):
    # 21 Oct, Kash: "Not sure" on watering said "Thanks: we'll use your answer about
    # watering", and sent "last watered: not sure" on to the advice
    card = asks_card(WID)
    assert '"last_watered": "when you last watered"' in card  # "Fine: we'll go without ..."
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _with_reply(c, Told(last_watered="today"), times=0)
    c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    waits = c.app.state.waits
    waits._items[c.wait_id].replies = Told(last_watered="today", soil_feel="dry")
    r = c.post(f"/waits/{c.wait_id}/told", data={"last_watered": "not_sure"})
    assert r.status_code == 200 and r.json()["counted"] in {"later", "kept"}
    assert waits._items[c.wait_id].replies == Told(soil_feel="dry")  # watering cleared
    both = c.post(
        f"/waits/{c.wait_id}/told", data={"soil_feel": "not_sure", "last_watered": "not_sure"}
    )
    assert both.status_code == 200
    assert waits._items[c.wait_id].replies is None  # nothing sent on to the advice


def test_not_sure_on_watering_says_kept_only_when_the_answer_used_a_watering_reply():
    w = waiting.Waits()
    w.start(WID, None, None)
    w.reply(WID, None, Told(last_watered="today"))
    w.take(WID, None)  # the advice used "today"
    assert w.reply(WID, None, Told(), frozenset({"last_watered"})) == "kept"
    w2 = waiting.Waits()
    w2.start(WID, None, None)
    w2.take(WID, None)  # the advice starts with no replies
    assert w2.reply(WID, None, Told(), frozenset({"last_watered"})) == "later"
    w2.finish(WID, "/answers/x")
    assert w2.late(WID, None) == ("/answers/x", None)  # nothing to check again


def test_the_answer_pills_take_two_columns_and_short_words_on_a_phone():
    # 22 Oct site walk: the 10 pills wrapped one per row on a phone (the card ~1.6 screens).
    # Two columns, and shorter words for watering; the values sent are the same
    from herbtwin.schemas import LAST_WATERED_TEXT
    from herbtwin.web.style import CSS

    card = asks_card(WID)
    watered = re.findall(r'name="last_watered" value="([^"]+)"> ([^<]+)</label>', card)
    assert [v for v, _ in watered] == list(LAST_WATERED_TEXT)
    assert [w for _, w in watered] == [
        "Today", "1–2 days ago", "3–7 days ago", "Over a week ago", "Not sure",
    ]  # fmt: skip
    assert max(len(w) for _, w in watered) <= 15
    assert (
        "@media (max-width: 720px) { .wait-asks .choices { display: grid;"
        " grid-template-columns: 1fr 1fr;" in CSS
    )


# 22 Oct phone walk (Kash: "I thought we normally got more info"): no place was given, so
# the answer had no weather, no twin and no Compare. The wait asks where it is

LEEDS = {"results": [{"name": "Leeds", "country_code": "GB", "latitude": 53.8, "longitude": -1.55}]}


def test_the_place_question_shows_when_the_upload_gave_no_place():
    from herbtwin.web.progress import PLACE_ASK

    asked, not_asked = asks_card(WID, ask_place=True), asks_card(WID)
    assert '<fieldset class="wait-place" id="wait-place">' in asked
    assert f'<legend id="wait-place-l">{PLACE_ASK}</legend>' in asked
    assert 'aria-labelledby="wait-place-l"' in asked
    assert PLACE_ASK == "Where is it? (UK town or postcode)"
    assert '<h2 id="wait-asks-h">While you wait: three quick questions</h2>' in asked
    # a place came with it: the question waits, hidden, in case the read finds none
    assert '<fieldset class="wait-place" id="wait-place" hidden>' in not_asked
    assert '<h2 id="wait-asks-h">While you wait: two quick questions</h2>' in not_asked
    # it comes before the soil and the watering: the weather and the twin hang on it
    assert asked.index('name="place"') < asked.index('name="soil_feel"')


def test_a_read_that_finds_no_place_asks_where_it_is_and_one_that_has_one_drops_it():
    from herbtwin.pipeline import WeatherMissed
    from herbtwin.web.progress import ASK_PLACE, PLACE_KNOWN, _step

    for why, asks in (
        ("no_location", True),
        ("place_not_found", True),
        ("fetch_failed", False),
        ("photo_too_old", False),
    ):
        assert (ASK_PLACE in _step(WeatherMissed(why))) is asks, why
    assert PLACE_KNOWN in _step("Checking the weather where you are")
    card = asks_card(WID)
    assert "window.herbtwinAskPlace=()=>{if(!pl||f.hidden)return;pl.hidden=false;" in card
    # an unanswered place question goes once the weather is on its way; a typed one stays
    assert "window.herbtwinPlaceKnown=()=>{if(!pl||pi.value.trim())return;pl.hidden=true;" in card
    # an empty box is never sent as a place
    assert "if(!String(d.get('place')||'').trim())d.delete('place')" in card


def _placeless(tmp_path):
    from tests.test_web import _placeless_client

    tmp_path.mkdir(exist_ok=True)
    return _placeless_client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)


@respx.mock
def test_a_place_typed_while_the_photo_is_read_gets_the_weather_and_the_twin(tmp_path):
    from herbtwin.where import GEOCODE_URL

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LEEDS))
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    # the control: no place, so no weather and no twin
    bare = _placeless(tmp_path / "bare")
    page = bare.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert '<fieldset class="wait-place" id="wait-place">' in page  # asked from the start
    assert "No place given: skipping the weather" in page and "Tried " not in page
    # the same photo, with "Leeds" typed before the advisors start
    c = _placeless(tmp_path / "told")
    _with_reply(c, Told(place="Leeds"))
    page = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert "<li>Using what you told us</li>" in page
    assert "<li>Checking the weather where you are</li>" in page
    assert 'id="fact-weather"' in page and '<li class="twin">Tried ' in page
    answer = re.search(r'<a id="next" href="([^"]+)"', page)[1]
    rec = c.app.state.answers.get_for(answer.rsplit("/", 1)[1], None).latest
    assert rec.location is not None and round(rec.location.lat, 1) == 53.8
    assert rec.environment is not None and rec.state is not None and rec.told.place == "Leeds"


@respx.mock
def test_a_place_typed_while_waiting_that_cant_be_found_says_so_and_the_answer_still_comes(
    tmp_path,
):
    from herbtwin.where import GEOCODE_URL, PLACE_NOT_FOUND_HINT

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    c = _placeless(tmp_path)
    _with_reply(c, Told(place="Nowhereville"))
    page = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert "Couldn&#x27;t find that place: skipping the weather" in page
    answer = re.search(r'<a id="next" href="([^"]+)"', page)[1]
    rec = c.app.state.answers.get_for(answer.rsplit("/", 1)[1], None).latest
    # review: the answer never claims a place it didn't use, and says it wasn't found
    assert rec.location is None and (rec.told is None or rec.told.place is None)
    assert any(n.endswith(PLACE_NOT_FOUND_HINT) for n in rec.notes)


def test_the_wait_takes_a_place_reply(tmp_path):
    c = _client(tmp_path, [], [])
    c.app.state.waits.start(WID, None, None)
    r = c.post(f"/waits/{WID}/told", data={"place": " LS1 4AP "})
    assert r.json() == {"counted": "now"}
    assert c.app.state.waits.take(WID, None) == Told(place="LS1 4AP")
    assert c.post(f"/waits/{WID}/told", data={"place": "x" * 81}).status_code == 400


def test_a_card_said_again_takes_the_old_ones_place_and_an_empty_place_sends_nothing():
    # review: a place typed on the wait when the photo had one says its weather again; the
    # side column keeps one weather card, not two with the same id
    from herbtwin.web.progress import NOW_JS

    assert "a.querySelectorAll('.'+id).forEach(o=>o.remove());a.append(" in NOW_JS
    card = asks_card(WID, ask_place=True)
    assert "if(pi&&!pi.value.trim()&&!f.querySelector('input:checked'))return;" in card


# 23 Oct, Kash's phone walk of rev 00089: a photo of several plants, no place. London, the
# finger test and watering were answered on the wait page after the read had ended; the
# wait said "tell us again under your answer", and the tapped plant's answer had no weather.
# Kash: "It should redo and add location to our information if we have done that."

LONDON = {
    "results": [{"name": "London", "country_code": "GB", "latitude": 51.5, "longitude": -0.12}]
}


@pytest.mark.parametrize("whole", [True, False])
@respx.mock
def test_what_was_told_on_the_wait_reaches_the_answer_for_the_plant_tapped(tmp_path, whole):
    from herbtwin.web.progress import ASKED_BELOW
    from herbtwin.where import GEOCODE_URL
    from tests.test_web import _placeless_client
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LONDON))
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    reads = [json.dumps(MIXED)] + ([] if whole else [json.dumps(OBS)])  # a crop is read again
    c = _placeless_client(tmp_path, reads, [json.dumps(ADV)] * 3)
    _with_reply(c, Told(soil_feel="dry"))  # one reply while the photo was read
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    assert "No place given: skipping the weather" in page
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    # the rest after the read had ended: each is kept for the tap, and the line says so
    told = f"/waits/{c.wait_id}/told"
    assert c.post(told, data={"place": "London"}).json() == {"counted": "below"}
    assert c.post(told, data={"last_watered": "today"}).json() == {"counted": "below"}
    assert ASKED_BELOW == "Thanks: we'll use it for the plant you tap."
    form = {"whole": "1"} if whole else {"fx": "0.25", "fy": "0.5"}
    page = c.post(f"/taps/{tap}", data=form).text
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    rec = c.app.state.answers.get_for(answer, None).latest
    # a crop's read looks the place up as an upload's typed place: in its location, not
    # in what they told us (#504 review: one it can't find is never claimed)
    place = {"place": "London"} if whole else {}
    assert rec.told == Told(soil_feel="dry", last_watered="today", **place)
    assert rec.location is not None and round(rec.location.lat, 1) == 51.5  # its weather too
    assert rec.environment is not None and rec.state is not None
    assert "No place given" not in page


@respx.mock
def test_signed_in_what_was_told_on_the_wait_reaches_the_tapped_plants_answer(tmp_path):
    from herbtwin.where import GEOCODE_URL
    from tests.test_web_history import _signed_in
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LONDON))
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED)], [json.dumps(ADV)] * 3)
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    wait_id = re.search(r'action="/waits/([0-9a-f]+)/told"', page.text)[1]
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page.text)[1]
    c.post(f"/waits/{wait_id}/told", data={"soil_feel": "wet", "place": "London"})
    page = c.post(f"/taps/{tap}", data={"whole": "1"}).text
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    stored = hist.for_user("u1").get_answer(answer)
    assert stored.told == Told(soil_feel="wet", place="London")


@respx.mock
def test_a_wait_place_the_tap_cannot_find_says_so_and_is_not_claimed(tmp_path):
    from herbtwin.where import GEOCODE_URL, PLACE_NOT_FOUND_HINT
    from tests.test_web import _placeless_client
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    c = _placeless_client(tmp_path, [json.dumps(MIXED)], [json.dumps(ADV)] * 3)
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    wait_id = re.search(r'action="/waits/([0-9a-f]+)/told"', page)[1]
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    c.post(f"/waits/{wait_id}/told", data={"place": "Nowhereville", "soil_feel": "dry"})
    page = c.post(f"/taps/{tap}", data={"whole": "1"}).text
    assert "Couldn&#x27;t find that place: skipping the weather" in page
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    rec = c.app.state.answers.get_for(answer, None).latest
    assert rec.told == Told(soil_feel="dry") and rec.location is None
    assert any(n.endswith(PLACE_NOT_FOUND_HINT) for n in rec.notes)


def test_a_reply_after_the_plant_was_tapped_is_never_said_to_count():
    # #504 review: the tap's answer takes the replies when the tap starts; one after that
    # was told "we'll use it for the plant you tap", then dropped
    from herbtwin.web.progress import ASKED_TAPPED

    w = waiting.Waits()
    w.start(WID, None, None)
    w.reply(WID, None, Told(soil_feel="dry"))
    w.take(WID, None, answering=False)
    assert w.reply(WID, None, Told(last_watered="today")) == "below"  # before the tap: used
    assert w.for_tap(WID) == (True, Told(soil_feel="dry", last_watered="today"))
    assert w.reply(WID, None, Told(soil_feel="wet")) == "tapped"
    assert ASKED_TAPPED == "That came after you picked your plant: tell us again under its answer."
    # a "not sure" on a question the answer already took: still "tapped", never "kept",
    # which would say the answer used it (#508 review)
    assert w.reply(WID, None, Told(), frozenset({"soil_feel"})) == "tapped"
    # the server words it, and the page says what the server sent, whatever the reply
    assert "say(j.said?j.said:" in asks_card(WID)
    # a refused tap may come again: a reply meanwhile goes into it, and is said to
    w.untap(WID)
    assert w.reply(WID, None, Told(last_watered="1_2_days")) == "below"


@respx.mock
def test_a_wait_place_a_tapped_crop_cannot_find_is_said_and_not_claimed(tmp_path):
    from herbtwin.where import GEOCODE_URL, PLACE_NOT_FOUND_HINT
    from tests.test_web import _placeless_client
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    reads = [json.dumps(MIXED), json.dumps(OBS)]  # the crop is read again
    c = _placeless_client(tmp_path, reads, [json.dumps(ADV)] * 3)
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    wait_id = re.search(r'action="/waits/([0-9a-f]+)/told"', page)[1]
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    c.post(f"/waits/{wait_id}/told", data={"place": "Nowhereville", "soil_feel": "dry"})
    page = c.post(f"/taps/{tap}", data={"fx": "0.25", "fy": "0.5"}).text
    assert "Couldn&#x27;t find that place: skipping the weather" in page
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    rec = c.app.state.answers.get_for(answer, None).latest
    assert rec.told == Told(soil_feel="dry") and rec.location is None
    assert any(n.endswith(PLACE_NOT_FOUND_HINT) for n in rec.notes)


@respx.mock
def test_after_a_real_tap_a_late_reply_hears_it_came_after(tmp_path):
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED)], [json.dumps(ADV)] * 3)
    _with_reply(c, Told(soil_feel="dry"))  # sent while the photo was read: the read took it
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    wait_id = re.search(r'action="/waits/([0-9a-f]+)/told"', page)[1]
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    c.post(f"/taps/{tap}", data={"whole": "1"})
    said = "That came after you picked your plant: tell us again under its answer."
    late = c.post(f"/waits/{wait_id}/told", data={"soil_feel": "wet"}).json()
    assert late == {"counted": "tapped", "said": said}
    # "not sure" on the soil the answer took: the same line, never "already used" (#508)
    unsure = c.post(f"/waits/{wait_id}/told", data={"soil_feel": "not_sure"}).json()
    assert unsure == {"counted": "tapped", "said": said}


@respx.mock
def test_a_refused_crop_lets_a_reply_meanwhile_into_the_retry(tmp_path, monkeypatch):
    # review of #508: a crop that can't be cut puts the tap back; a reply before the retry
    # is said to count, and the retried tap's answer has it
    from herbtwin.web import tapping
    from tests.test_web_tap import MIXED, PHOTO

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}).text
    wait_id = re.search(r'action="/waits/([0-9a-f]+)/told"', page)[1]
    tap = re.search(r'<a id="next" href="/taps/([0-9a-f]+)"', page)[1]
    real, calls = tapping.crop_at, []

    def once_refused(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("too small")
        return real(*a, **k)

    monkeypatch.setattr(tapping, "crop_at", once_refused)
    box = {"fx": "0.25", "fy": "0.5"}
    assert c.post(f"/taps/{tap}", data=box).status_code == 400  # refused: tap again
    meanwhile = c.post(f"/waits/{wait_id}/told", data={"last_watered": "today"}).json()
    assert meanwhile == {"counted": "below"}
    page = c.post(f"/taps/{tap}", data=box).text
    answer = re.search(r'<a id="next" href="/answers/([0-9a-f]+)"', page)[1]
    assert c.app.state.answers.get_for(answer, None).latest.told == Told(last_watered="today")
