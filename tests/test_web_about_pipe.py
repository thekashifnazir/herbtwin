"""About, How it's built, led by the simple pipeline (25 Oct, Kash on the About audit: the
Devpost figure is "super clear, anyone can follow it"; About's flow was dense). Six steps,
the answer with its cost, then the days after; the detailed flow folds under "See every
step"; What each service did stays open (Kash: sponsor use super clear)."""

import re
from pathlib import Path

from herbtwin.web import style
from tests.test_web_answer_reveal import _rules
from tests.test_web_spot import _client as _spot_client

SHEET = Path(__file__).parents[1] / "src/herbtwin/web/static/pages/about_pipe.css"

STEPS = [
    ("", "Your photo and place", None),
    ("", "Read the photo", "GLM-5.3-Flash"),
    ("", "Gather evidence", None),
    ("", "The plant's twin", None),  # neutral: colour says only NVIDIA Nemotron (25 Oct)
    (" advisors", "Advise", "NVIDIA Nemotron 3 Super"),
    ("", "How sure?", None),
]
LOOP = [
    (" advisors", "Ask", "NVIDIA Nemotron 3 Nano"),
    ("", "Reminder email", None),
    ("", "Did you do it?", None),
]


def _built(tmp_path) -> str:
    page = _spot_client(tmp_path, spot=False)[0].get("/about").text
    return page.split('<h2 id="built">', 1)[1].split("</section>", 1)[0]


def _boxes(ol: str) -> list[tuple[str, str, str | None]]:
    found = re.findall(
        r'<li><div class="node([a-z ]*)"><strong>([^<]+)</strong>(?:<em>([^<]+)</em>)?', ol
    )
    return [(kind, name.replace("&#39;", "'"), model or None) for kind, name, model in found]


def test_the_pipeline_leads_with_six_steps_the_answer_then_the_days_after(tmp_path):
    built = _built(tmp_path)
    pipe = built.split('<figure class="pipe" aria-labelledby="pipe-cap">', 1)[1].split(
        "</figure>", 1
    )[0]
    steps = pipe.split('<ol class="pipe-steps" role="list"', 1)[1].split("</ol>", 1)[0]
    loop = pipe.split('<ol class="pipe-loop" role="list"', 1)[1].split("</ol>", 1)[0]
    assert _boxes(steps) == STEPS and _boxes(loop) == LOOP
    # the answer between them, the step its cost prices
    assert (
        pipe.index("</ol>")
        < pipe.index('<p class="pipe-answer">')
        < pipe.index('<ol class="pipe-loop"')
    )
    answer = pipe.split('<p class="pipe-answer">', 1)[1].split("</p>", 1)[0]
    assert "<strong>The answer: one thing to do today, and how sure we are.</strong>" in answer
    # it leads: under the Nebius line, before the fold and the services panel
    assert (
        built.index('<p class="about-nebius">')
        < built.index('<figure class="pipe"')
        < built.index('<details class="pipe-more">')
        < built.index('<div class="about-services ink">')
        < built.index("A few decisions I'd call out")
    )
    # its title and key at the top, as on the Devpost figure (25 Oct, Kash: "sure")
    assert pipe.lstrip().startswith(
        '<figcaption id="pipe-cap"><strong>How herbtwin answers one photo</strong>'
    )
    assert "Tinted: NVIDIA Nemotron." in pipe.split("</figcaption>", 1)[0]


def test_the_pipelines_figures_are_the_codes(tmp_path):
    # every number the pipeline gives is one the code does
    from herbtwin.stages.advise import PANEL_TEMPERATURES
    from herbtwin.web.app import MAX_PHOTOS

    pipe = _built(tmp_path).split('<figure class="pipe"', 1)[1].split("</figure>", 1)[0]
    assert f"Up to {MAX_PHOTOS} photos of a herb" in pipe
    n = len(PANEL_TEMPERATURES)
    assert f"<span>Asked {n} times</span>" in pipe and f"How far the {n} answers agree" in pipe


def test_the_pipeline_says_the_twin_and_the_forecast_are_outdoors(tmp_path):
    # review of #535: the open pipeline read as if the twin always runs, with "Not built yet:
    # a twin indoors" folded away; indoors there is no forecast and no twin run (pipeline
    # weather_missing "indoors")
    steps = _built(tmp_path).split('<ol class="pipe-steps"', 1)[1].split("</ol>", 1)[0]
    assert "<span>Care facts, a Tavily search and, outdoors, the 2-week forecast</span>" in steps
    assert (
        "<strong>The plant&#39;s twin</strong><span>Outdoors, tries each choice against that"
        " weather. Indoors: no twin yet</span>"
        in steps
        or "<strong>The plant's twin</strong><span>Outdoors, tries each choice against that"
        " weather. Indoors: no twin yet</span>"
        in steps
    )


