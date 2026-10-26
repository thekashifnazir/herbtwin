"""About, "How it's built", round 3 (22 Oct, Kash's notes): our rules in the main row, bigger
boxes, the stack's chips coloured as the legend, a three-item legend, the Nebius line in plain
words, plainer decision cards, and the dashed "not built yet" box kept."""

import re
from pathlib import Path

import pytest

from herbtwin.web import style
from tests.test_web_answer_reveal import _rules
from tests.test_web_spot import HOME
from tests.test_web_spot import _client as _spot_client

ROOT = Path(__file__).parents[1]
SHEET = ROOT / "src/herbtwin/web/static/pages/about-built.css"
# round 4 (22 Oct): the section's new rules, sorting after about.css
SHEET_4 = ROOT / "src/herbtwin/web/static/pages/about_built.css"


def _built(tmp_path, monkeypatch, env: dict | None = None) -> str:
    from herbtwin.web import app as web_app

    monkeypatch.setattr(web_app, "trusted_check_on", lambda settings: True)
    page = _spot_client(tmp_path, home={**HOME, **(env or {})})[0].get("/about").text
    return page.split('<h2 id="built">', 1)[1].split("</section>", 1)[0]


def _steps(built: str) -> list[str]:
    """The flow's top-level steps, in order (each opens on its own line at one indent)."""
    flow = built.split('<ol class="flow-built"', 1)[1].split("</ol>", 1)[0]
    return re.split(r"\n      <li[ >]", flow)[1:]


def test_our_rules_sit_in_the_main_row_between_the_advisors_and_the_answer(tmp_path, monkeypatch):
    # Kash: "Move 'Our rules' into the main row: advisors -> our rules -> the answer (left to
    # right), not hanging below"
    steps = _steps(_built(tmp_path, monkeypatch))
    assert len(steps) == 8
    first = [re.search(r"<strong>([^<]+)</strong>", s).group(1) for s in steps]
    assert first == [
        "Your photo and place",
        "Read the photo",
        "Care and season",
        "Weather",
        "The plant&#39;s twin" if "&#39;" in steps[4] else "The plant's twin",
        "3 × NVIDIA Nemotron 3 Super",
        "Our rules",
        "The answer",
    ]
    # each is a step of its own, not a box stacked under the advisors
    assert '<div class="node rules">' in steps[6] and "node rules" not in steps[5]
    assert " then" not in "".join(steps)


def test_the_not_built_yet_box_stays_dashed_beside_the_twin(tmp_path, monkeypatch):
    # Kash: "good to show what comes next"
    twin = _steps(_built(tmp_path, monkeypatch))[4]
    assert (
        '<div class="node later"><strong>Not built yet</strong><span>A twin indoors</span>' in twin
    )
    assert ".about-page .node.later { box-shadow: none; border: 2px dashed var(--muted-fg);" in (
        style.CSS
    )


def test_the_legend_has_three_items(tmp_path, monkeypatch):
    built = _built(tmp_path, monkeypatch)
    key = built.split('<ul class="flow-key"', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r'<li><i class="sw ([a-z]+)"></i>([^<]+)</li>', key) == [
        ("path", "the weather&#39;s path" if "&#39;" in key else "the weather's path"),
        ("plain", "you, our notes, the answer"),
        ("later", "not built yet"),
    ]


def test_the_chips_went_and_the_flow_names_its_sources(tmp_path, monkeypatch):
    # Kash (22 Oct) had the stack's chips coloured as the flow's key; 25 Oct, the About audit
    # cut them: the pipeline and the services panel name every source, and in the folded
    # flow each source's tag carries its colour
    built = _built(tmp_path, monkeypatch)
    assert "about-chips" not in built and "about-chips" not in style.CSS
    for tag in ('<i class="tag">Tavily</i>', '<i class="tag">GBIF</i>', "<em>Open-Meteo</em>"):
        assert tag in built, tag


