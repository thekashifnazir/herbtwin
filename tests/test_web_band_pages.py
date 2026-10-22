"""Judges, sign-in and privacy open on the green band, as About, My plants and the answer do
(22 Oct site walk: they were plain pages, and /judge, the judges' first page, was mostly
empty at 1300px). The band comes first, and each page has one primary button."""

import re

from herbtwin.web import style
from tests.test_web import _client
from tests.test_web_accounts import _accounts_client
from tests.test_web_judge import CODE
from tests.test_web_judge import _client as _judge_client


def _main(page: str) -> str:
    return page.split("<main", 1)[1].split("</main>", 1)[0]


def _on_the_band(page: str, page_class: str, first_after: str) -> None:
    assert f'<body class="{page_class} has-band">' in page
    main = _main(page)
    assert main.index('<div class="page-band">') < main.index(first_after)
    assert len(re.findall(r'class="[^"]*\bprimary\b', main)) == 1  # one thing to press


def test_judge_opens_on_the_band_with_the_code_card_over_its_edge(tmp_path):
    page = _judge_client(tmp_path).get("/judge").text
    _on_the_band(page, "judge-page", 'name="code"')
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert "<h1>Judges</h1>" in band and "Enter the judges' code" in band
    assert '<form method="post" action="/judge" class="card ink band-overlap judge-code">' in page
    assert '<button class="primary" type="submit">Use code</button>' in page
    assert '<div class="wrap wide">' in page  # the samples get the frame's width
    assert (
        ".judge-page .judge-picks { grid-template-columns: repeat(2, minmax(0, 1fr)); }"
        in style.CSS
    )


def test_judge_in_puts_the_way_on_on_the_band(tmp_path):
    page = _judge_client(tmp_path).post("/judge", data={"code": CODE}).text
    _on_the_band(page, "judge-page", "Or a quick look: one tap each")
    band = page.split('<div class="page-band">', 1)[1].split('<section class="judge-start"', 1)[0]
    assert "You're in." in band and '<a class="button primary" href="/">' in band  # lime


def test_judge_blocked_says_so_on_the_band_with_no_form(tmp_path):
    c = _judge_client(tmp_path)
    for _ in range(10):
        c.post("/judge", data={"code": "nope"})
    page = c.post("/judge", data={"code": CODE}).text
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert "Too many tries today" in band and 'name="code"' not in page


def test_sign_in_opens_on_the_band_with_the_email_card_over_its_edge(tmp_path):
    c, _, _ = _accounts_client(tmp_path)
    page = c.get("/auth/sign-in").text
    _on_the_band(page, "sign-in-page", 'name="email"')
    assert '<form method="post" action="/auth/sign-in" class="card ink band-overlap">' in page
    # the wrap that holds a band is full width: what follows keeps the reading column
    assert ":is(.sign-in-page, .privacy-page) .page-band ~ * { max-width: var(--measure); }" in (
        style.CSS
    )


def test_the_emailed_link_page_has_its_button_on_the_band(tmp_path):
    c, _, _ = _accounts_client(tmp_path)
    page = c.get("/auth/callback?token_hash=abc&type=email").text
    _on_the_band(page, "sign-in-page", 'action="/auth/callback"')
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert '<button class="button primary big" type="submit">Sign in</button>' in band


def test_privacy_opens_on_the_band_and_says_what_to_do_next(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    _on_the_band(page, "privacy-page", "<h2>What is kept</h2>")
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert "<h1>Privacy</h1>" in band and 'class="lead"' in band
    assert '<a class="button primary" href="/">Check a plant</a>' in band
