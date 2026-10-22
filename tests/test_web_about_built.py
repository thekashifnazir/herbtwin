"""About, "How it's built", round 3 (22 Oct, Kash's notes): our rules in the main row, bigger
boxes, the stack's chips coloured as the legend, a three-item legend, the Nebius line in plain
words, plainer decision cards, and the dashed "not built yet" box kept."""

import re
from pathlib import Path

from herbtwin.web import style
from tests.test_web_answer_reveal import _rules
from tests.test_web_spot import HOME
from tests.test_web_spot import _client as _spot_client

ROOT = Path(__file__).parents[1]
SHEET = ROOT / "src/herbtwin/web/static/pages/about-built.css"


def _built(tmp_path, monkeypatch, env: dict | None = None) -> str:
    from herbtwin.web import app as web_app

    monkeypatch.setattr(web_app, "trusted_check_on", lambda settings: True)
    page = _spot_client(tmp_path, home={**HOME, **(env or {})})[0].get("/about").text
    return page.split('<h2 id="built">', 1)[1].split('<h2 id="works">', 1)[0]


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


def test_the_stack_chips_are_coloured_like_the_flow(tmp_path, monkeypatch):
    # Kash: "Colour the tech chips like the diagram ... so they act as part of the legend"
    built = _built(tmp_path, monkeypatch)
    chips = built.split('<ul class="about-chips"', 1)[1].split("</ul>", 1)[0]
    for colour, name in (
        ("tavily", "Tavily"),
        ("weather", "Open-Meteo"),
        ("gbif", "GBIF"),
        ("nvidia", "NVIDIA Nemotron 3"),
    ):
        assert f'<li class="{colour}">{name}</li>' in chips, name
    for name in ("Python 3.12", "FastAPI", "Cloud Run", "Nebius Token Factory", "Supabase"):
        assert f"<li>{name}</li>" in chips, name  # the rest neutral
    rules = {sel: body for _, sel, body in _rules(SHEET.read_text("utf-8"))}
    for colour, bg, fg in (
        ("tavily", "--lilac", "--lilac-fg"),
        ("weather", "--sky", "--sky-fg"),
        ("gbif", "--clay-bg", "--clay"),
        ("nvidia", "--soft", "--ok"),
    ):
        body = next(b for s, b in rules.items() if s.endswith(f".about-chips li.{colour}"))
        assert f"background: var({bg})" in body and f"color: var({fg})" in body, colour


def test_the_nebius_line_is_plain_and_true(tmp_path, monkeypatch):
    # Kash: "we need to improve this". Both halves checked against what runs: the live deploy
    # sends every model call through the Token Factory backend, and the reminders workflow
    # runs the job on Nebius AI Cloud
    built = _built(tmp_path, monkeypatch)
    plain = (
        "<p>Every AI model runs on Nebius Token Factory. "
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


def test_the_decision_cards_are_plain_and_carry_the_reports_figures(tmp_path, monkeypatch):
    built = _built(tmp_path, monkeypatch)
    cards = built.split('<ul class="about-cards decisions">', 1)[1].split("</ul>", 1)[0]
    for title in (
        "<strong>The mid-size model decides, not the biggest.</strong>",
        "<strong>The small model runs the chat.</strong>",
        "<strong>A non-NVIDIA model reads the photo, because it named plants better.</strong>",
    ):
        assert title in cards, title
    for figure in ("12.7%", "in 2%", "10 of 10", "about half", "0.54 to 0.627", "0.846 to 0.867"):
        assert figure in cards, figure
    assert (
        'href="https://github.com/thekashifnazir/herbtwin/blob/main/docs/reference/nvidia-models.md"'
        in cards
    )
    # the figures as the reports state them
    models = (ROOT / "docs/reference/nvidia-models.md").read_text("utf-8")
    assert "| **0.020** [0.000, 0.047] |" in models and "| 0.127 [0.080, 0.180] |" in models
    assert "| 0.627 [0.547, 0.707] |" in models and "| 0.540 | not run |" in models
    assert "**0.846** [0.785, 0.899]" in models and "| 0.867 [0.81, 0.92] |" in models
    nano = (ROOT / "docs/reference/chat-on-nano.md").read_text("utf-8")
    assert "| 10/10, 10/10, 10/10 | 15 s, 14 s, ~15 s |" in nano and "| 32 s, 24 s |" in nano


def test_about_built_css_is_scoped_to_the_page_and_uses_tokens_only():
    sheet = SHEET.read_text("utf-8")
    assert style._minify(sheet) in style.CSS  # inlined by style.py, no <link> needed
    rules = _rules(sheet)
    assert len(rules) > 10
    for _, sel, body in rules:
        for part in sel.split(","):
            assert part.strip().startswith(".about-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel
        for prop, value in re.findall(r"(?:^|;)\s*([a-z-]+)\s*:\s*([^;]+)", body):
            if prop in ("color", "background", "background-color", "border-color"):
                assert value.strip().startswith(("var(--", "transparent", "none")), (sel, prop)
    # bigger boxes and text in the flow (Kash: "now ~11px")
    node = next(b for _, s, b in rules if s == ".about-page .flow-built .node")
    assert int(re.search(r"font-size: (\d+)px", node).group(1)) >= 18
