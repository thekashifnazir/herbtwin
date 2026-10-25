"""The About page (21 Oct, Kash: "like my other hackathon projects"): why, what it does, how
it's built, the models, how we know it works, what didn't work, what's next, accessibility,
who made it, then the credits. /credits lands on its last section."""

import html
import re
from pathlib import Path

from herbtwin.web import style
from tests.test_web import _client
from tests.test_web_spot import _client as _spot_client

SECTIONS = [
    "How it's built",
    "How I know it works",
    "What didn't work",
    "What's next",
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
    # the sibling pages' title (22 Oct): the band and the "why" are one, not a band then a repeat
    assert "<h1>herbtwin, and why I built it</h1>" in page and page.count("why I built it") == 1
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
    cost = page.split('<div class="about-receipt about-card ink">', 1)[1].split("</div>", 1)[0]
    assert "<strong>$0.0040</strong>" in cost and "<strong>about $0.0177</strong>" in cost
    assert "One example, not an average." in cost
    assert "the same tokens at Ultra's listed price" in cost


def test_the_about_page_has_one_main_button_and_nothing_private(tmp_path):
    r = _spot_client(tmp_path)[0].get("/about")
    assert r.status_code == 200 and "<h1>herbtwin, and why I built it</h1>" in r.text
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
    assert "→" not in style.CSS and "↓" not in style.CSS  # any arrow is an escape, not text


def test_about_stays_short_and_links_the_details_on_the_public_repo(tmp_path, monkeypatch):
    # 22 Oct site walk: About ran to 1,961 words, Kash's other About pages a few hundred.
    # The numbers stay; the long prose went to the reports on the public repo
    import html

    from herbtwin.web import app as web_app

    # counted as live, with the trusted-page check on (22 Oct: the diagrams' labels count) and
    # "What can I grow here?" off, as it is live since 23 Oct (#515)
    monkeypatch.setattr(web_app, "trusted_check_on", lambda settings: True)
    page = _spot_client(tmp_path, spot=False)[0].get("/about").text
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    # what a reader sees: the credits are folded shut (round 2, Kash: "as we do for the home
    # page"), so their ~300 words count only once opened, as on home (22 Oct, round 3)
    shown = re.sub(
        r'<details class="made-credits" id="credits">.*?</details>', "", main, flags=re.S
    )
    assert shown != main
    words = html.unescape(
        re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", shown, flags=re.S))
    )
    # one rule (22 Oct, round 3 joined): the words shown on load, capped at what the four
    # round-3 sections measured together (1,469) plus about 40; grow it only on purpose
    # one rule: the words shown on load, capped at the measured total plus about 40. Grown on
    # purpose on 23 Oct, from 1,560 (1,522 measured) to 1,620 (1,586), for Kash's "Checked by
    # people": Tendem, the 11 Oct Toloka pilot and the next study. Grown on purpose on 25 Oct,
    # to 1,760 (1,721 measured, as live), for Kash's "What each service did" panel, with
    # "What it does" gone
    assert len(words.split()) <= 1760
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
        "<strong>25 vs 15</strong>",
        "51%",
        "$0.0040",
    ):
        assert number in main, number


def test_what_didnt_work_says_prices_failed_with_the_reports_numbers(tmp_path):
    # 22 Oct, Kash: "keep it in our testing to show it wasn't working well" (#434 hid prices;
    # data/eval/reports/2026-10-22-product-prices.md has the four probes)
    page = _about(tmp_path)
    section = page.split('<h2 id="didnt">', 1)[1].split("</section>", 1)[0]
    assert "<strong>Shops don't give prices to robots.</strong>" in section
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
    works = page.split('<h2 id="works">', 1)[1].split("</section>", 1)[0]
    assert "Trusted-page check, round 8: 3 false agrees in 418" in works
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


def _flows(tmp_path, check_on: bool, monkeypatch) -> tuple[str, str, str]:
    from herbtwin.web import app as web_app

    monkeypatch.setattr(web_app, "trusted_check_on", lambda settings: check_on)
    page = _spot_client(tmp_path)[0].get("/about").text
    built = page.split('<h2 id="built">', 1)[1].split("</section>", 1)[0]
    works = page.split('<h2 id="works">', 1)[1].split("</section>", 1)[0]
    return page, built, works


