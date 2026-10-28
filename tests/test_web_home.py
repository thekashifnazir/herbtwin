"""The home page: on the shared template, one main action, a quiet location and question,
the sharing ask as a tray, and one example answer clearly marked as an example."""

import re

from herbtwin.web import style
from tests.test_web import _client
from tests.test_web_accounts import _accounts_client, _sign_in
from tests.test_web_answer_reveal import _rules
from tests.test_web_spot import _client as _spot_client

HOME_CSS = (style.STATIC / "pages" / "home.css").read_text(encoding="utf-8")


def _home(tmp_path):
    return _client(tmp_path, [], []).get("/").text


def _credits(home: str) -> str:
    """ "Made with" at the foot of home: the model cards and the folded credits (19 Oct)."""
    return home.split('<section class="made-with" id="made-with"', 1)[1].split("</section>", 1)[0]


def test_home_is_on_the_shared_template(tmp_path):
    page = _home(tmp_path)
    assert page.count("<style>") == 1 and style.CSS in page
    assert 'class="wordmark" href="/"' in page and 'href="/privacy"' in page
    assert page.count("<h1>") == 1 and "<h1>What does this plant need?</h1>" in page
    assert 'style="' not in page  # no inline styles left


def test_home_has_one_main_action(tmp_path):
    page = _home(tmp_path)
    assert page.count('class="primary') == 1 and ">What does my plant need?</button>" in page
    spot, _ = _spot_client(tmp_path)
    on = spot.get("/").text
    assert on.count('class="primary') == 1
    assert re.search(r'class="primary[^"]*" type="submit">What does my plant need\?', on)
    assert 'formaction="/spots">What can I grow here?' in on


def test_the_photo_control_is_labelled_and_the_location_result_is_announced(tmp_path):
    page = _home(tmp_path)
    assert re.search(r'<label class="home-photo">Choose a photo.*?name="photo"', page, re.S)
    assert "<legend>Where is it?" in page
    assert 'id="located"' in page and 'aria-live="polite"' in page
    assert 'id="locate" hidden' in page  # shown only when the browser can locate


def test_home_shows_an_example_answer(tmp_path):
    page = _home(tmp_path)
    sample = page.split('aria-label="Example answer"', 1)[1].split("</article>", 1)[0]
    assert "TODAY" in sample and "How sure we are: Our best read. Right about half" in sample
    assert " in 10" not in sample  # 19 Oct answer-quality check: no number
    # the cold reason is the weather tile's; the card said it too (19 Oct re-check)
    assert "Because" not in sample


