"""The About page (21 Oct, Kash: "like my other hackathon projects"): why, what it does, how
it's built, the models, how we know it works, what didn't work, what's next, accessibility,
who made it, then the credits. /credits lands on its last section."""

import re
from pathlib import Path

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


def test_about_stays_short_and_links_the_details_on_the_public_repo(tmp_path):
    # 22 Oct site walk: About ran to 1,961 words, Kash's other About pages a few hundred.
    # The numbers stay; the long prose went to the reports on the public repo
    import html

    page = _spot_client(tmp_path)[0].get("/about").text
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    words = html.unescape(
        re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", main, flags=re.S))
    )
    # credits included; the story alone is about 1,100. 1,530 since the prices failure
    # joined What didn't work (22 Oct, Kash: keep it to show it wasn't working well)
    assert len(words.split()) <= 1530
    repo = "https://github.com/thekashifnazir/herbtwin/blob/main/"
    for doc in (
        "docs/reference/nvidia-models.md",
        "docs/reference/evaluation-methods.md",
        "data/eval/reports/2026-10-19-expert-review.md",
        "docs/reference/accessibility.md",
    ):
        assert f'href="{repo}{doc}"' in main, doc
    # the trusted-page check as it ships: round 8 (#395), not round 6's "backed nothing"
    assert "Round 8 shipped: 3 false agrees in 418" in main and "10 of the 26" in main
    for number in (
        "2%",
        "12.7%",
        "0.846",
        "0.63",
        "38 of 38",
        "25</strong> with",
        "51%",
        "$0.0040",
    ):
        assert number in main, number


def test_what_didnt_work_says_prices_failed_with_the_reports_numbers(tmp_path):
    # 22 Oct, Kash: "keep it in our testing to show it wasn't working well" (#434 hid prices;
    # data/eval/reports/2026-10-22-product-prices.md has the four probes)
    page = _about(tmp_path)
    section = page.split('<h2 id="didnt">', 1)[1].split("</section>", 1)[0]
    assert "<strong>Prices for the things to buy</strong>" in section
    # 22 Oct walk 2: "11 of 21 right, 9 wrong" added to 20; the report's one blank says it
    for said in ("11 of 21 right, 9 wrong and 1 left blank", "4 of 6 shops block", "not a price"):
        assert said in section, said
    story = (Path(__file__).parents[1] / "docs/submission/devpost.md").read_text("utf-8")
    assert "11 of\n  21 right, 9 wrong, 1 left blank;" in story


def test_about_gives_one_pass_figure_for_the_trusted_page_check(tmp_path, monkeypatch):
    # 22 Oct walk 2: the models list said "passed on the fifth round (4 false agrees in
    # 435)" while What didn't work said round 8 shipped at 3 in 418; it ships at round 8
    from herbtwin.web import app as web_app

    monkeypatch.setattr(web_app, "trusted_check_on", lambda settings: True)  # as live
    page = _spot_client(tmp_path)[0].get("/about").text
    models = page.split('id="made-with-h"', 1)[1].split("</section>", 1)[0]
    assert "Ultra checks a trusted page instead" in models
    assert "It shipped at round 8: 3 false agrees in 418" in models
    assert "4 false agrees in 435" not in page


def test_devpost_says_the_same_photo_can_read_differently_and_about_stays_short(tmp_path):
    # site walk 2 (22 Oct): r4 and r7 read the same coriander photo as "healthy" and as
    # "bolted"; the mildew pair had a different place set, so it is said not to be clean.
    # Devpost only: About was already flagged as too long (integrator, 22 Oct)
    story = (Path(__file__).parents[1] / "docs/submission/devpost.md").read_text("utf-8")
    flat = " ".join(story.split())
    assert "**The same photo can get a different read on another run.**" in flat
    assert '"looks healthy with no signs of stress"' in flat
    assert '"has bolted and is flowering"' in flat
    assert "That second pair is not a clean repeat" in flat
    assert "different read" not in _about(tmp_path)