def test_how_its_built_is_the_stack_then_one_coloured_flow(tmp_path, monkeypatch):
    # 22 Oct, Kash: "still very claude coded on this page rather than sticking to more of our
    # design language and where is the colour". The sibling pages' shape (a row of the stack,
    # then one drawn flow in a framed panel) in herbtwin's language: one list of steps, left
    # to right on a wide screen and one under another on a phone, the boxes home's sticker
    # tiles coloured by what they are
    _, built, _ = _flows(tmp_path, True, monkeypatch)
    chips = built.split('<ul class="about-chips"', 1)[1].split("</ul>", 1)[0]
    for name in (
        "Python 3.12",
        "FastAPI",
        "Cloud Run",
        "Cloudflare Worker",
        "Nebius Token Factory",
        "NVIDIA Nemotron 3",
        "Tavily",
        "Open-Meteo",
        "GBIF",
        "Supabase",
    ):
        # round 3 (22 Oct): a source's chip carries its colour class
        assert re.search(rf'<li(?: class="[a-z]+")?>{name}</li>', chips), name
    flow = built.split('<ol class="flow-built"', 1)[1].split("</figure>", 1)[0]
    # eight steps (round 3: our rules in the main row, the weather a step of its own), then
    # what hangs off the answer in a row of its own
    assert '<div class="flow-under">' in flow
    steps = re.findall(r"\n      <li[ >]", flow.split('<div class="flow-under">', 1)[0])
    assert len(steps) == 8
    # the numbers the flow states come from the code that does them
    from herbtwin.pipeline import HOLD_WATER_DAYS
    from herbtwin.sightings import WINDOW_DAYS
    from herbtwin.stages.observe import HEDGE_AFTER_S

    assert f"races it after {HEDGE_AFTER_S:g} s" in flow
    assert f"the last {WINDOW_DAYS} days" in flow and f"× {HOLD_WATER_DAYS} days" in flow
    assert "code quotes it only if it backs the answer" in flow
    for said in (
        "<strong>Read the photo</strong><em>GLM-5.3-Flash</em>",
        "DeepSeek V4.1 Flash races it after 14 s",
        "e.g. 17.4 s · $0.0016",
        '<div class="node weather">',
        "<em>Open-Meteo</em>",
        '<div class="node twin">',
        "6 choices × 14 days, each one tried",
        '<div class="node advisors">',
        "3 × NVIDIA Nemotron 3 Super",
        "e.g. 6.0 s · $0.0024",
        '<div class="node rules">',
        "Nemotron says water, but nothing looks dry and the twin sees no dry day ahead: leave it.",
        '<div class="node answer ink">',
        '<svg class="face content"',
        "$0.0040 of model time, one example",
        "NVIDIA Nemotron 3 Nano, with Tavily search",
        "NVIDIA Nemotron 3 Ultra reads a page",
        "GBIF pest sightings, the last 60 days",
        '<div class="node later">',
    ):
        assert said in flow, said
    # one green path: the arrows into the twin and the advisors
    assert flow.count('<li class="acc">') == 2 and flow.count('<li class="turn">') == 1
    assert "<figcaption>" in built and '<i class="sw later"></i>not built yet' in built
    css = style.CSS
    assert ".about-page .node.twin { background: var(--band); color: var(--band-fg); }" in css
    assert ".about-page .node.weather { background: var(--sky); }" in css
    assert ".about-page .node.advisors { background: var(--soft); }" in css
    assert ".about-page .node.rules { background: var(--warn-bg);" in css
    # theme tokens only, so dark mode follows; the lime is the band's one button, never a box
    rules = re.findall(r"\.about-page [^{]*\{[^}]*\}", css)
    assert not any(re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(", r) for r in rules)
    assert not any("--lime" in r for r in rules)


def test_the_trusted_page_box_shows_only_where_the_check_runs(tmp_path, monkeypatch):
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()
    _, on, _ = _flows(tmp_path / "on", True, monkeypatch)
    _, off, _ = _flows(tmp_path / "off", False, monkeypatch)
    assert "<strong>Trusted-page check</strong>" in on and "Trusted-page check" not in off


def test_how_i_know_it_works_is_a_flow_that_ships_or_fails(tmp_path, monkeypatch):
    # round 3 (22 Oct, Kash: "fix the test-flow diagram for sure"): the fork sat in a fourth
    # column, two boxes tall, leaving a big gap under the three steps. Now the steps fill one
    # row and the fork takes the whole row under them, If it passes / If it fails
    _, _, works = _flows(tmp_path, True, monkeypatch)
    flow = works.split('<ol class="works-flow"', 1)[1].split("</ol>", 1)[0]
    assert (
        flow.count('<li class="step">') == 3
        and flow.count('<li class="fork" data-reveal="stagger">') == 1
    )
    fork = flow.split('<li class="fork" data-reveal="stagger">', 1)[1]
    assert fork.count('<div class="branch">') == 2
    for said in (
        "Write the test down first",
        "Run it on held-out data",
        "Label it blind",
        "Trusted-page rounds: 2 labellers, yes only if both agree",
    ):
        assert said in flow.split('<li class="fork" data-reveal="stagger">', 1)[0], said
    for said in (
        '<p class="flow-by">If it passes</p><div class="node advisors"><strong>It ships</strong>',
        "round 8: 3 false agrees in 418",
        '<p class="flow-by">If it fails</p><div class="node rules"><strong>What didn\'t work</strong>',
        "specialist advisors (774 questions)",
    ):
        assert said in fork, said
    css = style.CSS
    assert "grid-template-columns: repeat(3, minmax(0, 1fr)); }" in css
    assert ".about-page .works-flow > .fork { grid-column: 1 / -1;" in css
    # bigger text than round 2's 16px and 17px
    body = re.search(r"\.about-page \.works-flow \.node \{[^}]*font-size: (\d+)px", css)
    head = re.search(r"\.about-page \.works-flow \.node strong \{ font: 700 (\d+)px", css)
    assert int(body[1]) >= 18 and int(head[1]) >= 20


# the question cards, in order: (colour, question, the answer's number, its bars as
# (label, value as written, bar width %), its yardstick line or None). Every number is the one
# the results (docs/reference/results.md, nvidia-models.md, soil-area-and-what-to-grow.md) give
CARDS = [
    (
        "advisors",
        "Is the advice safe?",
        "2%",
        [
            ("Nemotron 3 Super, the one we use", "2%", 13.3),
            ("Nemotron 3 Nano", "7.3%", 48.7),
            ("Nemotron 3 Ultra", "12.7%", 84.7),
        ],
        None,
    ),
    (
        "advisors",
        "Does it agree with experts?",
        "0.43 · 0.41",
        [
            ("150 Stack Exchange questions", "0.43", 43),
            ("200 from MIRAGE, a plant-care benchmark", "0.41", 41),
        ],
        "About 0.8 is the ceiling: a hand check agreed with the expert's action",
    ),
    (
        "advisors",
        "Does it know when it's unsure?",
        "63%",
        [("herbtwin's confidence", "63%", 63)],
        "50% is a coin flip.",
    ),
    (
        "photo",
        "Does it read the plant right?",
        "0.846",
        [
            ("GLM-5.3-Flash, the one we use", "0.846", 84.6),
            ("Nemotron 3.5 Super VL, the best NVIDIA model we tried", "0.627", 62.7),
        ],
        None,
    ),
    ("photo", "Does it notice what you did?", "38 of 38", [], None),
    (
        "tavily",
        "Does Tavily search help?",
        "25 vs 15",
        [("With Tavily search", "25 of 30", 83.3), ("Without", "15 of 30", 50)],
        None,
    ),
    (
        "wide",
        'Does "What can I grow here?" work?',
        "0.90",
        [("In our top two lists", "0.90", 90)],
        "0.85 was the pass bar.",
    ),
]

BAR = re.compile(
    r'<li(?: class="ours")?><span>([^<]+)</span><span class="val">([^<]+)</span>'
    r'<span class="bar" aria-hidden="true"><i style="width: ([\d.]+)%"></i>'
)


def _cards(works: str) -> list[str]:
    cards = works.split('<ul class="works-cards"', 1)[1]
    return re.split(r'<li class="works-card ', cards)[1:]


def test_the_results_are_the_questions_they_answer_with_fair_bars(tmp_path, monkeypatch):
    # round 3 (22 Oct, Kash: yes): the 8 number tiles became 7 questions, each answered in a
    # number and, where the comparison is fair, small bars. Each value is written beside its
    # bar, so a screen reader hears "Nemotron 3 Nano 7.3%" and the bar is only a picture
    page, _, works = _flows(tmp_path, True, monkeypatch)
    import html

    assert "about-tiles" not in works and "<table" not in page
    cards = _cards(works)
    assert len(cards) == len(CARDS)
    for card, (colour, question, number, bars, key) in zip(cards, CARDS, strict=True):
        card = html.unescape(card)
        assert card.startswith(f"{colour} ink"), question
        assert f"<h4>{question}</h4>" in card
        assert f'<p class="answer"><strong>{number}</strong>' in card, question
        assert [(w, v, float(x)) for w, v, x in BAR.findall(card)] == bars, question
        if key:
            assert '<i class="mk" aria-hidden="true"></i><span>' + key in card, question
        else:
            assert 'class="mark"' not in card, question
    # a bar is drawn to its value: one scale within a card
    for _, question, _, bars, _ in CARDS:
        scales = {round(x / float(v.split()[0].rstrip("%")), 1) for _, v, x in bars}
        assert len(scales) <= 1, (question, scales)


def test_the_question_cards_have_their_own_heading_under_the_flow(tmp_path, monkeypatch):
    # round 4 (22 Oct, Kash: the cards "look great! but need a heading for this section"): a
    # heading between the test flow and the cards names the list, and each question sits a
    # level under it
    _, _, works = _flows(tmp_path, True, monkeypatch)
    after_flow = works.split("</figure>", 1)[1]
    assert after_flow.lstrip().startswith(
        '<h3 class="works-head" id="works-results">What the tests found</h3>\n'
        '  <ul class="works-cards" aria-labelledby="works-results">'
    )
    assert works.count("<h4>") == 7 and "<h3>" not in after_flow
    assert ".about-page .about h3.works-head {" in style.CSS


def test_the_ceiling_is_named_for_what_it_is(tmp_path, monkeypatch):
    # 0.8 is how often a hand check agreed with the expert action we extracted (results.md),
    # not how often experts agree with each other; and the marks sit where the lines say
    _, _, works = _flows(tmp_path, True, monkeypatch)
    cards = _cards(works)
    assert cards[1].count('<b class="mark" style="left: 80%">') == 2
    assert cards[2].count('<b class="mark" style="left: 50%">') == 1
    assert cards[6].count('<b class="mark" style="left: 85%">') == 1
    assert "with each other" not in works
    # the sets as the reports count them: GLM scored 149 of the same 150 photos, and 461 is the
    # RHS picks that fit the setting (597 in all; 2026-10-12-grow.summary.json)
    assert "The same 150 GBIF photos of 15 kinds (GLM: 1 failed)" in cards[3]
    assert "415 of the 461 RHS picks that fit the setting" in cards[6]


def test_without_the_spot_feature_the_grow_card_goes(tmp_path):
    page = _about(tmp_path)  # spot off
    works = page.split('<h2 id="works">', 1)[1].split("</section>", 1)[0]
    assert "What can I grow here?" not in works and len(_cards(works)) == 6


def test_who_made_it_is_kashs_own_bio_and_ends_on_the_public_repo(tmp_path):
    page = _about(tmp_path)
    who = page.split('<h2 id="who">', 1)[1].split("</section>", 1)[0]
    # round 4: Moveset's voice (22 Oct, Kash: "the Moveset who made it is much better"); the
    # 23 Oct layout moved the name, role and event into the facts and kept his words
    for said in (
        "One idea, one person, built end to end.",
        "Senior Technical Architect, London",
        "I attended its London event.",
        "herbtwin inverts that.",
        "because it is the reason this exists at all",
        "I've never been a career developer",
        "The architecture and the judgement calls are mine.",
        '<a href="https://kashifnazir.com" rel="noopener noreferrer">kashifnazir.com</a>',
    ):
        assert said in who, said
    assert '<a class="button" href="https://github.com/thekashifnazir/herbtwin"' in who


def test_round_two_colours_every_source_and_says_what_each_colour_means(tmp_path, monkeypatch):
    # 22 Oct, Kash on round 1: "Tavily isn't made clear in colour like the others", and "under
    # the answer same issue". Each source has its colour, in the flow, the tiles and the cards,
    # and the legend names them all; Tavily and GBIF boxes carry a tag too
    page, built, works = _flows(tmp_path, True, monkeypatch)
    assert (
        # the problem check is the photo model's call; Tavily only finds how to treat what
        # it names, so the box is the photo model's grey with a Tavily tag (22 Oct review)
        '<div class="node photo"><i class="tag">Tavily</i><strong>If a problem shows</strong>'
        in built
    )
    assert '<div class="node photo">' in built
    under = built.split('<div class="flow-under">', 1)[1].split("</div>", 1)[0]
    assert (
        under.count('<i class="tag">Tavily</i>') == 3
        and '<li class="gbif"><i class="tag">GBIF</i>' in under
    )
    assert '<li class="tavily"><i class="tag">Tavily</i><strong>Shops, gardeners</strong>' in under
    # round 3 (22 Oct, Kash: "Shrink the legend to 3 items"): the stack's chips carry the
    # sources' colours, and the legend keeps what no chip says
    chips = built.split('<ul class="about-chips"', 1)[1].split("</ul>", 1)[0]
    for colour, name in (("nvidia", "NVIDIA Nemotron 3"), ("tavily", "Tavily"), ("gbif", "GBIF")):
        assert f'<li class="{colour}">{name}</li>' in chips, name
    key = built.split('<ul class="flow-key"', 1)[1].split("</ul>", 1)[0]
    for swatch, said in (("plain", "you, our notes, the answer"), ("later", "not built yet")):
        assert f'<i class="sw {swatch}"></i>{said}' in key, swatch
    css = style.CSS
    assert (
        "--lilac: #EEE8F7; --lilac-fg: #5B3F8F;" in css
        and "--lilac: #251E33; --lilac-fg: #C4B2EE;" in css
    )


def test_round_two_turns_the_long_text_into_cards(tmp_path):
    # Kash: "just not helpful"; the "All of it is public" card ("like this!") is the model
    page = _about(tmp_path)
    # (round 4 turned What didn't work and What's next out of cards again: see below)
    assert page.count('<blockquote class="about-card quote ink">') == 2
    css = style.CSS
    assert (
        ".about-page .about-card:is(.about-close, .about-receipt) { background: var(--soft); }"
        in css
    )
    assert ".about-page .about-two { display: grid;" in css


def test_the_credits_are_folded_and_a_credits_link_opens_them(tmp_path):
    # Kash: "do same for credits as we do for the home page instead of out so it's hidden away"
    page = _about(tmp_path)
    credits = page.split('<h2 id="credits-h">Credits</h2>', 1)[1]
    assert credits.lstrip().startswith('<details class="made-credits" id="credits">')
    assert '<details class="made-credits" id="credits" open' not in page
    assert (
        'if (location.hash === "#credits") document.getElementById("credits").open = true;' in page
    )


def test_the_palette_tints_each_kind_of_box_and_card():
    # one palette for the flow, the legend, the tiles and the cards; a dropped tint shows here
    css = style.CSS
    for rule in (
        ".about-page .under li.advisors { background: var(--soft); }",
        ".about-page .under li.tavily { background: var(--lilac); }",
        ".about-page .under li.gbif { background: var(--clay-bg); }",
    ):
        assert rule in css, rule


def test_round_three_quotes_are_two_lines_each_and_carry_their_link(tmp_path):
    # 22 Oct round 3, Kash: short quotes (What it does, tested here until 25 Oct, went then)
    page = _spot_client(tmp_path)[0].get("/about").text
    # the small print under the results went; its link moved into the expert's card
    assert "The expert questions are text only" not in page
    quotes = re.findall(
        r'<blockquote class="about-card quote ink">(.*?)</blockquote>', page, flags=re.S
    )
    assert len(quotes) == 2 and all(q.count("<br>") == 1 for q in quotes)  # two lines each
    assert "An expert's review." in quotes[0] and ">how we measured</a>" in quotes[0]


def test_what_didnt_work_leads_each_row_with_its_lesson(tmp_path):
    # Kash: each lesson should make a judge think "of course!": the lesson, the evidence, now
    page = _about(tmp_path)
    didnt = page.split('<h2 id="didnt">', 1)[1].split("</section>", 1)[0]
    cards = re.findall(r"<li>(.*?)</li>", didnt, flags=re.S)
    assert len(cards) == 5
    for card in cards:
        assert re.match(
            r"<strong>[^<]+\.</strong>\s*<span>[^<]+</span>\s*<em>Now: [^<]+</em>$", card.strip()
        )
    for said in (
        "774 expert questions",
        "Round 8 shipped: 3 false agrees in 418",
        "10 of the 26",
        "4 false agrees in 205",
        "81% of answers",
        "4.8 points less often",
        "about $1.63 a run",
        "(5 of 6)",
        "11 of 21 right, 9 wrong and 1 left blank",
    ):
        assert said in didnt, said
    # self-hosting cost more, not less (devpost.md: about $1.63 a run against about a cent)
    assert "dearer" in didnt and "Cheaper" not in didnt


def test_whats_next_says_why_and_accessibility_is_a_plain_words_list(tmp_path):
    page = _about(tmp_path)
    nxt = page.split('<h2 id="whats-next">', 1)[1].split("</section>", 1)[0]
    assert nxt.count("<span>Why: ") == 6  # spot off adds its return
    access = page.split('<h3 id="access">', 1)[1].split("</section>", 1)[0]
    items = re.findall(r"<li>(.*?)</li>", access, flags=re.S)
    assert len(items) == 5 and all(
        i.startswith('<span aria-hidden="true">✓</span> ') for i in items
    )
    assert ">See the accessibility checks</a>" in access
    assert "axe-core" not in access and "3.98:1" not in access  # no jargon on its face


def test_round_three_joined_up(tmp_path):
    # 22 Oct, after the four round-3 parts landed: no names in the testers line, the reminder
    # job's platform among the stack chips, and no leftover rules the flow no longer uses
    page = _spot_client(tmp_path)[0].get("/about").text
    nxt = page.split('<h2 id="whats-next">', 1)[1].split("</section>", 1)[0]
    # the beginners' study ran on 23 Oct; the answer page changed after it (#517)
    assert "no screen-reader test yet, and the beginners' study ran before the answer page" in nxt
    assert "hasn't run" not in nxt
    # not "every step": the voice (when on) is ElevenLabs and the photo has a backup (review)
    assert (
        "Why: then reading the photo runs on NVIDIA too, and it's 5 times faster than GLM." in nxt
    )
    chips = page.split('<ul class="about-chips"', 1)[1].split("</ul>", 1)[0]
    assert "<li>Nebius AI Cloud</li>" in chips
    assert "Reminder emails come from a small daily job on Nebius AI Cloud." in page
    css = style.CSS
    assert ".node.then" not in css and ".about-page .node.answer { padding-top: 12px; }" not in css


def test_round_four_top_is_clear_of_the_band_with_a_green_nebius_line(tmp_path):
    # 22 Oct round 4, Kash: space under the band; the Nebius line across the page like home's
    # green "Decided by" line. 25 Oct: What it does went, so How it's built takes the space
    page = _spot_client(tmp_path)[0].get("/about").text
    css = style.CSS
    assert ".about-page .about #made-with { margin-top: 40px; }" in css
    assert ".about-page .about section > p.about-nebius { max-width: none;" in css
    nebius = css.split(".about-page .about section > p.about-nebius {", 1)[1].split("}", 1)[0]
    assert "text-align: center;" in nebius and "color: var(--ok);" in nebius
    assert '<p class="about-nebius">Every AI model runs on Nebius Token Factory' in page


def test_round_four_makes_one_lessons_panel_and_a_roadmap(tmp_path):
    # 22 Oct round 4, Kash: "boxes after boxes, more variety". What didn't work is one amber
    # panel of ruled rows; What's next is a line with five stops, not five dashed boxes
    page = _about(tmp_path)
    didnt = page.split('<h2 id="didnt">', 1)[1].split("</section>", 1)[0]
    assert didnt.count('<ul class="lesson-rows ink">') == 1 and didnt.count("<li><strong>") == 5
    assert "about-card" not in didnt
    nxt = page.split('<h2 id="whats-next">', 1)[1].split("</section>", 1)[0]
    assert (
        nxt.count('<ol class="roadmap" data-reveal="stagger">') == 1
        and nxt.count("<li><strong>") == 6  # spot off: its return is the sixth stop
    )
    assert "about-card" not in nxt
    css = style.CSS
    assert (
        ".about-page ul.lesson-rows { list-style: none;" in css
        and "background: var(--warn-bg); }" in css
    )
    assert ".about-page .lesson-rows > li + li { border-top: 1px solid var(--warn-line); }" in css
    assert "border-top: 2px dashed var(--muted-fg); }" in css  # the line, across on a wide screen
    assert "border-left: 2px dashed var(--muted-fg); }" in css  # and down on a phone


def test_round_four_left_no_rules_behind(tmp_path):
    # 23 Oct: four rounds by four sessions left 35 About rules that matched nothing (old tiles,
    # cards, the first flow, its swatches, the round-3 lesson grids); a browser scan found them
    css = style.CSS
    for gone in (
        "about-tiles",
        "about-lessons",
        "about-next",
        ".about-page .flow ",
        ".flow-evals",
        ".node.tavily",
        ".about-cards",
        ".sw.twin",
        ".sw.weather",
        ".about-card.later",
    ):
        assert gone not in css, gone


def test_the_cost_follows_the_flow_and_accessibility_closes_the_checks(tmp_path):
    # 23 Oct, Kash: "What each answer costs" straight after How it's built; Accessibility at
    # the end of How I know it works, before What didn't work, as a sub-heading
    page = _spot_client(tmp_path)[0].get("/about").text
    built_end = page.index("</section>", page.index('<h2 id="built">'))
    costs = page.index('<section class="about-costs" aria-labelledby="costs">')
    works = page.index('<h2 id="works">')
    assert built_end < costs < works
    cost = page[costs:works]
    assert (
        '<h3 id="costs">What each answer costs</h3>' in cost
        and "about-receipt about-card ink" in cost
    )
    access, real_user, didnt = (
        page.index('<h3 id="access">Accessibility</h3>'),
        page.index("<strong>A real user.</strong>"),
        page.index('<h2 id="didnt">'),
    )
    assert real_user < access < didnt
    assert page.count('id="access"') == 1 and '<h2 id="access">' not in page


def test_people_checks_have_their_own_sub_section_with_a_next_step(tmp_path):
    # 23 Oct, Kash: "Checked by people" in How I know it works, after the tests' cards and
    # before Accessibility; the expert was hired through Tendem ($47.86, the review), and the
    # Toloka study is pre-registered but has not run, so it claims no results ("and Tendem")
    page = _spot_client(tmp_path)[0].get("/about").text
    found, people, access = (
        page.index('id="works-results"'),
        page.index('<h3 id="people">Checked by people</h3>'),
        page.index('<h3 id="access">'),
    )
    assert found < people < access
    part = page[people:access]
    assert "A professional gardener hired through <strong>Tendem</strong> graded 3 photos" in part
    assert part.count('<blockquote class="about-card quote ink">') == 2
    nxt = part.split('<p class="about-people-next">', 1)[1].split("</p>", 1)[0]
    # run 23 Oct: the line gives its result and links the plan and the results
    assert nxt.startswith(
        "<strong>A first-time-user study on Toloka</strong> (23 Oct, 11 people): all got an"
        " answer, but only 6 could say what to do"
    )
    assert 'data/eval/prereg/2026-10-22-toloka-site-study.md"' in nxt
    assert 'data/eval/reports/2026-10-23-toloka-site-study.md"' in nxt
    # the two services in bold where they are named (23 Oct, Kash)
    assert (
        "<strong>Tendem</strong> and <strong>Toloka</strong> are paid from Nebius AI Builder"
        " programme credits." in nxt
    )


def test_the_toloka_pilot_is_aggregates_only_and_says_how_small(tmp_path):
    # 23 Oct, Kash: "It was a small pilot to verify our models." The 11-12 Oct run, majority
    # hits 4/5 without the reference and 3/5 with it (the private working repo's `2026-10-12-`
    # human-judges-toloka.md); we publish aggregates only, never raw labels
    page = _about(tmp_path)
    pilot = page.split('<p class="about-people-pilot">', 1)[1].split("</p>", 1)[0]
    assert pilot.startswith("<strong>A small Toloka pilot</strong> to check our photo reading")
    assert (
        "4 of 5 photos" in pilot
        and "(3 of 5)" in pilot
        # 15 people in all: 2 arms of 3 raters a photo (devpost: "15 beginner raters",
        # "30 ratings"); "3 raters each" read as 15 ratings (25 Oct)
        and "A tiny sample: 5 photos, 15 raters." in pilot
    )
    story = " ".join(
        (Path(__file__).parents[1] / "docs/submission/devpost.md").read_text("utf-8").split()
    )
    assert "**A small Toloka pilot.** To check our photo reading against people" in story
    assert "in 4 of 5 without the reference (one more partly) and 3 of 5 with it" in story
    assert "we publish aggregates only." in story and "trial terms" not in story
    assert "TODO (Kash), user testing" not in story  # the site study's slot, filled 24 Oct
    assert "**A first-time-user study on Toloka.** On 23 Oct, 11 strangers" in story


def test_one_name_for_the_builder_programme_everywhere(tmp_path):
    # 23 Oct review: the page said "Nebius Builder Program", the story and the source "AI
    # Builder programme"; one name for it on every page and in the story
    story = (Path(__file__).parents[1] / "docs/submission/devpost.md").read_text("utf-8")
    page = _about(tmp_path)
    for text in (story, page):
        assert "Builder Program" not in text
    assert "Nebius AI Builder programme credits" in " ".join(story.split())
    assert "Nebius AI Builder programme credits" in page


def test_with_the_spot_feature_off_whats_next_says_why(tmp_path):
    # 23 Oct, Kash: switched off for a focused experience; About says so under What's next
    nxt = _about(tmp_path).split('<h2 id="whats-next">', 1)[1].split("</section>", 1)[0]
    assert 'Bringing back "What can I grow here?"' in nxt
    assert "0.90 of the time" in nxt and "as good as the plant check" in nxt
    on = _spot_client(tmp_path)[0].get("/about").text
    assert "Bringing back" not in on.split('<h2 id="whats-next">', 1)[1].split("</section>", 1)[0]


def test_no_what_it_does_section_the_band_says_it_and_where_it_works_best(tmp_path):
    # 25 Oct, Kash: "just remove the What it does as we have the top of the About page already
    # saying enough". The band keeps the one point it didn't make: outdoors is where it's best
    for page in (_about(tmp_path), _spot_client(tmp_path, spot=False)[0].get("/about").text):
        assert 'class="about-what"' not in page and '<h2 id="what">' not in page
        assert 'class="about-lead"' not in page
        band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
        lead = html.unescape(band.split('<p class="lead">', 1)[1].split("</p>", 1)[0])
        assert lead.endswith("herbtwin does. It works best for herbs grown outside.")
        # How it's built comes straight after the band
        about = page.split('<div class="about">', 1)[1]
        assert about.lstrip().startswith('<section id="made-with" aria-labelledby="built">')
    css = style.CSS
    assert ".about-what" not in css and "p.about-lead" not in css


def test_the_advisors_are_one_model_asked_three_times_not_three_models(tmp_path):
    # 25 Oct (the #525 fact-check): "three advisors" read as three models; it is NVIDIA
    # Nemotron 3 Super asked the same question three times. How far the asks agree feeds into
    # how sure we are: one factor of several, so it never "sets" it (the Devpost fix).
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _about(tmp_path))))
    for loose in (
        "three advisors decide",
        "three plain advisors",
        "Advisors say water",
        "agree sets",
    ):
        assert loose not in text, loose
    assert "before three asks of Nemotron 3 Super decide" in text
    assert "Each decides on its own; how far they agree feeds into how sure we are" in text
    assert "Nemotron says water, but nothing looks dry" in text
    assert "Now: one model, Nemotron 3 Super, asked the same question three times." in text


