"""The About page (21 Oct, Kash: "like my other hackathon projects"): why, what it does, how
it's built, the models, how we know it works, what didn't work, what's next, accessibility,
who made it, then the credits. /credits lands on its last section."""

import re

from herbtwin.web import style
from tests.test_web import _client
from tests.test_web_spot import _client as _spot_client

SECTIONS = [
    "herbtwin, and why I built it",
    "What it does",
    "How it's built",
    "The models, and what each does",
    "How I know it works",
    "What didn't work",
    "What's next",
    "Accessibility",
    "Who made it",
    "Credits",
]


def _about(tmp_path) -> str:
    r = _client(tmp_path, [], []).get("/about")
    assert r.status_code == 200
    return r.text


def test_about_tells_the_story_in_its_sections_in_order(tmp_path):
    page = _about(tmp_path)
    heads = re.findall(r'<h2 id="[^"]+">([^<]+)</h2>', page)
    assert heads == SECTIONS
    assert "<h1>About herbtwin</h1>" in page
    assert "<title>About · herbtwin</title>" in page


def test_the_nav_and_the_footer_link_about_and_mark_it_on_its_page(tmp_path):
    c = _client(tmp_path, [], [])
    for path in ("/", "/privacy"):
        nav = c.get(path).text.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
        assert '<li><a href="/about">About</a></li>' in nav, path
    nav = _about(tmp_path).split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
    assert '<a href="/about" aria-current="page">About</a>' in nav


def test_old_credits_links_land_on_the_credits_section(tmp_path):
    r = _client(tmp_path, [], []).get("/credits", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/about#credits"


def test_the_answers_example_cost_is_labelled_one_example_and_an_estimate(tmp_path):
    page = _about(tmp_path)
    cost = page.split('<div class="about-receipt">', 1)[1].split("</div>", 1)[0]
    assert "<strong>$0.0040</strong>" in cost and "<strong>about $0.0177</strong>" in cost
    assert "One example, not an average." in cost
    assert "the same tokens at Ultra's listed price" in cost


def test_the_about_page_has_one_main_button_and_nothing_private(tmp_path):
    r = _spot_client(tmp_path)[0].get("/about")
    assert r.status_code == 200 and "<h1>About herbtwin</h1>" in r.text
    page = r.text
    main = page.split('<main id="content"', 1)[1].split("</main>", 1)[0]
    assert len(re.findall(r'class="[^"]*\bprimary\b|id="next"', main)) == 1
    assert '<a class="button primary" href="/">Check a plant</a>' in main
    assert "great" + "agent" not in page.lower()  # spelled split, as the export test does
    assert "/answers/" not in page and "/judge" not in main
    # pictures: only the openly licensed sample thumbnails
    assert all(s.startswith("/static/samples/") for s in re.findall(r'<img src="([^"]+)"', main))


def test_nothing_on_the_about_page_or_in_made_with_is_under_16px():
    rules = re.findall(r"\.(?:about-page|made-with|made-group)[^{]*\{[^}]*\}", style.CSS)
    sizes = [int(px) for r in rules for px in re.findall(r"font(?:-size)?:[^;]*?(\d+)px", r)]
    assert len(rules) > 20 and sizes and min(sizes) >= 16
    about = style.CSS.split(".about-page .about-stats {", 1)[1]
    assert "→" not in style.CSS and "↓" not in style.CSS  # the arrows are escapes, not text
    assert '.about-page .about-flow li + li::before { content: "\\2192" / "";' in about
