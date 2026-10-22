"""The "What can I grow here?" page (spot spec S6): off unless HERBTWIN_SPOT_ENABLED; the
direction card during the read (an 8-way pick: the compass failed step 0); answers rerun
code only; the JSON API."""

import json
import re
from datetime import date, timedelta

import httpx
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.history import MemoryHistory
from herbtwin.pipeline import Deps
from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web import style
from herbtwin.web.app import create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import JPEG, LEAVE, MINT, OCT_4, SAMPLE

HOME = {"HERBTWIN_HOME_LAT": "51.26", "HERBTWIN_HOME_LON": "-0.31"}  # Box Hill: open, with a pH
BED = {"setting": "raised_bed", "medium": "soil", "texture_lean": "unknown",
       "texture_lean_conf": 0, "backed_by_wall": False}  # fmt: skip
WALLED = {**BED, "backed_by_wall": True}  # a wall or fence behind: the direction counts


def _client(tmp_path, spot=True, observe=None, advise=None, home=HOME):
    env = {**home, "HERBTWIN_SPOT_ENABLED": "1"} if spot else home
    deps = Deps(
        observe_adapter=MockAdapter(observe if observe is not None else [json.dumps(BED)]),
        advise_adapter=MockAdapter(advise or []),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps, clock=lambda: OCT_4)), deps


def _archive():
    days = [(date(1991, 7, 1) + timedelta(days=i)).isoformat() for i in range(365 * 30 + 8)]
    return httpx.Response(
        200, json={"daily": {"time": days, "temperature_2m_min": [-7.0] * len(days)}}
    )


def test_off_no_entry_and_no_routes(tmp_path):
    c, _ = _client(tmp_path, spot=False)
    assert "/spots" not in c.get("/").text and "Analyse" in c.get("/").text
    assert c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).status_code == 404
    assert c.get("/spots/" + "a" * 32).status_code == 404


