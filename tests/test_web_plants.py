import json

import httpx
import respx

from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_web import ADV, SAMPLE
from tests.test_web_history import SAGE, _signed_in, _upload


@respx.mock
def test_plants_page_lists_plants_with_their_visits(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    r = c.get("/plants")
    assert r.status_code == 200 and "Sage" in r.text and "Water it." in r.text
    assert "<img" in r.text  # the latest thumbnail


def test_plants_page_needs_sign_in(tmp_path):
    from herbtwin.history import MemoryHistory
    from tests.fakes import FakeAuth, fake_accounts
    from tests.test_web import _client

    c = _client(tmp_path, [], [], accounts=fake_accounts(MemoryHistory(), FakeAuth()))
    r = c.get("/plants", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/auth/sign-in"


@respx.mock
def test_rename_and_delete_a_plant(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    pid = store.list_plants()[0].id
    assert (
        c.post(
            f"/plants/{pid}/rename", data={"name": "Trough sage"}, follow_redirects=False
        ).status_code
        == 303
    )
    assert store.list_plants()[0].name == "Trough sage"
    assert c.post(f"/plants/{pid}/rename", data={"name": ""}).status_code == 400
    assert c.post(f"/plants/{pid}/delete", follow_redirects=False).status_code == 303
    assert store.list_plants() == [] and not any(k.startswith("u1/") for k in hist.photos)


@respx.mock
def test_the_plants_page_asks_before_deleting(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    page = c.get("/plants").text
    assert "return confirm(" in page  # the plant delete asks first
    assert 'href="/account/delete"' in page and 'action="/account/delete"' not in page


@respx.mock
def test_a_plant_name_cannot_break_out_of_the_delete_prompt(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    store.rename_plant(store.list_plants()[0].id, "Kash's');alert(1)//")
    page = c.get("/plants").text
    prompt = page.split("onsubmit='")[1].split("'>")[0]
    assert "\\u0027);alert(1)//" in prompt and "');" not in prompt and "&#39;" not in prompt


@respx.mock
def test_each_visit_and_the_thumbnail_link_to_their_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    [visit] = store.answers_for(store.list_plants()[0].id)
    r = c.get("/plants")
    assert (
        r.text.count(f'href="/answers/{visit.id}"') == 3
    )  # the thumbnail, the visit line and "Open the latest answer"
    assert c.get(f"/answers/{visit.id}").status_code == 200


@respx.mock
def test_a_signed_in_answer_links_back_to_my_plants(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    page = _upload(c, place="")
    assert 'href="/plants"' in page.text


@respx.mock
def test_a_signed_out_answer_has_no_my_plants_link(tmp_path):
    from tests.test_web import OBS, _client

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    from tests.fakes import follow
    from tests.test_web import JPEG

    r = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}, data={"place": ""})
    page = follow(c, r)
    assert page.status_code == 200 and 'href="/plants"' not in page.text


@respx.mock
def test_the_answer_names_the_plant_once(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    mint = {
        **SAGE,
        "species": [{"name": "Mentha spicata (mint)", "common_name": "mint", "confidence": 0.9}],
    }
    c, _, _ = _signed_in(tmp_path, [json.dumps(mint)], [json.dumps(ADV)] * 3)
    page = _upload(c, place="")
    assert "Mint (Mentha spicata)" in page.text and "(mint))" not in page.text


@respx.mock
def test_the_plant_chooser_has_a_way_back(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, [json.dumps(ADV)] * 6)
    _upload(c, place="")
    chooser = _upload(c, place="")
    assert "Which plant is this?" in chooser.text and 'href="/"' in chooser.text


def test_my_plants_is_on_the_site_frame_with_the_nav_marked(tmp_path):
    from herbtwin.web import style

    c, _, _ = _signed_in(tmp_path, [], [])
    page = c.get("/plants").text
    assert page.count("<style>") == 1 and style.CSS in page and 'class="wordmark"' in page
    assert 'href="/plants" aria-current="page"' in page and 'action="/auth/sign-out"' in page
    assert "style=" not in page and page.count("<h1>") == 1


def test_my_plants_with_no_plants_offers_the_upload(tmp_path):
    c, _, _ = _signed_in(tmp_path, [], [])
    page = c.get("/plants").text
    assert (
        "No plants yet" in page and '<a class="button primary" href="/">Upload a photo</a>' in page
    )
    assert "Your account" in page and 'href="/account/delete"' in page


@respx.mock
def test_the_plant_chooser_is_on_the_site_frame_and_offers_a_new_plant(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, [json.dumps(ADV)] * 6)
    _upload(c, place="")
    chooser = _upload(c, place="").text
    assert "<h1>Which plant is this?</h1>" in chooser and 'class="wordmark"' in chooser
    assert 'href="/plants"' in chooser and 'action="/auth/sign-out"' in chooser  # signed in
    assert 'name="plant_id" value="new"' in chooser and "style=" not in chooser


@respx.mock
def test_the_latin_name_starts_with_a_capital(tmp_path):
    # live 14 Oct: names are stored lower-case, so My plants showed "ocimum basilicum"
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    assert '<p class="muted small plant-species">Salvia officinalis</p>' in c.get("/plants").text


@respx.mock
def test_my_plants_is_a_band_then_a_grid_of_short_cards(tmp_path):
    # 16 Oct, Kash: "/plants still looks weird": the narrow column and every card open to
    # its reminder, rename and delete. Now the home look, and the card's chores fold away
    from herbtwin.web import style

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    empty = c.get("/plants").text  # no plants yet: the band still offers the upload
    assert '<div class="page-band">' in empty and 'href="/">Upload a photo</a>' in empty
    _upload(c, place="")
    page = c.get("/plants").text
    assert (
        '<body class="plants-page has-band">' in page
        and '<main id="content" tabindex="-1"><div class="wrap wide">' in page
    )
    assert page.index('<div class="page-band">') < page.index('<div class="plant-grid">')
    card = page.split('<article class="card plant">', 1)[1].split("</article>", 1)[0]
    top, manage = card.split('<details class="plant-manage">', 1)
    assert 'action="/plants/' in manage and "Delete this plant" in manage  # folded away
    assert "Delete this plant" not in top and 'class="plant-latest"' in top
    assert (
        ".plants-page .plant, .plants-page .plants-empty { margin: 0; border: 1.5px solid"
        in style.CSS
    )