def test_the_diagrams_sit_on_an_oat_panel_no_box_uses(tmp_path):
    # 25 Oct, Kash picked D1 from round 3: the page colour hid the panels, white (A) let the
    # white boxes blend, grey (B) vanished, pale sage (C1) merged with the mint boxes. One new
    # token, an oat stone, for light and dark; no edge
    static = Path(__file__).parents[1] / "src/herbtwin/web/static"
    base = (static / "herbtwin.css").read_text("utf-8")
    light, dark = base.split("@media (prefers-color-scheme: dark) { :root { --ink-shadow", 1)
    assert "--stone: #E3DACA;" in light.rsplit(":root { --lime", 1)[1]
    assert "--stone: #221F1A;" in dark.split("} }", 1)[0]
    about = (static / "pages/about.css").read_text("utf-8")
    panel = about.split(".about-page .flow-panel {", 1)[1].split("}", 1)[0]
    assert "background: var(--stone);" in panel and "border: 1.5px solid transparent;" in panel
    # no box wears it, so the boxes always stand off the panel; only the phone fork's mask,
    # which hides the rail's end, paints the panel's own colour (it was the page's, a pale bar)
    sheets = {p.name: p.read_text("utf-8") for p in (static / "pages").glob("*.css")}
    assert sum(s.count("var(--stone)") for s in sheets.values()) == 2
    mask = sheets["about-works.css"].split(".works-flow .branch:last-child::after {", 1)[1]
    assert "background: var(--stone);" in mask.split("}", 1)[0]
    assert "var(--bg)" not in sheets["about-works.css"] + sheets["about-built.css"]
    assert style._minify(about) in style.CSS
