"""22 Oct site walk: after "Check the advice again" or the Indoors switch (both POST
/answers/<id>/refine) the address bar kept the POST URL. A reload asked to send the form
again, a second paid run, and a copied link failed. The refined page now takes its answer's
own address, and that address shows the refined answer."""

import json

import httpx
import respx

from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_web import ADV, HOLD, OBS, SAMPLE, _client, _first
from tests.test_web_history import SAGE, _signed_in, _upload

# the hook: the page's own address, never the POST one, with no re-post on reload
HOOK = (
    "<script>try{const p=location.pathname,"
    'u=p.replace(/^(\\/answers\\/[^/]+)\\/refine$/,"$1");'
    'if(u!==p)history.replaceState(null,"",u)}catch(e){}</script>'
)


@respx.mock
def test_the_refined_page_takes_the_answer_address(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    assert r.status_code == 200
    head = r.text.split("</head>", 1)[0]
    assert HOOK in head  # in the head: the address changes before the page draws


@respx.mock
def test_the_answer_address_shows_the_refined_answer_and_costs_nothing(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    rid = _first(c)
    c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    calls = len(c.app.state.deps.advise_adapter.calls)
    again = c.get(f"/answers/{rid}")  # the reload, or the copied link
    assert again.status_code == 200
    assert '<p class="checked">Changed after what you told us. Was: <s>Water it.</s></p>' in (
        again.text
    )
    assert "Hold off watering." in again.text
    assert 'value="wet" checked' in again.text  # what was told rides along
    assert len(c.app.state.deps.advise_adapter.calls) == calls  # nothing re-ran
    # the hook does nothing there: the address is already the answer's own
    assert HOOK in again.text


@respx.mock
def test_the_switch_lands_on_the_answer_address_indoors(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "outdoor"})], [json.dumps(ADV)] * 6)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"setting": "indoor"})
    assert HOOK in r.text
    again = c.get(f"/answers/{rid}")
    assert '<span class="chip setting">Indoors (you said)</span>' in again.text


@respx.mock
def test_signed_in_the_answer_address_shows_the_refined_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    stored = store.answers_for(store.list_plants()[0].id)[0]
    r = c.post(f"/answers/{stored.id}/refine", data={"soil_feel": "wet"})
    assert HOOK in r.text
    for gone in (False, True):  # from the cache, then after the hour, from the store
        if gone:
            c.app.state.answers._entries.clear()
        again = c.get(f"/answers/{stored.id}")
        assert again.status_code == 200 and "Hold off watering." in again.text, gone