def test_the_nebius_line_is_plain_and_true(tmp_path, monkeypatch):
    # Kash: "we need to improve this". Both halves checked against what runs: the live deploy
    # sends every model call through the Token Factory backend, and the reminders workflow
    # runs the job on Nebius AI Cloud
    built = _built(tmp_path, monkeypatch)
    plain = (
        '<p class="about-nebius">Every AI model runs on Nebius Token Factory. '
        "Reminder emails come from a small daily job on Nebius AI Cloud.</p>"
    )
    assert plain in built
    assert "One adapter" not in built and "Serverless Job" not in built
    deploy = (ROOT / "the private working repo's `deploy.sh`").read_text("utf-8")
    assert "HERBTWIN_BACKEND=tokenfactory" in deploy
    job = (ROOT / ".github/workflows/reminders.yml").read_text("utf-8")
    assert "nebius ai job create" in job and '"-m herbtwin.reminders"' in job
    assert '- cron: "0 8 * * *"' in job


def test_with_the_voice_on_the_nebius_line_names_its_one_exception(tmp_path, monkeypatch):
    # the plant's voice is ElevenLabs, not Token Factory: off live, but if it comes back the
    # line must not say "every"
    env = {"HERBTWIN_VOICE_ENABLED": "1", "HERBTWIN_ELEVENLABS_API_KEY": "x"}
    built = _built(tmp_path, monkeypatch, env=env)
    assert "Every AI model runs on Nebius Token Factory, except the plant" in built
    assert "voice (ElevenLabs)" in built


def test_the_decisions_are_three_columns_that_carry_the_reports_figures(tmp_path, monkeypatch):
    # 23 Oct, Kash: the bullets "don't do them justice", but no more boxes. Three columns of
    # type, each read top to bottom: we chose, the model, over what, the figure, why
    built = _built(tmp_path, monkeypatch)
    decided = built.split("<h3>A few decisions I'd call out</h3>", 1)[1]
    cols = decided.split('<ul class="about-chose" data-reveal="stagger">', 1)[1]
    cols = cols.split("</ul>", 1)[0]
    assert "about-card" not in cols and "ink" not in cols and "about-points" not in built
    items = re.findall(r"<li>(.*?)</li>", cols, flags=re.S)
    assert len(items) == 3
    got = [
        [
            re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r'<p class="chose-[a-z]+(?: [a-z]+)?">(.*?)</p>', i, flags=re.S)
        ]
        for i in items
    ]
    assert [g[:4] for g in got] == [
        ["We chose", "Nemotron 3 Super", "over Ultra, the biggest", "2% vs 12.7%"],
        ["We chose", "Nemotron 3 Nano", "for the chat", "10 of 10"],
        ["We chose", "GLM-5.3-Flash", "over 4 NVIDIA vision models", "0.846 vs 0.627"],
    ]
    assert "said &#34;treat it&#34;" in items[0] or 'said "treat it"' in items[0]
    # the middle size treats least: Nano, the smallest, over-treated too, so "bigger was
    # keener to treat" would mislead
    assert "the middle size over-treated least" in items[0]
    assert "on our what-if check, in about half Super&#39;s time" in items[1] or (
        "on our what-if check, in about half Super's time" in items[1]
    )
    assert "on the same prompt. All four: 0.54 to 0.627; GLM: 0.846 to 0.867" in items[2]
    assert (
        'href="https://github.com/thekashifnazir/herbtwin/blob/main/docs/reference/nvidia-models.md"'
        in items[2]
    )
    # the model's name in its role's colour, but in words too, so colour is never the signal
    assert 'class="chose-name nvidia"' in items[0] and 'class="chose-name nvidia"' in items[1]
    assert 'class="chose-name photo"' in items[2]
    # the figures as the reports state them, like for like: 0.846 and 0.627 on the live prompt
    models = (ROOT / "docs/reference/nvidia-models.md").read_text("utf-8")
    assert "| **0.020** [0.000, 0.047] |" in models and "| 0.127 [0.080, 0.180] |" in models
    assert "| Nemotron 3 Nano 30B-A3B | 0.420 [0.340, 0.500] | 0.073 |" in models
    assert "| Token Factory | live | **0.846** [0.785, 0.899]" in models
    assert "| live | 0.627 [0.547, 0.707] |" in models
    assert "| 0.540 | not run |" in models and "| earlier | 0.867 [0.81, 0.92] |" in models
    nano = (ROOT / "docs/reference/chat-on-nano.md").read_text("utf-8")
    assert "| 10/10, 10/10, 10/10 | 15 s, 14 s, ~15 s |" in nano and "| 32 s, 24 s |" in nano