def test_signed_in_home_names_the_account_and_asks_in_a_tray(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    # 19 Oct home pass: the nav's "Sign in" says it; the line under the buttons repeated it
    assert "to remember your plants" not in c.get("/").text
    _sign_in(c, auth)
    page = c.get("/").text
    assert "Signed in as" not in page and 'href="/plants"' in page
    ask = page.split('class="tray home-ask"', 1)[1].split("</form>", 1)[0]
    assert 'value="yes">Yes</button>' in ask and 'value="no">No</button>' in ask
    assert "primary" not in ask  # the ask never outranks the photo


def test_the_survey_square_and_the_ruler_tape_are_gone(tmp_path):
    # on real screens the square ran through the headline and the photo box; the ruler
    # tape was its last leftover (13 Oct walkthrough): a plain hairline instead
    page = _home(tmp_path)
    assert "survey" not in page and ".survey" not in style.CSS
    assert "tape" not in page and ".tape" not in style.CSS and "mask-image" not in style.CSS


def _tokens(name):
    """[light, dark] values of a colour token, in the order the sheet sets them"""
    return re.findall(rf"--{name}: (#[0-9A-Fa-f]{{6}})", style.CSS)


def _contrast(a, b):
    def lum(h):
        c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_secondary_buttons_can_be_seen_in_light_and_dark():
    assert "background: var(--soft-strong)" in style.CSS
    assert "border: 1px solid var(--soft-line)" in style.CSS
    strong, line = _tokens("soft-strong"), _tokens("soft-line")
    assert len(strong) == len(line) == 2
    for i in (0, 1):  # light, dark
        fg, bg, card, soft = (_tokens(t)[i] for t in ("fg", "bg", "card", "soft"))
        assert _contrast(fg, strong[i]) >= 4.5  # the words on the button
        for under in (bg, card, soft):  # the edge, on the page, a card and a tray
            assert _contrast(line[i], under) >= 3


def test_the_optional_word_reads_on_the_place_box_in_light_and_dark():
    # 21 Oct accessibility pass: the place box keeps one green in both themes, so the dark
    # theme's dimmer --band-muted on it fell to 3.98:1 ("(optional)" by "Where is it?")
    assert ".home-page .home-band .home-where .muted { color: var(--tone-muted); }" in style.CSS
    (tone,) = _tokens("tone")
    (muted,) = _tokens("tone-muted")
    assert _contrast(muted, tone) >= 4.5


def test_the_green_band_holds_the_hero_form_and_twin(tmp_path):
    page = _home(tmp_path)
    band = page.split('<div class="home-band">', 1)[1].split('<figure class="home-twin"', 1)[0]
    assert "<h1>What does this plant need?</h1>" in band
    assert 'action="/analyse"' in band  # the form lives in the band
    assert (
        '<main id="content" tabindex="-1"><div class="wrap wide">' in page
    )  # the whole frame, not the reading column
    assert ".home-page .home-band { background: var(--band);" in style.CSS
    assert "var(--poster)" in style.CSS  # the condensed display face, band hero only


LEAD = (
    "<strong>One photo and one clear action!</strong><br>We model what the next 2 weeks could"
    " look like with your herb's digital twin, trying each action we can test."
)
IDEAL = "Ideal for outdoor herbs, with helpful information for indoor ones too!"


def test_the_hero_says_what_it_does_in_two_lines(tmp_path):
    # 18 Oct judge walk: the site never said what it does; 25 Oct, Kash's hook: a bold line,
    # then what the twin models, only the actions it can test (review: never "each possible"),
    # and "Is your herb perturbed?" stays the eyebrow above the H1
    hero = _home(tmp_path).split('<section class="home-hero">', 1)[1].split("</section>", 1)[0]
    assert hero.index('<p class="home-eyebrow">Is your herb perturbed?</p>') < hero.index("<h1>")
    assert "<h1>What does this plant need?</h1>" in hero
    assert f'<p class="lead">{LEAD}</p>' in hero
    assert hero.count("<p") == 2  # eyebrow and lead, nothing more


def test_the_twin_compare_uses_a_real_labelled_slider(tmp_path):
    page = _home(tmp_path)
    fig = page.split('<figure class="home-twin" data-reveal="rise">', 1)[1].split("</figure>", 1)[0]
    assert "qwen__basil__if_you_do.jpg" in fig and "qwen__basil__if_you_dont.jpg" in fig
    assert "If you protect it" in fig and "If you don't" in fig
    assert re.search(
        r'type="range"[^>]*aria-label="Compare if you protect it and if you don.t"', fig
    )
    # the credit for the picture is one tap away, in Credits and models
    assert '<a class="credits-link" href="#credits">Photo credits</a>' in fig
    assert "Forest and Kim Starr" in _credits(page) and "Qwen-Image-Edit" in _credits(page)


def test_the_sample_tiles_exist_on_disk(tmp_path):
    from herbtwin.web.style import STATIC
    from tests.test_web_spot import _client as _spot_client

    static = STATIC
    assert 'data-sample="7-pea-bed.jpg"' not in _home(tmp_path)  # no spot answer, no bed
    page = _spot_client(tmp_path)[0].get("/").text
    row = page.split('class="home-chip-row"', 1)[1].split("</div>", 1)[0]
    tiles = re.findall(
        r'href="(/static/samples/[^"]+)"[^>]*>\s*<picture><source type="image/webp"'
        r' srcset="([^"]+)"[^>]*><img src="(/static/samples/[^"]+)"',
        row,
    )
    assert len(tiles) == 6, tiles  # five plants and, with the spot answer on, one bed
    for href, srcset, src in tiles:
        assert (static / href.removeprefix("/static/")).is_file(), href
        assert (static / src.removeprefix("/static/")).is_file(), src
        for url in (c.split()[0] for c in srcset.split(", ")):
            assert (static / url.removeprefix("/static/")).is_file(), url
        # the tap sends the link's file, the full-size sample the model reads: only the
        # 40 px chip is a small copy (23 Oct image pass)
        assert not href.endswith((".webp", "-thumb.jpg")) and src.endswith("-thumb.jpg")
    # tapping a tile loads the file into the form rather than sending you away
    script = page.split("data-sample", 1)[1] + page.split("<script>", 1)[1]
    assert "DataTransfer" in script and 'dispatchEvent(new Event("change"' in script


def test_the_steps_strip_is_gone_since_how_it_works_says_it(tmp_path):
    # 19 Oct small-print plan: "What happens when you send it" repeated How it works, and
    # the wait page now shows the steps live
    home = _home(tmp_path)
    assert 'id="home-steps"' not in home and "What happens when you send it" not in home
    assert "home-step-list" not in style.CSS


def test_the_home_frame_is_wide_and_carries_all_the_evidence(tmp_path):
    # the band bleeds to the viewport from the full frame; inside the reading column it
    # was pulled sideways and cut off
    home = _home(tmp_path)
    assert (
        '<main id="content" tabindex="-1"><div class="wrap wide">' in home
        and "grow-page" not in home
    )
    for part in (
        '<figure class="home-twin"',
        'class="home-chip-row"',
        'id="credits"',
        'class="home-giant"',
        'class="home-bento"',
    ):
        assert part in home, part
    assert "grow-page" not in style.CSS


def test_the_chosen_photo_is_shown_back_and_sent_untouched(tmp_path):
    page = _home(tmp_path)
    box = page.split('<label class="home-photo"', 1)[1].split("</label>", 1)[0]
    assert 'name="photo"' in box and "required" in box
    assert 'id="photo-chosen" hidden' in box and 'id="photo-thumb"' in box
    assert 'id="photo-name"' in box and "Choose a different photo" in box
    script = page.split("the chosen photo, shown back", 1)[1].split("})();", 1)[0]
    assert "URL.createObjectURL" in script and "URL.revokeObjectURL" in script
    for touch in ("canvas", "toBlob", "DataTransfer", "input.files ="):
        assert touch not in script  # the vision model gets the file exactly as picked


def test_each_way_in_says_what_photo_it_wants(tmp_path):
    spot, _ = _spot_client(tmp_path)
    on = spot.get("/").text
    plant = on.split("What does my plant need?", 1)[1].split("</button>", 1)[0]
    grow = on.split('formaction="/spots">What can I grow here?', 1)[1].split("</button>", 1)[0]
    assert "One plant, close up" in plant and "A bed, pot or border" in grow


def test_the_photo_box_centres_its_words_and_the_picked_photo():
    """21 Oct, Kash: "align this better so choose a photo is in the center of this box".
    Centred before and after a pick; once picked the box rounds less, so the thumbnail
    never runs into the pill's curve on a phone."""
    rules: dict[str, str] = {}
    for _, sel, body in _rules(HOME_CSS):
        rules[sel] = rules.get(sel, "") + " " + body  # a selector may have several rules
    box = rules[".home-page .home-band .home-photo"]
    assert "display: flex" in box and "flex-direction: column" in box
    assert "align-items: center" in box and "text-align: center" in box
    assert "justify-content: center" in rules[".home-page .home-chosen"]
    assert "align-items: center" in rules[".home-page .home-chosen > span"]
    picked = rules[".home-page .home-band .home-photo.has-photo"]
    assert "border-radius: 28px" in picked


def test_a_picked_photo_box_still_shows_keyboard_focus():
    # the file input is always clipped (the pill is the target), so the pill draws the ring
    assert ".home-page .home-band .home-photo:has(input:focus-visible) { outline:" in style.CSS
    assert (
        ".home-page .home-band .home-photo input[type=file] { position: absolute; width: 1px;"
        in style.CSS
    )


def test_the_example_answer_says_how_sure_the_way_a_real_answer_can(tmp_path):
    # 13 Oct walkthrough: the example's wording must be one a real answer can emit
    # (19 Oct answer-quality check: our best read / not sure, no number; 21 Oct: the
    # answer's word badge and its line, as the rater text reads them)
    real = {
        "Our best read. Right about half the time in our tests.",
        "Not sure, check first. Right about 1 in 3 times in our tests.",
    }
    sample = _home(tmp_path).split('class="card home-sample"')[1].split("</article>")[0]
    said = re.search(r"How sure we are: ([^<]+)<", sample)
    assert said and said.group(1) in real, (said and said.group(1), real)


def test_the_band_place_field_stays_readable_and_the_bleed_never_scrolls_sideways():
    # the field is white in both themes, so its text can't take the theme's ink (near
    # white in dark mode); and the band's 100vw bleed counts a classic scrollbar, so the
    # page clips it rather than scrolling 15px sideways on Windows and Linux
    place = style.CSS.split(".home-page .home-band input[name=place] {", 1)[1].split("}", 1)[0]
    assert "background: var(--band-btn)" in place and "color: var(--band-btn-fg)" in place
    # the tokens, not the theme's ink: light paper and dark ink in both themes
    light, dark = style.CSS.split("prefers-color-scheme: dark", 1)
    for css in (light, dark.split("}", 1)[0]):
        assert re.search(r"--band-btn:\s*#[EF]", css) and re.search(r"--band-btn-fg:\s*#[12]", css)
    assert ".home-page { overflow-x: clip; }" in style.CSS


def test_the_home_example_is_set_in_london(tmp_path):
    # 17 Oct: the example is set in London, and London is the only place it names
    home = _home(tmp_path)
    frame = home.split('<section class="home-example"', 1)[1].split("</section>", 1)[0]
    assert "<strong>A basil photo, a cold week in London</strong>" in frame


def test_the_illustration_says_it_is_an_example_on_the_picture_and_in_words(tmp_path):
    home = _home(tmp_path)
    frame = home.split('id="twin-frame"', 1)[1].split("</div>", 1)[0]
    assert '<span class="home-twin-tag ex">Example</span>' in frame
    cap = home.split("<figcaption>", 1)[1].split("</figcaption>", 1)[0]
    assert (
        cap.startswith("<strong>Example:</strong>") and "An illustration, not a prediction" in cap
    )
    assert len(re.sub(r"<[^>]+>", "", cap).split()) <= 32  # was 60 words


def test_every_page_footer_carries_the_wordmark(tmp_path):
    # 17 Oct, Kash: only home had the big wordmark, so other pages looked plainer
    from herbtwin.web import progress

    c = _client(tmp_path, [], [])
    for page in (c.get("/privacy").text, progress.HEAD + progress._done("/x")):
        foot = page.split('<footer class="foot">', 1)[1]
        # a picture of the word since 25 Oct (final walk #7), still hidden from readers
        assert (
            '<svg class="foot-mark" viewBox="0 0 350 90" aria-hidden="true"' in foot
            and ">herbtwin</text>" in foot
        )
    from herbtwin.web.app import TEMPLATES

    spot = TEMPLATES.env.loader.get_source(TEMPLATES.env, "spot.html")[0]
    assert "{% block foot %}{{ super() }}" in spot  # the spot page adds its record id
    home_foot = _home(tmp_path).split('<footer class="foot">', 1)[1]
    assert 'class="home-giant"' in home_foot and "foot-mark" not in home_foot


def test_the_bed_sample_points_at_what_can_i_grow_and_is_credited(tmp_path):
    # 18 Oct judge walk: every sample was one plant close up, so a judge with no garden to
    # hand had nothing to try "What can I grow here?" with
    from pathlib import Path

    from tests.test_web_spot import _client as _spot_client

    page = _spot_client(tmp_path)[0].get("/").text
    tile = page.split('data-sample="7-pea-bed.jpg"', 1)[1].split("</a>", 1)[0]
    assert 'data-go="go-spot"' in tile and "<span>Raised bed</span>" in tile
    assert 'id="go-spot"' in page and "tile.dataset.go" in page
    assert ">Wikimedia Commons</a>" in _credits(page) and "Kolforn" in _credits(page)
    assert "CC BY-SA 4.0" in _credits(page)
    assert "own photo" not in page  # 18 Oct: no garden of ours as a public sample
    root = Path(__file__).parent.parent
    credits = (root / "docs/judges/samples/CREDITS.md").read_text()
    assert "| `7-pea-bed.jpg` | Kolforn (Wikimedia) | CC BY-SA 4.0 |" in credits
    assert (root / "docs/judges/samples/7-pea-bed.jpg").is_file()
    # JUDGES.md's samples are the site's, byte for byte: that is how they are set in London
    for doc in (root / "docs/judges/samples").glob("*.jpg"):
        site = root / "src/herbtwin/web/static/samples" / doc.name
        assert doc.read_bytes() == site.read_bytes(), doc.name


def test_no_page_asks_for_the_replaced_bed_photo_urls(tmp_path):
    # 18 Oct: Cloudflare kept serving the old bed photo at its old URL for 30 days after
    # the file was replaced in place; a new name is a new URL, and nothing asks for the old
    from tests.test_web_judge import CODE
    from tests.test_web_judge import _client as _judge_client
    from tests.test_web_spot import _client as _spot_client

    home = _spot_client(tmp_path)[0].get("/").text
    env = {"HERBTWIN_JUDGE_CODE": CODE, "HERBTWIN_SPOT_ENABLED": "1"}
    (tmp_path / "j").mkdir()
    judge = _judge_client(tmp_path / "j", env).post("/judge", data={"code": CODE}).text
    for page in (home, judge):
        assert "7-raised-bed" not in page and "/static/samples/7-pea-bed.jpg" in page


def test_the_home_example_is_one_framed_example_with_its_input_and_no_date(tmp_path):
    # 18 Oct judge walk: the 4 boxes under the card read as live widgets, and "12 Oct"
    # looked stale on any later day. One frame holds the answer and its evidence, the
    # "Example" tab sits on its edge, and the header shows what went in
    home = _home(tmp_path)
    assert "12 Oct" not in home
    frame = home.split('<section class="home-example"', 1)[1].split("</section>", 1)[0]
    assert '<p class="home-example-tab" id="home-example-tab">Example</p>' in frame
    head = frame.split('<p class="home-example-in" data-reveal="rise">', 1)[1].split("</p>", 1)[0]
    # an openly licensed sample (Forest and Kim Starr, CC BY 3.0 US), never Kash's own
    assert 'src="/static/samples/3-basil-yellow-leaves-thumb.jpg"' in head
    # one line: what went in, then the arrow to what came out (19 Oct home pass)
    assert "<strong>A basil photo, a cold week in London</strong>" in head and "→" in head
    assert 'aria-label="Example answer"' in frame and "Next 2 weeks vs leaving it" in frame
    # how it works is not part of this answer: one line under the frame, no "4 models" box
    assert "home-how-sources" not in frame and "4 models" not in home
    assert "Try this example" not in home


def test_the_example_arrow_stays_with_its_last_word_on_a_phone(tmp_path):
    # 28 Oct site walk: at 390 px the arrow was its own flex item and wrapped onto a line
    # of its own. Text and arrow are one item, joined by a no-break space
    frame = _home(tmp_path).split('<section class="home-example"', 1)[1].split("</section>", 1)[0]
    head = frame.split('<p class="home-example-in" data-reveal="rise">', 1)[1].split("</p>", 1)[0]
    assert (
        '<span class="home-example-what"><strong>A basil photo, a cold week in London</strong>'
        '&nbsp;<span class="home-example-arrow" aria-hidden="true">→</span></span>'
    ) in head
    # and that item grows from zero, so it wraps beside the thumbnail, not under it
    what = style.CSS.split(".home-page .home-example-what {", 1)[1].split("}", 1)[0]
    assert "flex: 1 1 0" in what and "min-width: 0" in what


def test_the_example_frame_keeps_its_tab_on_the_edge_and_a_small_thumbnail():
    frame = style.CSS.split(".home-page .home-example {", 1)[1].split("}", 1)[0]
    assert "dashed" in frame and "position: relative" in frame
    tab = style.CSS.split(".home-page .home-example-tab {", 1)[1].split("}", 1)[0]
    assert "translateY(-50%)" in tab and "top: 0" in tab
    thumb = style.CSS.split(".home-page .home-example-in img {", 1)[1].split("}", 1)[0]
    assert "width: 56px" in thumb  # a fixed small thumbnail, never the 480 px file's width


def test_the_example_frame_is_filled_with_abouts_oat():
    # 25 Oct, Kash: "change this background colour to the same as what we did in About with
    # the brown oat colour"; the page's own paper made the frame read as part of the page
    frame = style.CSS.split(".home-page .home-example {", 1)[1].split("}", 1)[0]
    assert "background: var(--stone);" in frame and "var(--bg)" not in frame
    assert "border: 2px dashed var(--fg);" in frame  # the dashed edge and its tab stay


def test_how_it_works_is_four_photo_cards_of_the_examples_real_output(tmp_path):
    # 18 Oct judge ideas, item 12: the pipeline at a glance, one chip of output per step.
    # #408 took it out; back on 22 Oct (Kash: "it was nice getting a how to on the bottom")
    home = _home(tmp_path)
    how = home.split('<section class="home-how"', 1)[1].split("</section>", 1)[0]
    assert '<h2 id="home-how-h" data-reveal="rise">How it works</h2>' in how
    cards = (
        how.split('<ol class="home-how-cards" data-reveal="stagger">', 1)[1]
        .split("</ol>", 1)[0]
        .split("<li>")[1:]
    )
    chips = [re.search(r'class="home-how-chip">([^<]+)<', c).group(1) for c in cards]
    assert chips == [
        "Found basil",
        "3 °C nights from Wed",
        "Twin: shelter ✓ better",
        "Shelter it this week · our best read",
    ]
    # the chips agree with the example above them
    frame = home.split('<section class="home-example"', 1)[1].split("</section>", 1)[0]
    assert "<h2>Basil</h2>" in frame  # Found basil
    assert "3 °C" in frame and "Nights from Wednesday" in frame  # 3 °C nights from Wed
    assert (
        "Shelter it" in frame and "How sure we are: Our best read." in frame
    )  # Shelter it this week · our best read
    assert re.search(r"Better</span>\s*<strong>Protect it</strong>", frame)  # shelter ✓ better
    # card 3's picture is the twin left out, said on the picture, under the verdict chip
    assert '<span class="home-how-tag">If left out</span>' in cards[2]
    # only the openly licensed basil sample and the twin pictures drawn from it
    srcs = re.findall(r'<img src="([^"]+)"', how)
    assert srcs and all(
        s in {"/static/samples/3-basil-yellow-leaves-thumb.jpg"}
        or s.startswith("/static/twin/qwen__basil__")
        for s in srcs
    )
    # no link at all (21 Oct, Kash: "do we even need the link to go to a separate page? We
    # already have that info below"): Made with is the next section, and the nav has About
    pill = how.split('<p class="home-how-sources" data-reveal="rise">', 1)[1].split("</p>", 1)[0]
    assert pill == "Decided by NVIDIA Nemotron 3 Super on Nebius Token Factory"
    assert "Forest and Kim Starr" in _credits(home)
    # Made with at home's foot, on a phone: two to a row, job and name (About has them in full)
    phone = style.CSS.split("@media (max-width: 560px) { .home-page .made-with .made-cards {", 1)
    assert len(phone) == 2 and phone[1].startswith(" grid-template-columns: repeat(2,")


def _rule(selector: str) -> str:
    return style.CSS.split(selector + " {", 1)[1].split("}", 1)[0]


def _mix(top: str, under: str, share: float) -> str:
    """color-mix(in srgb, top share, transparent) over `under`, as a hex colour"""
    ch = [
        round(int(top[i : i + 2], 16) * share + int(under[i : i + 2], 16) * (1 - share))
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02x}" for c in ch)


def test_the_models_line_keeps_the_green_but_never_the_shape_of_a_button():
    # 22 Oct, Kash on the filled pill: "like the colour but it does look like a button"; the
    # ink outline (#408) lost the green. Green words, centred, with no box at all
    rule = _rule(".home-page .home-how-sources")
    assert "color: var(--ok);" in rule and "text-align: center;" in rule
    assert not re.search(r"background|border|padding|display", rule)
    for i in (0, 1):  # light, dark
        assert _contrast(_tokens("ok")[i], _tokens("bg")[i]) >= 4.5


def test_the_two_week_box_has_the_twins_colour_and_its_verdicts_are_words(tmp_path):
    # 22 Oct, Kash: the filled green "Better" looked pressable, and the box's amber meant
    # nothing (walk A10). The box is the twin's verdict, so the twin's deep green (the band's,
    # where the slider sits); Better and Same are small tinted tags, like Also do: no border,
    # no shadow, tight, never the primary green of a press
    frame = _home(tmp_path).split('<div class="home-bento"', 1)[1].split("</section>", 1)[0]
    tiles = frame.split('<div class="card home-tile')[1:]
    assert "Next 2 weeks vs leaving it" in tiles[2]  # :nth-child(3)
    box = _rule(".home-page .home-tile:nth-child(3)")
    assert "background: var(--band); color: var(--band-fg);" in box and "warn" not in box
    same = " ".join(_rule(".home-page .home-verdict").split())
    better = " ".join(_rule(".home-page .home-outlook .better .home-verdict").split())
    assert "padding: 2px 10px;" in same and "14px" in same
    wash = "background: color-mix(in srgb, var(--band-fg) 18%, transparent); color: var(--band-fg);"
    assert wash in same
    assert better == "background: var(--soft); color: var(--ok);"
    for rule in (same, better):
        assert not re.search(r"border:|shadow|--primary", rule)
    assert "primary" not in tiles[2]  # nothing to press in the box
    # on a phone each choice is one row (tag, name, note), and the rule outranks the base one
    phone = HOME_CSS.split("@media (max-width: 720px)")[-1]
    assert ".home-page .home-bento .home-outlook li { flex-direction: row;" in " ".join(
        phone.split()
    )
    assert _rule(".home-page .home-tile:nth-child(3) .muted") == " color: var(--band-muted); "
    for i in (0, 1):  # each tag's words read on it; the notes and the words on the twin's green
        assert _contrast(_tokens("ok")[i], _tokens("soft")[i]) >= 4.5
        band = _tokens("band")[i]
        assert _contrast(_tokens("band-fg")[i], _mix(_tokens("band-fg")[i], band, 0.18)) >= 4.5
        assert _contrast(_tokens("band-muted")[i], band) >= 4.5
        assert _contrast(_tokens("band-fg")[i], band) >= 4.5


def test_how_it_works_names_open_plantbook_only_when_it_is_asked(tmp_path, monkeypatch):
    # plantbook_from skips it without both keys: a keyless run must not claim it
    def line(home: str) -> str:
        return _credits(home)

    assert "Open Plantbook" not in line(_home(tmp_path))  # the test settings carry no keys
    monkeypatch.setattr("herbtwin.web.app.plantbook_on", lambda settings: True)
    (tmp_path / "keyed").mkdir()
    assert "Open Plantbook" in line(_home(tmp_path / "keyed"))


def test_open_plantbook_is_on_only_with_both_keys():
    from herbtwin.config import load_settings
    from herbtwin.plantbook import plantbook_on

    both = {
        "HERBTWIN_OPENPLANTBOOK_CLIENT_ID": "test-id",
        "HERBTWIN_OPENPLANTBOOK_CLIENT_SECRET": "test-secret",
    }
    assert plantbook_on(load_settings(both))
    assert not plantbook_on(load_settings({"HERBTWIN_OPENPLANTBOOK_CLIENT_ID": "test-id"}))
    assert not plantbook_on(load_settings({}))


def test_how_it_works_keeps_one_models_line_and_credits_hold_the_rest(tmp_path):
    home = _home(tmp_path)
    line = home.split('<p class="home-how-sources" data-reveal="rise">', 1)[1].split("</p>", 1)[0]
    # the judges' eligibility signal stays in view
    assert line.startswith("Decided by NVIDIA Nemotron 3 Super on Nebius Token Factory")
    credits = _credits(home)
    # Token Factory is named once, in the line above (22 Oct walk 2: it was said 3 times)
    for name in ("RHS", "Open-Meteo.com", "NVIDIA Nemotron 3 Super"):
        assert name in credits
    cards = credits.split('<ul class="made-cards">', 1)[1].split("</ul>", 1)[0]
    assert "<img" not in cards  # names, not logos


def test_where_says_which_location_once_a_photo_is_picked(tmp_path):
    # 19 Oct, Kash's walk: the photo's own location is said up front, the choices folded
    # behind "Use somewhere else"; no location says so and leaves the choices open
    home = _home(tmp_path).replace("&#39;", "'")
    where = home.split('<fieldset class="home-where">', 1)[1].split("</fieldset>", 1)[0]
    assert '<p class="home-photo-place" id="photo-place" hidden>' in where
    assert "<span>Location found in your photo (rounded to about 1 km).</span>" in where
    assert (
        'id="where-else" aria-controls="where-pick" aria-expanded="false">Use somewhere else'
        in where
    )
    assert '<div class="home-no-place" id="no-photo-place" hidden>' in where
    assert (
        "<p><strong>No location in this photo.</strong> Add a town for weather-checked advice: "
        "frost, rain and what's normal this month.</p>" in where
    )
    # the choices are open in the markup: without a script they simply show
    pick = where.split('<div class="home-where-pick" id="where-pick">', 1)[1].split("</div>", 1)[0]
    assert 'id="locate"' in pick and 'name="place"' in pick
    js = home.split("say which location the answer will use", 1)[1].split("})();", 1)[0]
    # what they chose or typed wins on the server, so the photo's line goes when they have
    assert "const chosen = Boolean(place.value.trim() || lat.value);" in js
    assert "uses.hidden = !where || chosen;" in js
    assert "none.hidden = Boolean(where) || chosen || !input.files || !input.files[0];" in js
    assert "pick.hidden = Boolean(where) && !chosen && !open;" in js
    assert "if (mine !== asked) return;" in js  # a slow read never overwrites a newer pick
    assert '<div role="status" aria-live="polite"><p class="home-photo-place"' in where  # heard


def test_where_says_found_in_green_and_missing_in_amber_with_the_choices_up_front(tmp_path):
    """21 Oct, Kash: "make it more obvious that no location was picked up, and so they can add
    it if they want more info". No location: an amber "check" note (not an error) with an
    icon and the benefit; found: green with a tick. Both stay optional."""
    home = _home(tmp_path).replace("&#39;", "'")
    where = home.split('<fieldset class="home-where">', 1)[1].split("</fieldset>", 1)[0]
    assert "Where is it? <span" in where and "(optional)" in where
    found = where.split('id="photo-place" hidden>', 1)[1].split("</p>", 1)[0]
    missing = where.split('id="no-photo-place" hidden>', 1)[1].split("</div>", 1)[0]
    for box in (found, missing):
        assert '<svg class="where-icon"' in box and 'aria-hidden="true"' in box
    rules: dict[str, str] = {}
    for _, sel, body in _rules(HOME_CSS):
        rules[sel] = rules.get(sel, "") + " " + body
    amber = rules[".home-page .home-band .home-no-place"]
    assert "background: var(--warn-bg)" in amber and "var(--warn-line)" in amber
    assert "color: var(--warn)" in rules[".home-page .home-band .home-no-place :is(svg, strong)"]
    green = rules[".home-page .home-band .home-photo-place"]
    assert "background: var(--soft)" in green
    assert "color: var(--ok)" in rules[".home-page .home-band .home-photo-place svg"]
    # the way to add one stands out while the note shows: a filled button, not an outline
    prominent = ".home-page .home-band .home-where:has(#no-photo-place:not([hidden])) #locate"
    assert "background: var(--band-btn)" in rules[prominent]
    assert ":hover" in "".join(s for s in rules if s.startswith(prominent))  # it still answers
    # the script rewrites only the words, so the found box keeps its tick
    js = home.split("say which location the answer will use", 1)[1].split("})();", 1)[0]
    assert 'uses.querySelector("span").textContent = said[where]' in js
    # the button inside the light green box reads on it in both themes
    assert "color: var(--fg)" in rules[".home-page .home-band .home-photo-place #where-else"]


def test_a_sample_says_london_and_its_own_name_and_the_button_comes_into_view(tmp_path):
    # judge pre-walk, 19 Oct: a sample read "place unknown" (now London: where.is_sample),
    # showed "3-basil-yellow-leaves.jpg", and the button to press sat below the fold
    home = _home(tmp_path).replace("&#39;", "'")
    js = home.split("say which location the answer will use", 1)[1].split("})();", 1)[0]
    assert 'sample: ["Sample photo: set in London.",' in js
    assert 'show(sample ? "sample" : gps ? "photo" : null);' in js
    assert 'if (e.type !== "change") return;' in js  # a restored page keeps its scroll
    assert 'button.scrollIntoView({block: "nearest"' in js
    assert "named.textContent = sample ? `Sample photo: ${sample.name}` : file.name;" in js
    # a sample picked through the file picker is known by its bytes, as on the server
    assert 'crypto.subtle.digest("SHA-256"' in js
    assert '"1-parsley-healthy.jpg"' in js.split("const samples = ", 1)[1].split(";", 1)[0]
    assert (
        "input.herbtwinSample = {file: input.files[0], name: tile.textContent.trim(), "
        'go: tile.dataset.go || ""};' in home
    )


def test_the_location_choices_say_what_this_browser_can_do_and_the_last_one_wins(tmp_path):
    # #271 review: "Use my location" offered with no geolocation; device and town both given
    # and the device winning silently
    home = _home(tmp_path).replace("&#39;", "'")
    js = home.split('const go = document.getElementById("locate")', 1)[1].split("})();", 1)[0]
    # no geolocation: the button stays hidden and the note's "Add a town" still holds, so
    # the note is never rewritten (it keeps its icon)
    assert "none.textContent" not in js
    assert (
        'lat.value = ""; lon.value = "";' in js
        and 'said.textContent = "We\'ll use the town you typed.";' in js
    )
    assert 'place.value = "";' in js.split("getCurrentPosition", 1)[1]


def test_the_photo_button_says_it_is_ideal_for_outdoor_herbs(tmp_path):
    # 25 Oct, Kash: "make it clear to people what is the optimal way to use this ... if
    # someone is using indoor, understand why they have less". One quiet line right under
    # the Choose a photo pill, said once; never a box or a second press
    for page in (_home(tmp_path), _spot_client(tmp_path)[0].get("/").text):
        form = page.split('<form class="home-form"', 1)[1].split("</form>", 1)[0]
        line = f'<p class="small muted home-ideal">{IDEAL}</p>'
        after = form.split('<label class="home-photo">', 1)[1].split("</label>", 1)[1]
        assert re.sub(r"\{#.*?#\}", "", after, flags=re.S).lstrip().startswith(line)
        assert page.count(IDEAL) == 1
        for gone in ("Best for herbs grown outside", "Built for outdoor herbs"):
            assert gone not in page
        assert page.count('class="primary') == 1
    rule = re.search(r"\.home-band \.home-ideal \{([^}]*)\}", HOME_CSS).group(1)
    assert not re.search(r"border|background|shadow", rule)
