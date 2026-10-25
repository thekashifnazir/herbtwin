"""About's "Who made it" (23 Oct, Kash yes to a redesign): a pull-quote, the facts at a glance
beside his words, a strip of figures counted from the repo. The public card that closed it
moved up to the band on 25 Oct (the About audit)."""

import ast
import re
from pathlib import Path

from herbtwin.web import style
from tests.test_web import _client

ROOT = Path(__file__).parents[1]
# the strip's figures, in one place: counted 25 Oct (527 merged pull requests; 4,863 tests
# collected) and rounded down. The pull requests are pinned here, never re-counted (the
# public repo's history isn't this one's); the tests are re-counted below
STRIP = [("500+", "merged pull requests"), ("4,800+", "automated tests"), ("1", "person")]
# a quick read of the files sees fewer than pytest collects (4,504 of 4,863 on 25 Oct: it
# misses generated cases), so it guards the figure from under: this floor keeps the strip true
QUICK_FLOOR = 4500


def _who(tmp_path) -> str:
    page = _client(tmp_path, [], []).get("/about").text
    return page.split('<h2 id="who">', 1)[1].split("</section>", 1)[0]


def test_who_made_it_leads_with_the_pull_quote_and_ends_on_the_strip(tmp_path):
    who = _who(tmp_path)
    assert (
        who.index('<p class="who-lead">One idea, one person, built end to end.</p>')
        < who.index('<div class="who-two">')
        < who.index('<ul class="who-strip"')
    )
    assert "about-close" not in who  # the public card is the band's button now
    facts = who.split('<div class="who-facts">', 1)[1].split('<div class="who-words">', 1)[0]
    for said in (
        '<p class="who-name">Kashif Nazir</p>',
        "Senior Technical Architect, London",
        "Solo build for the NVIDIA × Nebius hackathon. I attended its London event.",
        "First commit 2 Oct 2026",
    ):
        assert said in facts, said
    words = who.split('<div class="who-words">', 1)[1].split("</div>", 1)[0]
    assert words.count("<p>") == 2 and "My day job is cloud, AI strategy" in words


def test_the_profile_links_are_the_footers(tmp_path):
    # the same targets and accessible names as _maker.html, so the two can't drift apart
    who = _who(tmp_path)
    maker = (ROOT / "src/herbtwin/web/templates/_maker.html").read_text()
    links = who.split('<nav class="who-links"', 1)[1].split("</nav>", 1)[0]
    for href, label in (
        ("https://github.com/thekashifnazir", "GitHub"),
        ("https://www.linkedin.com/in/kashifnazir", "LinkedIn"),
    ):
        tag = f'href="{href}" rel="noopener noreferrer me" aria-label="{label}">'
        assert tag in maker and f'<a class="who-icon" {tag}' in links, label
    assert (
        '<a href="https://kashifnazir.com" rel="noopener noreferrer">kashifnazir.com</a>' in links
    )
    assert ".about-page .who-links a.who-icon { min-width: 44px;" in style.CSS


def test_the_strip_says_its_figures_rounded_down(tmp_path):
    strip = _who(tmp_path).split('<ul class="who-strip"', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r"<li><strong>([^<]+)</strong> ([^<]+)</li>", strip) == STRIP


def _tests_in(folder: Path) -> int:
    """The tests a quick read of the files can see: each test function, times the cases in
    any literal parametrize list. Under pytest's own count (generated cases are missed)."""
    total = 0
    for path in folder.rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                cases = 1
                for mark in node.decorator_list:
                    if (
                        isinstance(mark, ast.Call)
                        and getattr(mark.func, "attr", "") == "parametrize"
                        and len(mark.args) > 1
                        and isinstance(mark.args[1], ast.List | ast.Tuple)
                    ):
                        cases *= len(mark.args[1].elts)
                total += cases
    return total


def test_the_tests_figure_still_holds():
    # 4,185 on 23 Oct against 4,496 collected; 4,504 on 25 Oct against 4,863. Under the floor,
    # the collected count may have dropped under the strip's 4,800 and it would overclaim
    assert _tests_in(ROOT / "tests") >= QUICK_FLOOR
    assert int(STRIP[1][0].rstrip("+").replace(",", "")) <= 4863  # never above what ran


def test_the_strip_says_the_pull_requests_are_in_the_private_repo(tmp_path):
    # 23 Oct, Kash: "we are talking about all the commits and PRs but those are in our private
    # repo, not the curated public one". The band's button links the public copy, and the Devpost
    # draft stays out of it (scripts/export_public.py), so it names only the code and the reports
    who = _who(tmp_path)
    after = who.split('<ul class="who-strip"', 1)[1].split("</ul>", 1)[1].lstrip()
    assert after.startswith(
        '<p class="who-strip-note"><strong>Pull requests in the private working repo; the public'
        " repo is a curated copy of it.</strong></p>"
    )
    (tmp_path / "band").mkdir()
    page = _client(tmp_path / "band", [], []).get("/about").text
    band = page.split('<div class="page-band">', 1)[1].split("</div>", 1)[0]
    assert ">The code and test reports</a>" in band and "Devpost" not in band


def test_the_private_repo_note_is_bold_in_the_body_colour():
    # 23 Oct, Kash: bold and in the normal text colour, not muted
    css = style.CSS
    rule = css.split("p.who-strip-note {", 1)[1].split("}", 1)[0]
    assert "color:" not in rule
