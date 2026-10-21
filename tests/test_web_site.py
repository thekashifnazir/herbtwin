"""The site frame, round 3: a deep-green header band on every page, the nav's jobs on
every page (one photo box: /grow redirects home), no back links that only go home, notes at 16px,
My plants newest first, and a wide frame option for the answer and spot pages."""

import json
import uuid
from datetime import timedelta

import httpx
import respx

from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import style
from tests.test_web import ADV, SAMPLE, _client
from tests.test_web_accounts import _accounts_client, _sign_in
from tests.test_web_history import SAGE, _signed_in, _upload
from tests.test_web_home import _contrast, _tokens
from tests.test_web_judge import _client as _judge_client
from tests.test_web_spot import _client as _spot_client


def _nav(page: str) -> str:
    return page.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]


def test_the_nav_names_the_jobs_and_marks_the_page_you_are_on(tmp_path):
    # 16 Oct: one photo box takes a plant or a bed, so "What can I grow here?" is no
    # longer a tab of its own; it stays a button on the home form
    spot, _ = _spot_client(tmp_path)
    home = _nav(spot.get("/").text)
    assert '<a href="/" aria-current="page">Check a plant</a>' in home
    assert "/grow" not in home and "What can I grow here?" not in home
    off = _nav(_client(tmp_path, [], []).get("/privacy").text)
    assert "Check a plant" in off and "/grow" not in off


def test_pages_that_never_look_the_person_up_still_show_the_right_account_links(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    signed_out = _nav(c.get("/privacy").text)
    assert 'href="/auth/sign-in"' in signed_out and 'href="/plants"' not in signed_out
    _sign_in(c, auth)
    for path in ("/privacy", "/auth/sign-in", "/account/delete"):
        nav = _nav(c.get(path).text)  # the session cookies are there: signed in
        assert 'href="/plants"' in nav and 'action="/auth/sign-out"' in nav, path
        assert 'href="/auth/sign-in"' not in nav, path


def test_the_page_after_deleting_the_account_shows_sign_in_not_sign_out(tmp_path):
    c, _, auth = _signed_in(tmp_path, [], [])
    r = c.post("/account/delete", data={"confirm": "delete"})
    assert "Your account and everything in it are deleted." in r.text
    nav = _nav(r.text)  # the request still carried the cookies this response clears
    assert 'action="/auth/sign-out"' not in nav and 'href="/plants"' not in nav


def test_the_old_grow_tab_lands_on_the_one_photo_box(tmp_path):
    for spot_on in (True, False):
        c = _spot_client(tmp_path, spot=spot_on)[0]
        r = c.get("/grow", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "/"
    home = _spot_client(tmp_path)[0].get("/grow").text
    assert 'formaction="/spots">What can I grow here?' in home  # still a button on the form


def test_no_back_links_that_only_go_home(tmp_path):
    c, _, _ = _accounts_client(tmp_path)
    for path in ("/privacy", "/auth/sign-in"):
        assert 'class="back"' not in c.get(path).text, path
    assert 'class="back"' not in _judge_client(tmp_path).get("/judge").text
    sent = c.post("/auth/sign-in", data={"email": "a@b.co"}).text  # a message page
    assert "Check your email" in sent and 'class="button"' not in sent
    assert 'aria-current="page"' not in _nav(sent)  # a message, not the sign-in page
    bad = c.post("/auth/sign-in", data={"email": "nope"}).text  # this one leads somewhere
    assert '<a class="button primary" href="/auth/sign-in">Try again</a>' in bad


def test_the_header_band_reads_in_light_and_dark():
    assert ".site { position: relative; background: var(--band); color: var(--band-fg); }" in (
        style.CSS
    )
    assert ".site :focus-visible { outline-color: var(--band-fg); }" in style.CSS
    assert 'stroke="var(--band)"' in style.MARK  # the leaf's vein, cut in the band's green
    for i in (0, 1):  # light, dark
        band = _tokens("band")[i]
        assert _contrast(_tokens("band-fg")[i], band) >= 7  # wordmark, nav, focus, page bar
        assert _contrast(_tokens("band-muted")[i], band) >= 4.5


def test_notes_are_16px_and_muted_text_reads_on_every_surface():
    assert "small, .small { font-size: 16px; }" in style.CSS
    assert (
        ".foot { border-top: 1px solid var(--border); padding: 16px 0 32px; font-size: 16px;"
        in (style.CSS)
    )
    assert ".home-page .home-go-for { display: block; font-size: 16px;" in style.CSS
    for i in (0, 1):  # light, dark
        muted = _tokens("muted-fg")[i]
        for under in ("bg", "card", "muted", "soft", "warn-bg", "clay-bg"):
            assert _contrast(muted, _tokens(under)[i]) >= 4.5, (i, under)


def test_the_frame_has_a_wide_option_and_a_two_column_helper(tmp_path):
    assert ".wrap { max-width: var(--frame);" in style.CSS and "--frame: 72rem;" in style.CSS
    assert "main .wrap.wide { padding-right: 16px; }" in style.CSS
    wide = style.CSS.split("@media (min-width: 960px)", 1)[1]
    assert ".cols { display: grid;" in wide
    c, _, _ = _accounts_client(tmp_path)
    assert (
        '<main id="content" tabindex="-1"><div class="wrap wide">' in c.get("/").text
    )  # home: form and example
    assert (
        '<main id="content" tabindex="-1"><div class="wrap">' in c.get("/privacy").text
    )  # the reading column


@respx.mock
def test_my_plants_lists_the_most_recently_photographed_plant_first(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    [sage] = store.list_plants()
    [visit] = store.answers_for(sage.id)
    mint = store.create_plant("Mint", "mentha spicata", "mentha", None)  # added after sage
    later = visit.taken_at + timedelta(days=2)
    store.add_answer(visit.model_copy(update={"id": uuid.uuid4().hex, "plant_id": mint.id,
                                              "taken_at": later}))  # fmt: skip
    store.create_plant("Thyme", "thymus vulgaris", "thymus", None)  # no photo yet: last
    page = c.get("/plants").text
    assert page.index("<h2>Mint</h2>") < page.index("<h2>Sage</h2>") < page.index("<h2>Thyme</h2>")
    # a newer photo of the older plant moves it back to the top: the latest photo decides
    store.add_answer(visit.model_copy(update={"id": uuid.uuid4().hex,
                                              "taken_at": later + timedelta(days=2)}))  # fmt: skip
    page = c.get("/plants").text
    assert page.index("<h2>Sage</h2>") < page.index("<h2>Mint</h2>")
