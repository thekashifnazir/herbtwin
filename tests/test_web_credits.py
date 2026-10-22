"""19 Oct small-print plan: one place for credits and models. Every licence credit stays
reachable from the page that shows the image (CC BY and BY-SA ask for that), and the rest
of the page loses the grey small print."""

import re
from pathlib import Path

from tests.test_web import _client
from tests.test_web_home import _credits, _home
from tests.test_web_spot import _client as _spot_client

LICENCES = {
    "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC BY 3.0 US": "https://creativecommons.org/licenses/by/3.0/us/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
}
AUTHORS = ["Johnathon Ridden", "Forest and Kim Starr", "Максим Шумских", "Ian Wolfe", "Kolforn"]


def test_credits_page_names_every_author_with_source_and_licence(tmp_path):
    # the credits are About's last section now (21 Oct); /credits lands on it
    page = _spot_client(tmp_path)[0].get("/credits")
    assert page.status_code == 200 and page.url.path == "/about"
    body = page.text.split('<section class="made-with about-credits" id="credits"', 1)[1]
    for author in AUTHORS:
        assert author in body, author
    for name, url in LICENCES.items():
        assert f'<a href="{url}" rel="noopener noreferrer">{name}</a>' in body, name
    assert "Qwen-Image-Edit" in body and "basil from Forest and Kim Starr's (CC BY 3.0 US)" in body
    assert "© UKRI" in body and "Open Government Licence" in body  # BGS, with the spot on
    models = page.text.split('id="made-with"', 1)[1].split("</section>", 1)[0]
    assert "Open-Meteo.com" in body and '<div class="made-groups">' in models
    assert "<strong>NVIDIA Nemotron 3 Super</strong>" in models


def test_every_page_links_about_and_credits_from_its_footer(tmp_path):
    c = _client(tmp_path, [], [])
    for path in ("/", "/privacy", "/about"):
        foot = c.get(path).text.split('<footer class="foot">', 1)[1]
        assert '<a href="/about">About</a>' in foot, path
        assert '<a href="/about#credits">Credits</a>' in foot, path


def test_each_image_group_on_home_links_to_the_credits_it_needs(tmp_path):
    home = _spot_client(tmp_path)[0].get("/").text
    # "Photo credits" by each group opens the fold (the pill's link went on 21 Oct)
    link = re.compile(r'<a class="credits-link" href="#credits">Photo credits</a>')
    twin = home.split('<figure class="home-twin">', 1)[1].split("</figure>", 1)[0]
    samples = home.split('<div class="home-chips"', 1)[1].split('<fieldset class="home-where">', 1)[
        0
    ]
    for group in (twin, samples):  # How it works and its pictures went (22 Oct walk)
        assert link.search(group)
    credits = _credits(home)
    for author in AUTHORS:  # the bed photo too: the spot answer is on here
        assert author in credits, author
    # the full credit lines left the groups: only the link stays by the pictures
    for group in (twin, samples):
        assert "CC BY" not in group and "Qwen-Image-Edit" not in group
    # a credits link opens the folded section (it starts closed)
    assert '<details class="made-credits" id="credits">' in home and "box.open = true" in home


def test_the_judge_page_says_the_no_script_way_only_without_script(tmp_path):
    from tests.test_web_judge import _client as _judge_client

    page = _judge_client(tmp_path).get("/judge").text
    said = page.split('id="judge-said"', 1)[1].split("</p>", 1)[0]
    assert "Without JavaScript" not in said
    assert "<noscript><p" in page and "Without JavaScript, a tap opens the photo" in page


def test_home_keeps_its_eligibility_line_in_view(tmp_path):
    home = _home(tmp_path)
    assert (
        "Decided by NVIDIA Nemotron 3 Super on Nebius Token Factory"
        in home.split('<details class="home-credits"', 1)[0]
    )


def test_the_judge_picks_link_their_photo_credits(tmp_path):
    from tests.test_web_judge import _client as _judge_client

    page = _judge_client(tmp_path).get("/judge").text
    picks = page.split('<div class="judge-picks">', 1)[1].split("</form>", 1)[0]
    after = page.split('<div class="judge-picks">', 1)[1].split('id="judge-said"', 1)[0]
    assert "Forest and Kim Starr" not in picks  # the credit lines live in one place
    assert '<a href="/about#credits">Photo credits</a>' in after


def test_credits_name_only_what_this_site_uses(tmp_path):
    plain = _client(tmp_path, [], []).get("/credits").text  # no spot answer, no voice
    assert "Kolforn" not in plain and "© UKRI" not in plain and "ElevenLabs" not in plain
    from herbtwin.web.app import TEMPLATES

    macro = TEMPLATES.env.get_template("_credits.html").module.made_with
    assert "ElevenLabs" in str(macro(voice_on=True)) and "ElevenLabs" not in str(macro())


def test_the_about_page_has_its_own_headings_and_the_credits_open_last(tmp_path):
    from herbtwin.web import style

    page = _client(tmp_path, [], []).get("/about").text
    levels = [int(n) for n in re.findall(r"<h([1-6])\b", page)]
    assert levels[0] == 1 and all(b <= a + 1 for a, b in zip(levels, levels[1:], strict=False))
    assert '<h2 id="made-with-h">The models, and what each does</h2>' in page
    credits = page.split('<section class="made-with about-credits" id="credits"', 1)[1]
    assert '<h2 id="credits-h">Credits</h2>' in credits and "<h3>Sample photos</h3>" in credits
    assert "<details" not in credits  # open on About, never folded
    assert "<section" not in credits  # the page's last section
    assert page.count('id="credits"') == 1 and page.count('id="made-with"') == 1
    assert ".made-with .made-credits { padding: 0 16px 16px; }" in style.CSS


def test_the_credits_say_what_changed_once_and_consistently(tmp_path):
    # 19 Oct re-check: "nothing else changed" above, "resized" on two lines below
    body = _spot_client(tmp_path)[0].get("/credits").text
    photos = body.split("<h3>Sample photos</h3>", 1)[1].split("<h3>", 1)[0]
    assert "All downscaled, with metadata removed." in photos
    assert "resized" not in photos


def test_notice_credits_every_sample_photo_the_site_serves():
    # 19 Oct export dry run: NOTICE said "five sample photos" and left out 7-pea-bed.jpg
    root = Path(__file__).resolve().parents[1]
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    served = sorted(
        p.name
        for p in (root / "src/herbtwin/web/static/samples").glob("*.jpg")
        if not p.stem.endswith("-thumb")
    )
    assert len(served) == 6
    assert "The same six sample photos" in notice
    credits = (root / "docs/judges/samples/CREDITS.md").read_text(encoding="utf-8")
    for name in served:
        assert f"`{name}`" in credits, name
    for author in AUTHORS:
        assert author in notice, author
    assert "CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/" in notice
    assert "Young_pea_plants,_Trimingham,_Norfolk.JPG" in notice