def test_the_compass_probe_page_is_gone(tmp_path):
    deps = Deps(
        observe_adapter=MockAdapter(),
        advise_adapter=MockAdapter(),
        settings=load_settings({**HOME, "HERBTWIN_COMPASS_PROBE": "1"}),  # an old .env
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    assert TestClient(create_app(deps)).get("/probe/compass").status_code == 404


@respx.mock
def test_upload_asks_the_direction_while_reading_then_the_answer(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, deps = _client(tmp_path)
    assert 'formaction="/spots"' in c.get("/").text
    r = c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert "data-compass" in r.text and "Which way does it face?" in r.text
    assert 'name="direction"' in r.text and "data-compass-tap>" not in r.text  # 8-way only
    head = r.text.split("<ol>", 1)[0]
    assert "My plants" not in head and "your photo is not kept" in head  # amendment 2
    page = follow(c, r)
    assert page.status_code == 200 and "What could grow here" in page.text
    assert "Raised bed" in page.text and "Good now" in page.text
    assert "Looks like garden soil." in page.text  # the photo alone never states soil
    assert 'href="/plants"' not in page.text  # signed out: no My plants link
    assert "British Geological Survey" in page.text and "HadUK-Grid" in page.text
    assert len(deps.observe_adapter.calls) == 1
    climate._cache.clear()


@respx.mock
def test_the_answer_is_a_site_page_with_one_sheet_and_no_inline_styles(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    c.app.state.accounts = fake_accounts(MemoryHistory(), FakeAuth())
    page = _spot(c)
    assert '<header class="site">' in page.text and 'href="/auth/sign-in"' in page.text
    assert 'href="/plants"' not in page.text  # signed out
    assert page.text.count("<style>") == 1 and 'style="' not in page.text
    assert page.text.count("<h1>") == 1 and 'class="spot-hero"' in page.text
    assert "survey" not in page.text  # the survey square is gone (it ran through the heading)
    assert page.text.count('class="button primary"') == 1  # one main action
    climate._cache.clear()


@respx.mock
def test_a_tap_during_the_read_and_a_squeeze_after_rerun_code_only(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, deps = _client(tmp_path, observe=[json.dumps(WALLED)])
    r = c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    rid = re.search(r'action="/spots/([0-9a-f]{32})/told"', r.text).group(1)
    tap = {"direction": "S"}
    assert (
        c.post(f"/spots/{rid}/told", data=tap, headers={"X-Herbtwin-Fetch": "1"}).status_code == 204
    )
    page = c.get(f"/spots/{rid}")
    assert "from the direction you picked" in page.text
    after = c.post(f"/spots/{rid}/told", data={"squeeze": "sticky"})
    assert (
        after.status_code == 200 and "Your squeeze test says <strong>clayey</strong>" in after.text
    )
    assert "Garden soil." in after.text and "Looks like garden soil." not in after.text
    assert "from the direction you picked" in after.text  # the earlier answer still counts
    assert len(deps.observe_adapter.calls) == 1  # no second vision call
    climate._cache.clear()


@respx.mock
def test_bad_answers_are_400_and_unknown_spots_404(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = page.url.path.rsplit("/", 1)[1]
    for bad in ({"setting": "lawn"}, {"pot_size": "huge"}, {"heading": "400"}, {"squeeze": "wet"}):
        assert c.post(f"/spots/{rid}/told", data=bad).status_code == 400, bad
    assert c.post("/spots/" + "b" * 32 + "/told", data={"squeeze": "sticky"}).status_code == 404
    climate._cache.clear()


@respx.mock
def test_a_sunny_photo_with_no_json_still_gets_an_answer(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(503))
    c, _ = _client(tmp_path, observe=["thinking about shadows..."])
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert page.status_code == 200 and "couldn't read the spot" in page.text
    assert "Setting not clear" in page.text
    # the maps know the ground; with the setting unclear the page says how to see it, not
    # "Soil not known here" (17 Oct: read as a gap in the BGS soil feature)
    soil = page.text.split('<details class="soil">', 1)[1].split("</details>", 1)[0]
    assert "Soil not known here" not in soil
    assert 'pick "Bed or border" above' in soil
    climate._cache.clear()


@respx.mock
def test_the_json_api(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, observe=[json.dumps(WALLED)])
    r = c.post(
        "/api/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}, data={"direction": "S"}
    )
    body = r.json()
    assert r.status_code == 200 and body["spot"]["sun"]["method"] == "direction"
    assert body["grow"]["month"] == 10 and body["observation"] is None
    assert "51.26" not in json.dumps(body["notes"])
    assert len(c.app.state.spots) == 0  # nothing reads an API spot back, so none is kept
    climate._cache.clear()


@respx.mock
def test_about_this_spot_from_a_plant_answer(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, deps = _client(tmp_path, observe=[json.dumps(MINT)], advise=[json.dumps(LEAVE)] * 3)
    answer = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    rid = answer.url.path.rsplit("/", 1)[1]
    assert f"/answers/{rid}/spot" in answer.text
    spot = c.get(f"/answers/{rid}/spot")
    assert spot.status_code == 200 and "What could grow here" in spot.text and "Pot" in spot.text
    assert len(deps.observe_adapter.calls) == 1
    climate._cache.clear()


def _sign_in(c, hist, auth):
    c.app.state.accounts = fake_accounts(hist, auth)
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "a@b.co"), "type": "email"},
        follow_redirects=False,
    )


@respx.mock
def test_signed_in_a_second_spot_at_the_same_place_reuses_the_tap(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    hist, auth = MemoryHistory(), FakeAuth()
    c, deps = _client(tmp_path, observe=[json.dumps(WALLED)])
    _sign_in(c, hist, auth)
    deps.observe_adapter.responses.append(deps.observe_adapter.responses[0])
    first = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = first.url.path.rsplit("/", 1)[1]
    c.post(f"/spots/{rid}/told", data={"direction": "S"})
    [(owner, row)] = hist.spots.values()
    assert owner == "u1" and row.aspect.source == "tapped_direction" and row.place.lat == 51.26
    second = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert "Using the direction you picked here on 4 Oct." in second.text
    assert 'href="/plants"' in second.text  # amendment 8: My plants for signed-in people
    climate._cache.clear()


@respx.mock
def test_correcting_a_misread_trough_says_bought_compost(tmp_path):
    """The S2 safeguard: a trough close-up read as soil in open ground, corrected."""
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    misread = {**BED, "setting": "open_ground"}
    c, _ = _client(tmp_path, observe=[json.dumps(misread)])
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = page.url.path.rsplit("/", 1)[1]
    assert "Looks like garden soil." in page.text
    fixed = c.post(f"/spots/{rid}/told", data={"setting": "trough"})
    assert fixed.status_code == 200 and "Bought compost." in fixed.text
    assert "garden soil" not in fixed.text.lower()
    climate._cache.clear()


@respx.mock
def test_the_rest_of_each_tier_folds_away_without_script(tmp_path):
    """5 a tier are shown (round 3: the page was far too long at 8); the fitting RHS picks
    are mostly in the rest (recall 0.90 in the full tiers), so each tier's rest is one plain
    <details> away, and the verdict line counts the whole tier."""
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    good = page.text.split("<h2>Good now</h2>", 1)[1].split("<h2>", 1)[0]
    m = re.search(
        r"<details class=\"more\"><summary>(\d+) more</summary>(.*?)</details>", good, re.S
    )
    assert m is not None
    assert m.group(2).count('<li class="pick">') == int(m.group(1)) > 0
    assert good.split("<details", 1)[0].count('<li class="pick">') == 5
    assert "<script" not in good
    line = re.search(r'<a href="#good-now">Good now</a>: [^<]* and (\d+) more</li>', page.text)
    assert line is not None and int(line.group(1)) == 5 + int(m.group(1)) - 3
    climate._cache.clear()


def _spot(c):
    return follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))


@respx.mock
def test_about_this_spot_reuses_one_spot_per_answer(tmp_path):
    """Repeat clicks reuse the spot: one cache entry and one stored row, not one each."""
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    hist, auth = MemoryHistory(), FakeAuth()
    c, _ = _client(tmp_path, observe=[json.dumps(MINT)], advise=[json.dumps(LEAVE)] * 3)
    _sign_in(c, hist, auth)
    answer = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    rid = answer.url.path.rsplit("/", 1)[1]
    targets = set()
    for _ in range(3):
        r = c.get(f"/answers/{rid}/spot", follow_redirects=False)
        targets.add(r.headers["location"])
        assert c.get(r.headers["location"]).status_code == 200
    assert len(targets) == 1 and len(c.app.state.spots) == 1 and len(hist.spots) == 1
    climate._cache.clear()


@respx.mock
def test_a_picked_direction_can_be_changed_where_it_matters(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, observe=[json.dumps(WALLED)])
    rid = _spot(c).url.path.rsplit("/", 1)[1]
    north = c.post(f"/spots/{rid}/told", data={"direction": "N"})
    assert "Change direction" in north.text and 'value="N" checked' in north.text
    south = c.post(f"/spots/{rid}/told", data={"direction": "S"})
    assert 'value="S" checked' in south.text and "from the direction you picked" in south.text
    june = re.compile(r"About (\d+) h of direct sun on a clear June day")
    assert june.search(north.text).group(1) != june.search(south.text).group(1)
    climate._cache.clear()


def test_the_open_spot_wording_matches_the_default_horizon():
    # 17 Oct: the page said "open sky with a low horizon", yet the defaults are a fence
    # about 20 degrees up all round, so winter showed 0 h of sun and read as a bug
    from herbtwin import sun
    from herbtwin.web.app import TEMPLATES

    assert sun.DEFAULT_PITCH == sun.BACK_OPEN == 20.0  # what "1.8 m, 5 m away" describes
    page = TEMPLATES.env.loader.get_source(TEMPLATES.env, "spot.html")[0]
    assert "low horizon" not in page and "about 1.8 m high and 5 m away" in page


@respx.mock
def test_an_open_spot_says_the_direction_changes_nothing(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)  # open behind
    r = c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert "the answer will use it." not in r.text  # the wait card promises nothing
    page = follow(c, r)
    rid = page.url.path.rsplit("/", 1)[1]
    # said short by the sun hours, in full under "Where this comes from" (19 Oct small print)
    assert "assumes a typical 1.8 m fence about 5 m away" in page.text
    assert 'name="direction"' not in page.text and "Change direction" not in page.text
    after = c.post(f"/spots/{rid}/told", data={"direction": "S"})
    assert "from the direction you picked" not in after.text
    assert "assumes a typical 1.8 m fence about 5 m away" in after.text
    climate._cache.clear()


@respx.mock
def test_a_texture_the_photo_moved_is_credited_to_the_photo_too(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    leaning = {**BED, "texture_lean": "sandy", "texture_lean_conf": 0.8}
    c, _ = _client(tmp_path, observe=[json.dumps(leaning)])
    page = _spot(c)
    assert "The maps and your photo suggest <strong>sandy</strong>" in page.text
    assert "The maps suggest" not in page.text
    climate._cache.clear()


@respx.mock
def test_compost_in_a_raised_bed_shows_no_map_soil(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, observe=[json.dumps({**BED, "medium": "compost"})])
    page = _spot(c)
    assert "Bought compost." in page.text
    assert "The maps suggest" not in page.text and "Topsoil pH" not in page.text
    assert 'name="squeeze"' not in page.text
    climate._cache.clear()


@respx.mock
def test_answering_before_the_read_ends_without_script_waits_not_expires(tmp_path):
    c, _ = _client(tmp_path)
    c.app.state.spots.start("c" * 32, None)  # the photo is still being read
    r = c.post("/spots/" + "c" * 32 + "/told", data={"direction": "S"})
    assert r.status_code == 200 and "Still reading your photo" in r.text
    assert '<meta http-equiv="refresh" content="3">' in r.text and "expired" not in r.text


@respx.mock
def test_no_location_says_why_and_asks_nothing(tmp_path):
    archive = respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, home={})
    page = _spot(c)
    assert "We couldn&#39;t tell where this is" in page.text and "for the UK" not in page.text
    assert 'name="squeeze"' not in page.text and 'name="direction"' not in page.text
    assert "British Geological Survey" not in page.text and "HadUK" not in page.text
    assert archive.call_count == 0


@respx.mock
def test_a_windowsill_shows_no_outdoor_lines(tmp_path):
    archive = respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, observe=[json.dumps({**BED, "setting": "windowsill"})])
    page = _spot(c)
    assert "Windowsill" in page.text and "air frosts" not in page.text
    assert "coldest night" not in page.text and "running warm" not in page.text
    assert archive.call_count == 0


@respx.mock
def test_a_walled_spot_with_no_list_does_not_ask_for_a_direction_it_cannot_take(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    paris = {"HERBTWIN_HOME_LAT": "48.85", "HERBTWIN_HOME_LON": "2.35"}
    c, _ = _client(tmp_path, observe=[json.dumps(WALLED)], home=paris)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert 'name="direction"' not in page.text
    assert "pick the way it faces to firm it up" not in page.text
    climate._cache.clear()


@respx.mock
def test_a_read_that_crashes_is_expired_not_still_reading(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    app = c.app
    rid = "b" * 32
    app.state.spots.start(rid, None)
    app.state.spots.drop(rid)  # what the read's failure path does
    r = c.get(f"/spots/{rid}")
    assert r.status_code == 404 and "refresh" not in r.text
    climate._cache.clear()


TOWN = {"HERBTWIN_HOME_LAT": "51.501", "HERBTWIN_HOME_LON": "-0.142"}  # a built-up cell


def _main(page):
    return page.text.split('<main id="content" tabindex="-1">', 1)[1]


@respx.mock
def test_the_verdict_comes_first_then_the_questions_then_the_top_picks(tmp_path):
    """Round 3, three jobs: a line per group on the first screen, then the two questions,
    then the picks; a row never repeats the fine conditions. 22 Oct: the questions came
    after both long lists in the source, so a phone (and Tab, and a screen reader) met
    them 2,700 px down. The source now runs in the phone's order, details last, so Tab
    and a screen reader follow what a phone shows."""
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, observe=[json.dumps(WALLED)])
    main = _main(_spot(c))
    order = [
        '<ul class="verdict">',
        '<a href="#good-now">Good now</a>: ',
        '<dl class="sheet">',
        "<h2>Two quick answers make this surer</h2>",
        'name="direction"',
        'name="squeeze"',
        "<h2>Good now</h2>",
        '<li class="pick">',
        "<h2>Worth a try</h2>",
        "<h2>The details</h2>",
        "<summary>The spot: sun and frost</summary>",
        "<summary>The soil</summary>",
        "<summary>Where this comes from</summary>",
        'class="actions spot-again"',
    ]
    at = [main.index(s) for s in order]
    assert at == sorted(at), order
    for fine in ("Sun: fits", "Soil: fits", "Frost: fine", "Timing: now", "Frost: not needed"):
        assert fine not in main, fine
    assert "Sources:" not in main and main.count('class="src"') > 0  # one small link a row
    climate._cache.clear()


def test_a_wide_screen_keeps_the_questions_and_details_in_the_side_column():
    """The source runs verdict, questions, picks, details (a phone's order). Wide, the
    verdict and picks float left and the questions right, and the details clear only the
    questions, so each column stacks on its own as the old two-column grid did."""
    css = (style.STATIC / "pages" / "spot.css").read_text()
    wide = css.split("@media (min-width: 960px) {", 1)[1].split("\n}", 1)[0]
    assert (
        "float: left; clear: left;"
        in wide.split(".spot-page .spot-hero, .spot-page .spot-picks")[1]
    )
    assert ".spot-page .sharpen { float: right; width: 26rem;" in wide
    assert ".spot-page .spot-side { display: flow-root; clear: right; width: 26rem;" in wide
    assert ".spot-page .spot-again { clear: both; }" in wide
    assert not re.search(r"[{;]\s*order:", css)  # nothing is shown out of source order
    assert ".spot-side { display: contents" not in css


@respx.mock
def test_the_lead_note_leaves_the_top_of_the_page(tmp_path):
    """A raised bed of the ground's soil: the lead note sits in the folded soil details.
    A bed or border (food in the ground itself): it stays open, but after the top picks."""
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path, home=TOWN)
    main = _main(_spot(c))
    soil = main.split("<summary>The soil</summary>", 1)[1].split("</details>", 1)[0]
    assert main.count("hold lead") == 1 and "hold lead" in soil
    c, _ = _client(tmp_path, observe=[json.dumps({**BED, "setting": "open_ground"})], home=TOWN)
    main = _main(_spot(c))
    assert main.count("hold lead") == 1
    lead = main.index("Check the soil for lead.")
    assert main.index("<h2>Worth a try</h2>") < lead < main.index("<h2>The details</h2>")
    climate._cache.clear()


def test_an_expired_spot_answer_starts_again_at_the_photo_box(tmp_path):
    c, _ = _client(tmp_path)
    r = c.get("/spots/" + "d" * 32)
    assert r.status_code == 404 and '<a class="button primary" href="/">Check a plant</a>' in r.text
    page = (TEMPLATES_DIR / "spot.html").read_text("utf-8")
    assert '<a class="button primary" href="/">Try another photo</a>' in page


TEMPLATES_DIR = style.STATIC.parent / "templates"


@respx.mock
def test_a_spot_read_by_the_backup_model_asks_pot_or_ground_first(tmp_path):
    """While GLM is down Gemma reads spots, and it reads pots as open ground (13 Oct eval:
    setting 0.78, target 0.90): one tap settles it before the list is trusted."""
    from herbtwin.adapters.fallback import FallbackAdapter

    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    misread = {**BED, "setting": "open_ground"}
    c, deps = _client(tmp_path)
    deps.observe_adapter = FallbackAdapter(MockAdapter([]), MockAdapter([json.dumps(misread)]))
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = page.url.path.rsplit("/", 1)[1]
    check = page.text.split('class="tray warn setting-check" aria-label="Pot or ground"', 1)[1]
    check = check.split("</form>", 1)[0]
    assert "Is it in a pot or in the ground?" in check
    # one control at a time: the dropdown waits until the question is answered (14 Oct)
    assert '<form class="spot-fix"' not in page.text
    for v in ("pot", "raised_bed", "open_ground"):
        assert f'name="setting" value="{v}"' in check
    fixed = c.post(f"/spots/{rid}/told", data={"setting": "pot"})
    assert (
        '<form class="tray warn setting-check"' not in fixed.text
        and "Bought compost." in fixed.text
        and '<form class="spot-fix"' in fixed.text
    )
    climate._cache.clear()


@respx.mock
def test_a_spot_read_by_the_first_model_asks_nothing_extra(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert '<form class="tray warn setting-check"' not in page.text
    climate._cache.clear()


ROCKET_BED = {
    **MINT,
    "species": [
        {"name": "Eruca vesicaria", "common_name": "salad rocket", "confidence": 0.6},
        {"name": "Lactuca sativa", "common_name": "lettuce", "confidence": 0.3},
    ],
    "scene": "bed_or_border",
    "container": "ground",
}
BARE_BED = {**ROCKET_BED, "species": []}


@respx.mock
def test_a_bare_bed_leads_with_what_grows_here(tmp_path):
    # one photo, one box: bare ground sent to "What does my plant need?" is offered the spot
    # answer from the same read, with no second vision call
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, deps = _client(tmp_path, observe=[json.dumps(BARE_BED)])
    answer = follow(c, c.post("/analyse", files={"photo": ("bed.jpg", JPEG, "image/jpeg")}))
    rid = answer.url.path.rsplit("/", 1)[1]
    assert "<h1>This looks like a bed, ready for planting</h1>" in answer.text
    assert f'class="button primary" href="/answers/{rid}/spot">See what grows here' in answer.text
    assert "No plant found" not in answer.text
    spot = c.get(f"/answers/{rid}/spot")
    assert spot.status_code == 200 and "What could grow here" in spot.text
    assert len(deps.observe_adapter.calls) == 1 and len(deps.advise_adapter.calls) == 0
    climate._cache.clear()


@respx.mock
def test_an_empty_pot_is_called_a_pot_and_still_offered_what_grows_in_it(tmp_path):
    # #324 follow-up: compost ready for planting reads as a bare bed, a pot of it too. A pot
    # the read saw is a pot, and its spot answer is for a pot (spot.spot_from_record)
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, deps = _client(tmp_path, observe=[json.dumps({**BARE_BED, "container": "pot"})])
    answer = follow(c, c.post("/analyse", files={"photo": ("pot.jpg", JPEG, "image/jpeg")}))
    rid = answer.url.path.rsplit("/", 1)[1]
    assert "<h1>This looks like a pot, ready for planting</h1>" in answer.text
    assert "a bed" not in answer.text
    assert f'class="button primary" href="/answers/{rid}/spot">See what grows here' in answer.text
    spot = c.get(f"/answers/{rid}/spot")
    assert "<dt>Setting</dt><dd>Pot" in spot.text
    assert len(deps.observe_adapter.calls) == 1 and len(deps.advise_adapter.calls) == 0
    climate._cache.clear()


@respx.mock
def test_a_planted_bed_gets_its_answer_and_an_offer_of_what_else_grows(tmp_path):
    # a wrong "bed" read (herbs side by side) costs one line, never the advice
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, deps = _client(tmp_path, observe=[json.dumps(ROCKET_BED)], advise=[json.dumps(LEAVE)] * 3)
    asked = follow(c, c.post("/analyse", files={"photo": ("bed.jpg", JPEG, "image/jpeg")}))
    # different plants: asked which first (tapping.py); the whole photo gives the bed answer
    tid = re.search(r'action="/taps/([0-9a-f]+)"', asked.text).group(1)
    answer = follow(c, c.post(f"/taps/{tid}", data={"whole": "1"}))
    rid = answer.url.path.rsplit("/", 1)[1]
    assert "Salad rocket" in answer.text and "This looks like a bed" not in answer.text
    offer = f'Looks like a bed or border? <a class="band-go" href="/answers/{rid}/spot">See what else could grow here'
    assert offer in answer.text
    assert answer.text.index(offer) < answer.text.index("Leave it for now")  # above the advice
    assert c.get(f"/answers/{rid}/spot").status_code == 200
    assert len(deps.observe_adapter.calls) == 1
    one, _ = _client(tmp_path, observe=[json.dumps(MINT)], advise=[json.dumps(LEAVE)] * 3)
    page = follow(one, one.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    assert "Looks like a bed or border?" not in page.text  # one plant: no offer
    off, _ = _client(
        tmp_path, spot=False, observe=[json.dumps(ROCKET_BED)], advise=[json.dumps(LEAVE)] * 3
    )
    page = follow(off, off.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    tid = re.search(r'action="/taps/([0-9a-f]+)"', page.text).group(1)
    page = follow(off, off.post(f"/taps/{tid}", data={"whole": "1"}))
    assert "Salad rocket" in page.text and "Looks like a bed" not in page.text  # spot off
    climate._cache.clear()


def test_a_bare_bed_without_the_spot_feature_asks_for_one_plant(tmp_path):
    c, _ = _client(tmp_path, spot=False, observe=[json.dumps(BARE_BED)])
    answer = follow(c, c.post("/analyse", files={"photo": ("bed.jpg", JPEG, "image/jpeg")}))
    assert "<h1>This looks like a bed, ready for planting</h1>" in answer.text
    assert "/spot" not in answer.text and 'class="button primary" href="/"' in answer.text


@respx.mock
def test_a_signed_in_bed_is_theirs_alone_and_repeat_clicks_reuse_its_spot(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    hist, auth = MemoryHistory(), FakeAuth()
    c, deps = _client(tmp_path, observe=[json.dumps(BARE_BED)])
    _sign_in(c, hist, auth)
    answer = follow(c, c.post("/analyse", files={"photo": ("bed.jpg", JPEG, "image/jpeg")}))
    rid = answer.url.path.rsplit("/", 1)[1]
    stranger = TestClient(c.app)  # same server, no session: not the owner
    assert stranger.get(f"/answers/{rid}/spot", follow_redirects=False).status_code == 404
    targets = {c.get(f"/answers/{rid}/spot", follow_redirects=False).headers["location"]}
    targets.add(c.get(f"/answers/{rid}/spot", follow_redirects=False).headers["location"])
    assert len(targets) == 1 and len(c.app.state.spots) == 1
    assert len(deps.observe_adapter.calls) == 1
    climate._cache.clear()


@respx.mock
def test_the_sun_row_shows_the_spots_year_under_it(tmp_path):
    # idea 11 (18 Oct): the clear-day hours the page already tabulates, drawn small under
    # the Sun row, with this month's and next month's hours in words
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _client(tmp_path)
    page = _spot(c).text
    fig = page.split('<figure class="sun-arc">')[1].split("</figure>")[0]
    assert fig.count("<polyline") == 1 and fig.count("<polygon") == 1
    assert 'role="img" aria-label="Clear-day sun over the year: most in ' in fig
    assert "<figcaption>On a clear day here: " in fig and "of direct sun in October" in fig
    assert "<text" not in fig  # never small text inside the drawing
    # 19 Oct final look: "6 h in October, under 1 h in November" read like a bug with no
    # months on the curve; the initials sit under it, the photo's month marked
    months = fig.split('<ol class="months" aria-hidden="true">')[1].split("</ol>")[0]
    assert months.count("<li") == 12 and '<li class="now">O</li>' in months
    assert page.index('class="sheet"') < page.index('class="sun-arc"')
    climate._cache.clear()