def test_the_weather_path_carries_no_words(tmp_path, monkeypatch):
    # 23 Oct, Kash: the "Day by day: night lows, rain and drying" label on the green wire from
    # the weather meant nothing to a reader, so it is gone; the wire itself stays
    built = _built(tmp_path, monkeypatch)
    turn = _steps(built)[3]
    assert turn.startswith('class="turn">')
    assert '<p class="flow-feed" aria-hidden="true"></p>' in turn
    assert "Day by day" not in built and "night lows" not in built
    sheet = SHEET_4.read_text("utf-8")
    reveal = (ROOT / "src/herbtwin/web/static/pages/about_reveal.css").read_text("utf-8")
    assert ".flow-feed > span" not in sheet + reveal and "reveal-ride" not in reveal
    # and on a phone, where there is no wire, the empty path adds no gap under the weather
    narrow = {s: b for at, s, b in _rules(sheet) if at == ("@media (max-width: 959px)",)}
    assert "display: none" in narrow[".about-page .flow-built > li.turn > .flow-feed"]


def test_the_second_row_reads_left_to_right_with_the_weather_on_an_l(tmp_path, monkeypatch):
    # 23 Oct, Kash: "That was not the line I flagged, it was the dotted line between the
    # normal diagram and the answers." So round 4's right-to-left second row is undone: the
    # twin starts row two again, every arrow points right, and the weather's green wire is
    # the L again, down from the weather and back along the gap to the twin
    both = _rules(SHEET.read_text("utf-8")) + _rules(SHEET_4.read_text("utf-8"))
    assert not any("grid-area" in b or "grid-column" in b for _, _, b in both)
    assert not any("\\2190" in b for _, _, b in both)  # no arrow points back, left
    wide = {s: b for at, s, b in both if at == ("@media (min-width: 960px)",)}
    assert 'content: "\\2192" / ""' in wide[".about-page .flow-built > li + li::before"]
    run = wide[".about-page .flow-built > .turn + li::after"]  # along the gap, 3 columns
    assert "width: calc(300% + 3 * 44px + 3px)" in run and "background: var(--ok)" in run
    assert "top: -31.5px" in run
    drop = wide[".about-page .flow-built > li.turn > .flow-feed"]  # down to meet it
    assert "margin: -14px 0 -33px" in drop
    wire = wide[
        ".about-page .flow-built > li.turn > .flow-feed::before, "
        ".about-page .flow-built > li.turn > .flow-feed::after"
    ]
    assert "background: var(--ok)" in wire
    # and the page order is the flow's order, so the answer ends row two on the right
    steps = _steps(_built(tmp_path, monkeypatch))
    assert steps[4].startswith('class="acc"><div class="node twin">')
    assert '<div class="node answer ink">' in steps[7]


def test_what_hangs_off_the_answer_is_joined_to_it_not_ruled_off(tmp_path, monkeypatch):
    # 23 Oct, Kash: the dashed line "between the normal diagram and the answers" was the one
    # to fix. The cards now hang off the answer: a line down from its box into a bracket over
    # them, labelled with where they are; on a phone, an arrow down to the label
    built = _built(tmp_path, monkeypatch)
    under = built.split('<div class="flow-under">', 1)[1].split("</ul>", 1)[0]
    assert re.sub(r"\s+", " ", under).startswith(
        ' <p class="flow-by under-by"><span>Also on your answer page</span></p> <ul class="under">'
    )
    assert "Under the answer" not in built
    # true: chat, the trusted-page quote, the shops and the sightings are all on result.html
    result = (ROOT / "src/herbtwin/web/templates/result.html").read_text("utf-8")
    for part in (
        'class="chatlog"',
        'class="sources-line trusted-quote"',
        '"_extras_slot.html"',
        '"_reported_slot.html"',
    ):
        assert part in result, part
    rules4 = _rules(SHEET_4.read_text("utf-8"))
    # no bare dashed rule: about.css's dashed border is overridden by this later sheet
    assert style.CSS.index(
        style._minify((ROOT / "src/herbtwin/web/static/pages/about.css").read_text("utf-8"))
    ) < style.CSS.index(style._minify(SHEET_4.read_text("utf-8")))
    flat = {s: b for at, s, b in rules4 if not at}
    assert "border-top: 0" in flat[".about-page .flow-under"]
    assert not any("dashed" in b for _, s, b in rules4 if "flow-under" in s)
    wide = {s: b for at, s, b in rules4 if at == ("@media (min-width: 960px)",)}
    drop = wide[".about-page .flow-built > li:last-child::after"]  # down from the answer
    assert "background: var(--muted-fg)" in drop and "flex: 1 0 0" in drop
    for side, corner in (("before", "left"), ("after", "right")):
        arm = wide[f".about-page .flow-under .under-by::{side}"]  # the bracket's two arms
        assert "border-top: 2px solid var(--muted-fg)" in arm, side
        assert f"border-{corner}: 2px solid var(--muted-fg)" in arm, side
    phone = {s: b for at, s, b in rules4 if at == ("@media (max-width: 959px)",)}
    arrow = phone[".about-page .flow-under::before"]
    assert 'content: "\\2193" / ""' in arrow and "color: var(--muted-fg)" in arrow