def test_the_detailed_flow_folds_and_the_services_stay_open(tmp_path):
    built = _built(tmp_path)
    fold = built.split('<details class="pipe-more">', 1)[1].split("</details>", 1)[0]
    assert '<details class="pipe-more" open' not in built
    assert fold.lstrip().startswith("<summary>See every step</summary>")
    assert '<figure class="flow-panel">' in fold and '<ol class="flow-built"' in fold
    # Kash (25 Oct): sponsor use super clear, so What each service did is never folded
    assert '<div class="about-services ink">' not in fold
    services = built.split('<div class="about-services ink">', 1)[1]
    assert "<details" not in services.split("</ul>", 1)[0]


def test_nemotrons_boxes_take_the_flows_nvidia_tint_never_the_bands_lime():
    # the lime is the band's one press (test_how_its_built_is_the_stack_then_one_coloured_flow)
    css = SHEET.read_text("utf-8")
    assert "--lime" not in css and not re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(", css)
    assert ".about-page .node.advisors { background: var(--soft); }" in style.CSS
    assert style._minify(css) in style.CSS


def test_the_arrows_are_silent_and_turn_down_on_a_phone():
    rules = _rules(SHEET.read_text("utf-8"))
    arrows = [
        (at, sel, body) for at, sel, body in rules if "::before" in sel and "content:" in body
    ]
    # each arrow's alt text is empty, so a screen reader reads only the steps
    assert arrows and all('/ ""' in body or "content: none" in body for _, _, body in arrows)
    phone = {sel: body for at, sel, body in rules if at == ("@media (max-width: 720px)",)}
    one = phone[".about-page .pipe :is(.pipe-steps, .pipe-loop)"]
    assert "grid-template-columns: minmax(0, 1fr)" in one
    down = phone[".about-page .pipe :is(.pipe-steps, .pipe-loop) > li + li::before"]
    assert 'content: "\\2193" / ""' in down
    # the row-start arrow comes back on a phone, but never on the first step, which has no
    # arrow's place and was pushed aside by one (seen at 390, 25 Oct)
    back = [
        s for at, s, _ in rules if at == ("@media (max-width: 720px)",) and "nth-child(3n + 1)" in s
    ]
    assert back == [".about-page .pipe .pipe-steps > li + li:nth-child(3n + 1)::before"]


def test_the_band_keeps_one_press_and_carries_the_public_code(tmp_path):
    page = _spot_client(tmp_path, spot=False)[0].get("/about").text
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert band.count("button primary") == 1
    assert (
        '<a class="button" href="https://github.com/thekashifnazir/herbtwin" rel="noopener noreferrer">'
        "The code and test reports</a>" in band
    )


# where each box runs, as a tag at its foot; None: our own code, no model or service
TAGS = {
    "Your photo and place": None,
    "Read the photo": "Token Factory",
    "Gather evidence": "Tavily",
    "The plant's twin": None,
    "Advise": "Token Factory",
    "How sure?": None,
    "Ask": "Token Factory",
    "Reminder email": "Nebius AI Cloud",
    "Did you do it?": "Token Factory",
}


def test_each_box_reads_step_model_line_then_where_it_runs(tmp_path):
    # 25 Oct, Kash: drawn like the Devpost figure, one layout for every box: the step in bold,
    # its model, a plain line, a small tag at its foot saying where it runs
    pipe = _built(tmp_path).split('<figure class="pipe"', 1)[1].split("</figure>", 1)[0]
    boxes = re.findall(r'<div class="node[a-z ]*">(.*?)</div>', pipe)
    assert len(boxes) == 9
    for box in boxes:
        name = re.match(r"<strong>([^<]+)</strong>", box)[1].replace("&#39;", "'")
        parts = re.findall(r"<(strong|em|span|i)\b", box)
        tag = re.search(r'<i class="pipe-tag">([^<]+)</i>$', box)
        assert parts[0] == "strong" and "span" in parts, name
        assert (tag[1] if tag else None) == TAGS[name], name
        if tag:
            assert parts[-1] == "i", name  # the tag last, at the foot


def test_the_boxes_are_flat_and_only_nemotron_is_tinted(tmp_path):
    pipe = _built(tmp_path).split('<figure class="pipe"', 1)[1].split("</figure>", 1)[0]
    kinds = re.findall(
        r'<div class="node([a-z ]*)"><strong>([^<]+)</strong>(?:<em>([^<]+)</em>)?', pipe
    )
    for kind, name, model in kinds:
        nemotron = bool(model and "Nemotron" in model)
        assert (kind == " advisors") == nemotron, (name, kind)
    rules = {sel: body for at, sel, body in _rules(SHEET.read_text("utf-8")) if not at}
    node = rules[".about-page .pipe .node"]
    assert "box-shadow: none" in node and "border-radius: 12px" in node
    tag = rules[".about-page .pipe .pipe-tag"]
    assert "margin-top: auto" in tag and "16px" in tag  # pinned at the foot; never under 16px
    # the heading centred over the centred Nebius line
    assert "text-align: center" in rules[".about-page .about h2#built"]
