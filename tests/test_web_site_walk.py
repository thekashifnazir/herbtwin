"""The 17 Oct site walk (the private working repo's `2026-10-17-chore-phone-a11y-pass.md`): a skip link
and a chevron on every page, the home page saying what its own example shows, crop links a
screen reader can tell apart, the spot sun row saying when it is a guess, and the 404,
unsubscribe and privacy wording matching what the site does."""

import json
import re

import pytest
import respx

from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.web import accounts, judge
from herbtwin.web.app import NO_REMINDERS, NOT_FOUND
from herbtwin.web.progress import HEAD, SIGNED_OUT_HEAD, SPOT_HEAD
from tests.fakes import follow
from tests.test_web import ADV, OBS, _client
from tests.test_web_reminders import _client as _reminder_client
from tests.test_web_spot import JPEG, WALLED, _archive
from tests.test_web_spot import _client as _spot_client


def _home(tmp_path):
    return _client(tmp_path, [], []).get("/").text


def _rule(page, selector):
    """the declarations of one rule in the sheet the page itself carries"""
    sheet = page.split("<style>", 1)[1].split("</style>", 1)[0]
    found = re.search(re.escape(selector) + r" ?\{([^}]*)\}", sheet)
    assert found, selector
    return found.group(1)


def test_every_page_starts_with_a_skip_link_to_the_content(tmp_path):
    c = _client(tmp_path, [], [])
    pages = [c.get(p, headers={"accept": "text/html"}).text for p in ("/", "/privacy", "/x")]
    for page in [*pages, HEAD, SIGNED_OUT_HEAD, SPOT_HEAD]:  # the progress page is not Jinja
        body = page.split("<body", 1)[1]
        skip = body.index('<a class="skip" href="#content">Skip to content</a>')
        target = re.search(r'<main[^>]* id="content" tabindex="-1">', body)
        assert target and skip < body.index("<header") < target.start()
        assert body.count('id="content"') == 1
        assert "top: -100px" in _rule(page, ".skip") and "top: 8px" in _rule(page, ".skip:focus")


def test_the_home_headings_never_skip_a_level(tmp_path):
    # the example card's plant name was an h3 straight after the h1
    levels = [int(n) for n in re.findall(r"<h([1-6])\b", _home(tmp_path))]
    assert levels[0] == 1
    assert all(b <= a + 1 for a, b in zip(levels, levels[1:], strict=False)), levels


def test_the_model_line_names_every_model(tmp_path):
    home = _home(tmp_path)
    line = home.split('<section class="made-with" id="made-with"', 1)[1].split("</section>")[0]
    named = ["GLM-5.3-Flash", "a backup model", "Nemotron 3 Super", "Nemotron 3 Nano"]
    assert all(n in line for n in named) and "asked 3 times" in line


def test_the_example_card_and_its_factors_agree_on_pot_or_ground(tmp_path):
    page = _home(tmp_path)
    card = page.split('aria-label="Example answer"', 1)[1].split("</article>", 1)[0]
    assert not ("in a pot" in card and "Pot or ground unknown" in page)


def test_sample_3_is_named_for_what_the_photo_shows(tmp_path):
    # the app reads it as basil starting to flower (its source calls the faint marks early
    # downy mildew, which the problem-check eval keeps); the file name stays, the evals use it
    tile = (
        _home(tmp_path).split('data-sample="3-basil-yellow-leaves.jpg"', 1)[1].split("</a>", 1)[0]
    )
    assert "<span>Basil flowering</span>" in tile
    assert (
        "yellow" not in re.sub(r'src(set)?="[^"]*"', "", tile).lower()
    )  # only the file names keep it


def test_sample_chips_carry_a_round_thumbnail_and_a_label(tmp_path):
    # 19 Oct home pass: the big captioned tiles became chips under the photo card
    rule = _rule(_home(tmp_path), ".home-page .home-pick img")
    assert "border-radius: 50%" in rule and "width: 40px" in rule


def test_every_fold_shows_it_opens(tmp_path):
    # summary is display:flex, which drops the browser's own triangle
    page = _home(tmp_path)
    assert "<summary>Data and photo credits" in page
    assert "display: none" in _rule(page, "summary::-webkit-details-marker")
    assert 'content: ""' in _rule(page, "summary::after")
    assert "rotate(-135deg)" in _rule(page, "details[open] > summary::after")


@respx.mock
def test_crop_links_name_the_crop_and_the_new_tab(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path, observe=[json.dumps(WALLED)])
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    links = re.findall(
        r'<a class="src"[^>]*aria-label="([^"]+) on ([^"]+) \(opens in a new tab\)">([^<]+)</a>',
        page,
    )
    assert links and len(links) == page.count('<a class="src"')
    assert all(crop and host == shown for crop, host, shown in links)
    assert len({crop for crop, _, _ in links}) == len(
        links
    )  # one name per link, not "rhs.org.uk" each
    climate._cache.clear()