def test_the_weather_path_label_counts_in_few_words(tmp_path, monkeypatch):
    # the page's word cap: round 4's label added 8 words; 23 Oct, "Also on your answer page"
    # added 2 and the decisions as columns 2 fewer, so the section holds at 401
    import html

    built = _built(tmp_path, monkeypatch)
    # 25 Oct, the About audit: the detailed flow folds under "See every step", so it counts
    # only once opened, as the page's cap counts it
    shown = re.sub(r'<details class="pipe-more">.*?</details>', "", built, flags=re.S)
    assert shown != built
    words = html.unescape(re.sub(r"<[^>]+>", " ", '<h2 id="built">' + shown)).split()
    # grown on purpose on 25 Oct to 545 (537 measured) for Kash's "What each service did" panel,
    # then to 560 (551) when its LangSmith row said truly what a trace carries; the audit's
    # pipeline, open, with the flow folded, and the twin said to be outdoors (review): 460
    # (448 measured); Kash's round on rev 00119 (the trusted-page line under the answer, the
    # key and the cost line under the figure, its title gone): 475 (465 measured)
    assert len(words) <= 475


@pytest.mark.parametrize(
    ("sheet", "least"), [(SHEET, 10), (SHEET_4, 5)], ids=["about-built", "about_built"]
)
def test_about_built_css_is_scoped_to_the_page_and_uses_tokens_only(sheet, least):
    sheet = sheet.read_text("utf-8")
    assert style._minify(sheet) in style.CSS  # inlined by style.py, no <link> needed
    rules = _rules(sheet)
    assert len(rules) > least  # each sheet keeps its own guard (review)
    for _, sel, body in rules:
        for part in sel.split(","):
            assert part.strip().startswith(".about-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel
        for prop, value in re.findall(r"(?:^|;)\s*([a-z-]+)\s*:\s*([^;]+)", body):
            if prop in ("color", "background", "background-color", "border-color"):
                assert value.strip().startswith(("var(--", "transparent", "none")), (sel, prop)


def test_the_flow_boxes_stay_big():
    # bigger boxes and text in the flow (Kash: "now ~11px")
    rules = _rules(SHEET.read_text("utf-8"))
    node = next(b for _, s, b in rules if s == ".about-page .flow-built .node")
    assert int(re.search(r"font-size: (\d+)px", node).group(1)) >= 18


def test_the_decision_columns_are_split_by_thin_rules_only():
    # no boxes: no border all round, no fill, no shadow; one thin rule between columns, down
    # on a wide screen, across when they stack on a phone
    rules = [(at, s, b) for at, s, b in _rules(SHEET_4.read_text("utf-8")) if "about-chose" in s]
    for _, sel, body in rules:
        assert not re.search(r"(?:^|; )border:", body), sel
        assert "background" not in body and "box-shadow" not in body, sel
    flat = {s: b for at, s, b in rules if not at}
    assert "grid-template-columns: minmax(0, 1fr)" in flat[".about-page .about .about-chose"]
    assert (
        "border-top: 1px solid var(--border)" in flat[".about-page .about .about-chose > li + li"]
    )
    wide = {s: b for at, s, b in rules if at == ("@media (min-width: 860px)",)}
    assert "repeat(3, minmax(0, 1fr))" in wide[".about-page .about .about-chose"]
    between = wide[".about-page .about .about-chose > li + li"]
    assert "border-left: 1px solid var(--border)" in between and "border-top: 0" in between
    name = flat[".about-page .about .about-chose .chose-name"]
    assert "var(--display)" in name and "color: var(--ok)" in name
    assert "var(--display)" in flat[".about-page .about .about-chose .chose-fig"]
    assert "uppercase" in flat[".about-page .about .about-chose .chose-we"]
