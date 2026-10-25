"""About's "What each service did" (25 Oct, Kash: "make sure we are super clear about how we
have used" Token Factory, Tavily, LangSmith, Toloka and Tendem): one panel of ruled rows under
the stack, each with what it did here and its proof, every number as its source says it."""

import re
from pathlib import Path

from herbtwin.web import style
from tests.test_web_answer_reveal import _rules
from tests.test_web_spot import _client as _spot_client

ROOT = Path(__file__).parents[1]
SHEET = ROOT / "src/herbtwin/web/static/pages/about_services.css"


def _panel(tmp_path) -> str:
    page = _spot_client(tmp_path, spot=False)[0].get("/about").text
    built = page.split('<h2 id="built">', 1)[1].split("</section>", 1)[0]
    return built.split('<div class="about-services ink">', 1)[1].split("</ul>", 1)[0]


def test_one_row_per_service_in_order_under_the_stack(tmp_path):
    panel = _panel(tmp_path)
    assert panel.lstrip().startswith('<h3 id="services">What each service did</h3>')
    names = re.findall(r'<p class="svc-name">([^<]+)</p>', panel)
    assert names == ["Nebius Token Factory", "Tavily", "LangSmith", "Tendem", "Toloka"]
    assert panel.count('<p class="svc-what">') == 5 and panel.count('<p class="svc-proof">') == 5


def test_each_proof_is_the_number_its_source_gives(tmp_path):
    proofs = [
        re.sub(r"<[^>]+>", "", p)
        for p in re.findall(r'<p class="svc-proof">(.*?)</p>', _panel(tmp_path))
    ]
    assert proofs[0] == "One example answer: $0.0040 of model time"
    assert proofs[1] == "Chat answers right: 25 of 30 with it, 15 without"
    assert proofs[2] == "12 experiments, 4,052 scored runs"
    assert proofs[3].startswith("Every first action Acceptable; 3 of 5 overall")
    assert proofs[4].startswith("All got an answer; 6 of 11 could say what to do")
    # and the sources say them
    about = (ROOT / "src/herbtwin/web/templates/about.html").read_text("utf-8")
    assert "<strong>$0.0040</strong> of model time" in about  # the cost card
    assert 'bar("With Tavily search", "25 of 30"' in about and 'bar("Without", "15 of 30"' in about
    upload = (ROOT / "the private working repo's `2026-10-15-chore-langsmith-experiments.md`").read_text("utf-8")
    assert "12 experiments, 4,052 runs, every run scored" in re.sub(r"\s+", " ", upload)
    review = (ROOT / "data/eval/reports/2026-10-19-expert-review.md").read_text("utf-8")
    assert "Overall (1 to 5)" in review and review.count("| Acceptable | 3 |") == 3
    study = (ROOT / "data/eval/reports/2026-10-23-toloka-site-study.md").read_text("utf-8")
    assert "**11 of 11** reached an answer page" in study
    assert "| **P1** | Right action | **6 / 11 (55%)**" in study


def test_the_panel_is_one_inked_box_of_ruled_rows_in_the_legend_colours():
    rules = {s: b for at, s, b in _rules(SHEET.read_text("utf-8")) if not at}
    assert "box-shadow: 5px 5px 0 var(--ink-shadow)" in rules[".about-page .about-services"]
    assert "border-top: 1px solid var(--border)" in rules[".about-page .about-services .svc-row"]
    tavily = rules[".about-page .about-services .tavily .svc-name"]
    assert "var(--lilac)" in tavily and "var(--lilac-fg)" in tavily
    assert style._minify(SHEET.read_text("utf-8")) in style.CSS
    for _, sel, body in _rules(SHEET.read_text("utf-8")):
        assert sel.strip().startswith(".about-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel


def test_the_langsmith_row_says_what_reaches_it_and_token_factory_leaves_room_for_the_voice(
    tmp_path,
):
    # 25 Oct review: traces carry the text sent and returned, redacted only of photos, email
    # addresses and coordinates (remote_traces.py, redact.py; privacy.html says so), so
    # "never your words" was false; and the plant's voice runs on ElevenLabs, not Token Factory
    whats = [
        re.sub(r"<[^>]+>", "", w)
        for w in re.findall(r'<p class="svc-what">(.*?)</p>', _panel(tmp_path))
    ]
    assert whats[0].startswith("Runs the AI models: GLM-5.3 Flash reads the photo")
    assert whats[2] == (
        "Traces each model call on the live site (the text sent and returned, with photos, "
        "email addresses and locations removed; time, tokens, cost), and holds our saved evals."
    )
    devpost = (ROOT / "docs/submission/devpost.md").read_text("utf-8")
    row = devpost.split("| **LangSmith** |", 1)[1].split("\n", 1)[0]
    assert "text redacted" not in row
    assert "(model, tokens, cost, time; photos, email addresses and locations removed)" in row
