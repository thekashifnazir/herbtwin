from herbtwin.history import HistoryError, MemoryHistoryStore
from herbtwin.web import remember
from tests.test_web import _client
from tests.test_web_accounts import _accounts_client, _sign_in

ASK = "Help improve advice for everyone?"


def test_the_ask_shows_after_sign_in_and_not_after_an_answer(tmp_path):
    c, hist, auth = _accounts_client(tmp_path)
    assert ASK not in c.get("/").text  # signed out: never asked
    _sign_in(c, auth)
    page = c.get("/").text
    assert ASK in page and "We'd share how past advice turned out, never your photos." in page
    r = c.post("/account/sharing", data={"share": "yes", "back": "/"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    got = hist.for_user("u1").get_settings()
    assert got.share_scored_pairs is True and got.asked_at is not None
    assert ASK not in c.get("/").text


def test_the_home_page_saves_the_choice_in_the_background(tmp_path):
    # a reload would wipe a photo already picked, so the page's script asks for a 204
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    page = c.get("/").text
    ask = page.split('class="tray home-ask"', 1)[1].split("</form>", 1)[0]
    assert 'id="ask-said" role="status" aria-live="polite"' in ask
    script = page.split("<script>", 1)[1]
    assert 'document.getElementById("ask")' in script and '"X-Herbtwin-Fetch": "1"' in script
    r = c.post(
        "/account/sharing",
        data={"share": "yes", "back": "/"},
        headers={"X-Herbtwin-Fetch": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 204 and r.content == b""
    assert hist.for_user("u1").get_settings().share_scored_pairs is True
    assert ASK not in c.get("/").text


def test_an_expired_sign_in_is_never_shown_as_saved(tmp_path):
    # fetch follows the sign-in redirect to a 200, so the script must only trust a 204
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    script = c.get("/").text.split("<script>", 1)[1]
    assert "r.status !== 204" in script
    c.cookies.clear()
    r = c.post(
        "/account/sharing",
        data={"share": "yes", "back": "/"},
        headers={"X-Herbtwin-Fetch": "1"},
        follow_redirects=False,
    )
    assert r.status_code != 204 and hist.settings == {}


def test_no_is_remembered_and_ends_the_ask_too(tmp_path):
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    c.post("/account/sharing", data={"share": "no", "back": "/"}, follow_redirects=False)
    got = hist.for_user("u1").get_settings()
    assert got.share_scored_pairs is False and got.asked_at is not None
    assert ASK not in c.get("/").text


def test_the_choice_changes_on_my_plants(tmp_path):
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    assert "Sharing how past advice turned out: <strong>off</strong>" in c.get("/plants").text
    r = c.post("/account/sharing", data={"share": "yes", "back": "/plants"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/plants"
    page = c.get("/plants").text
    assert "Sharing how past advice turned out: <strong>on</strong>" in page
    # says what is shared, in plain words ("the next export" read as jargon, 14 Oct)
    assert "a rough region and how the advice turned out" in page and "export" not in page
    assert 'name="share" value="no"' in page  # the button now turns it off


def test_sharing_needs_sign_in_and_a_yes_or_no(tmp_path):
    c, hist, auth = _accounts_client(tmp_path)
    r = c.post("/account/sharing", data={"share": "yes"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/auth/sign-in"
    _sign_in(c, auth)
    assert c.post("/account/sharing", data={"share": "maybe"}).status_code == 400
    assert hist.settings == {}


def test_a_cross_site_post_cannot_opt_someone_in(tmp_path):
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    r = c.post(
        "/account/sharing", data={"share": "yes"}, headers={"origin": "https://evil.example"}
    )
    assert r.status_code == 403 and hist.settings == {}


def test_back_only_goes_to_our_own_pages(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    r = c.post(
        "/account/sharing",
        data={"share": "no", "back": "https://evil.example/"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/"


def test_a_settings_outage_shows_the_home_page_without_the_ask(tmp_path, monkeypatch):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)

    def down(self):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "get_settings", down)
    r = c.get("/")
    assert r.status_code == 200 and ASK not in r.text
    assert "Sign out" in r.text and 'action="/analyse"' in r.text


def test_a_failed_save_says_history_is_down(tmp_path, monkeypatch):
    c, hist, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)

    def down(self, share, now):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "set_sharing", down)
    r = c.post("/account/sharing", data={"share": "yes"})
    assert r.status_code == 503 and remember.HISTORY_DOWN in r.text
    assert hist.settings == {}


def test_without_accounts_there_is_no_sharing(tmp_path):
    c = _client(tmp_path, [], [])
    assert c.post("/account/sharing", data={"share": "yes"}).status_code == 404
    assert ASK not in c.get("/").text


def test_the_consent_line_names_sharing(tmp_path):
    c, _, _ = _accounts_client(tmp_path)
    page = c.get("/auth/sign-in").text
    assert "Sharing how advice turned out is a separate yes or no" in page
    assert "never your photos" in page


def test_my_plants_still_shows_when_only_the_sharing_read_fails(tmp_path, monkeypatch):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)

    def down(self):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "get_settings", down)
    r = c.get("/plants")
    assert r.status_code == 200 and "My plants" in r.text
    assert "Sharing how past advice turned out" not in r.text
