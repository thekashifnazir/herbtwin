"""19 Oct full-site walk (the private working repo's `2026-10-19-judge-site-walk.md`), items 4, 6, 7, 9:
no delete form for nobody, no dead-end spot link from an indoor answer, a way back from a
missing page, and the same names everywhere."""

import re

import respx

from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.web.app import CHOICES, TEMPLATES
from tests.fakes import follow
from tests.test_web import _client
from tests.test_web_accounts import _accounts_client, _sign_in
from tests.test_web_answer_page import _unsure_record
from tests.test_web_spot import JPEG, _archive
from tests.test_web_spot import _client as _spot_client


def test_signed_out_the_delete_page_sends_you_to_sign_in(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    r = c.get("/account/delete", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/auth/sign-in"
    _sign_in(c, auth)
    page = c.get("/account/delete")
    assert page.status_code == 200 and 'action="/account/delete"' in page.text


def _answer(rec) -> str:
    return TEMPLATES.get_template("result.html").render(
        rec=rec, failed={}, asks=["question"], choices=CHOICES, max_question=500, chat=[],
        max_chat=500, check=None, reminder=None, compass_first="", spot_on=True,
        signed_in=False, accounts=False,
    )  # fmt: skip


def test_an_indoor_answer_does_not_offer_the_windowsill_spot(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.observation is not None
    link = f'href="/answers/{rec.record_id}/spot"'
    assert link not in _answer(rec)  # no place: no spot to tell about (judge walk of #272)
    from herbtwin.schemas import Location

    rec.location = Location(lat=51.5, lon=-0.12, source="home", label="London")
    rec.observation.setting = "outdoor"
    assert link in _answer(rec)
    rec.observation.setting = "indoor"
    assert link not in _answer(rec)


def test_a_missing_page_has_a_way_back(tmp_path):
    page = _client(tmp_path, [], []).get("/no-such-page")
    assert page.status_code == 404
    actions = page.text.split("<h1>Page not found</h1>", 1)[1].split("</div>", 1)[0]
    assert '<a class="button primary" href="/">Check a plant</a>' in actions
    assert 'href="/plants">My plants</a>' not in actions  # signed out: no My plants
    (tmp_path / "in").mkdir()
    c, _, auth = _accounts_client(tmp_path / "in")
    _sign_in(c, auth)
    actions = c.get("/no-such-page").text.split("<h1>Page not found</h1>", 1)[1].split("</div>")[0]
    assert '<a class="button" href="/plants">My plants</a>' in actions


def test_the_judge_samples_are_named_as_on_the_home_page(tmp_path):
    from tests.test_web_judge import CODE
    from tests.test_web_judge import _client as _judge_client

    home = _spot_client(tmp_path)[0].get("/").text
    chips = re.findall(
        r'data-sample="([^"]+)"[^>]*><picture>.*?<img [^>]*></picture><span>([^<]+)</span>', home
    )
    names = dict(chips)
    (tmp_path / "judge").mkdir()
    judge = _judge_client(tmp_path / "judge").post("/judge", data={"code": CODE}).text
    picks = re.findall(
        r'data-sample="([^"]+)"[^>]*>\s*<picture>.*?<img [^>]*></picture>\s*<span><strong>([^<]+)</strong>',
        judge,
    )
    assert picks
    for sample, name in picks:
        assert names.get(sample) == name, (sample, name)


@respx.mock
def test_the_spot_footer_says_ref_like_the_answers(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path)
    page = follow(c, c.post("/spots", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    climate._cache.clear()
    foot = page.split('<footer class="foot">', 1)[1]
    assert re.search(r'<span class="num">Ref [0-9a-f]{32}</span>', foot)
    assert ">record " not in foot