@respx.mock
def test_the_sun_row_says_summer_and_says_when_it_is_a_guess(tmp_path):
    # 17 Oct: "Full sun, give or take" sat above "No direct sun from November to January"
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path, observe=[json.dumps(WALLED)])
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    row = page.text.split("<dt>Sun</dt>", 1)[1].split("</dd>", 1)[0]
    assert " in summer" in row and ">a guess until you say which way it faces</a>" in row
    rid = page.url.path.rsplit("/", 1)[1]
    picked = c.post(f"/spots/{rid}/told", data={"direction": "S"}).text
    row = picked.split("<dt>Sun</dt>", 1)[1].split("</dd>", 1)[0]
    assert " in summer" in row and "a guess" not in row and ">which way does it face?</a>" in row
    climate._cache.clear()


@respx.mock
def test_a_spot_answer_announces_the_update_after_a_reload(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path, observe=[json.dumps(WALLED)])
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    assert '<p class="note told-said" id="told-said" role="status" tabindex="-1"></p>' in page
    script = page.split('const KEY = "herbtwin-spot-told"', 1)[1].split("</script>", 1)[0]
    assert 'form[action$="/told"]' in script and "Updated with what you told us." in script
    assert "said.focus()" in script
    assert "Date.now() - was.t > 15000" in script  # a stale flag from a failed post stays quiet
    assert "display: none" in _rule(page, ".spot-page .told-said:empty")  # no empty box before
    climate._cache.clear()


def test_the_missing_page_only_points_at_what_the_menu_has(tmp_path):
    # the menu has "Check a plant" (and "My plants"); growing starts from a photo on home
    page = _client(tmp_path, [], []).get("/no-such-page", headers={"accept": "text/html"}).text
    nav = page.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
    assert ">Check a plant</a>" in nav and "grow" not in nav.lower()
    assert "menu above to check a plant or see what you can grow" not in NOT_FOUND
    assert "Check a plant from the menu above" in NOT_FOUND


def test_an_unsubscribe_link_with_reminders_off_does_not_talk_about_answers(tmp_path):
    c, _ = _reminder_client(tmp_path, secret=None)
    for r in (
        c.get("/reminders/unsubscribe", params={"a": "a" * 32, "t": "x"}),
        c.post("/reminders/unsubscribe", data={"a": "a" * 32, "t": "x"}),
    ):
        assert r.status_code == 404
        assert "Reminder emails are off on this site" in r.text and "upload the photo" not in r.text
    assert "answer" not in NO_REMINDERS


def test_the_privacy_page_lists_the_cookies_as_the_code_sets_them(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    cookies = page.split("<h2>Cookies</h2>", 1)[1].split("<h2>", 1)[0]
    assert accounts.REFRESH_DAYS == 30 and "one for an hour" in cookies and "30 days" in cookies
    assert judge.MAX_AGE == 60 * 86400 and "60 days" in cookies
    assert "sets no cookies" in cookies


def test_the_privacy_page_names_open_plantbook(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    assert "<strong>Open Plantbook</strong> gets the plant's name" in page


def test_the_progress_page_promises_what_a_read_takes():
    # judges read "about half a minute" in the story, then "a couple of minutes" here; the
    # slow-read timer (SLOW_S) already explains a longer wait when one happens
    for head in (HEAD, SIGNED_OUT_HEAD, SPOT_HEAD):
        assert '<p class="lead">Usually under a minute. Keep this page open.</p>' in head
        assert "couple of minutes" not in head


@pytest.mark.usefixtures("open_meteo_down")
def test_signed_out_the_working_page_never_points_at_my_plants(tmp_path):
    # 18 Oct judge walk: signed out, the page said "find it in My plants", which a
    # signed-out visitor has not got; the same photo again replays the finished answer
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    first = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert 'href="/plants"' not in first and "My plants" not in first
    assert "Send the same photo again in a few minutes" in first
    (tmp_path / "in").mkdir()
    c2, _ = _reminder_client(tmp_path / "in")
    signed_in = c2.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert 'find it in <a href="/plants">My plants</a>' in signed_in


def test_the_judges_notes_match_the_menu_and_say_answers_follow_the_weather():
    # 18 Oct judge walk: JUDGES.md sent judges to "What can I grow here?" in the top menu,
    # which has never had it; and the basil sample's answer changed with the week's weather
    from pathlib import Path

    notes = Path(__file__).parents[1].joinpath("JUDGES.md").read_text()
    nav = Path(__file__).parents[1].joinpath("src/herbtwin/web/templates/_nav.html").read_text()
    assert "What can I grow here" not in nav
    # 23 Oct: the answer is switched off, so the notes say so rather than say where it is
    assert "from the menu at the top" not in notes and "switched off on the live" in notes
    assert "Answers change with the date and the weather." in notes
