"""The scroll reveal on the rest of the site (23 Oct, Kash: "Can we extend this animation to
all our pages"). The same module and the same rules as home, About and the answer
(test_web_reveal.py): blocks opt in with data-reveal, the first screen never waits, every
held state needs html.reveal-on, and a reveal moves but never fades. The wait page is not a
Jinja page and streams its steps, so its steps rise by CSS alone as each one lands, with
nothing held."""

import json
import re

import httpx
import respx

from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import style
from herbtwin.web.progress import stream
from tests.test_web import ADV, SAMPLE
from tests.test_web import _client as _web_client
from tests.test_web_accounts import _accounts_client
from tests.test_web_answer_reveal import _rules
from tests.test_web_caps import _client as _caps_client
from tests.test_web_caps import _upload as _caps_upload
from tests.test_web_history import SAGE, _signed_in, _upload
from tests.test_web_judge import CODE
from tests.test_web_judge import _client as _judge_client
from tests.test_web_progress import _collect
from tests.test_web_reveal import CSS, ON, _hooks, _reveal_rules, _script
from tests.test_web_spot import _archive, _spot
from tests.test_web_spot import _client as _spot_client

MODULE = "// the shared scroll reveal"


def _spot_page(tmp_path) -> str:
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    page = _spot(_spot_client(tmp_path)[0]).text
    climate._cache.clear()
    return page


def _plants(tmp_path, with_a_plant: bool) -> str:
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    if with_a_plant:
        _upload(c, place="")
    return c.get("/plants").text


def _limit(tmp_path) -> str:
    from herbtwin.usage import MemoryUsage

    c = _caps_client(tmp_path, {"HERBTWIN_DAILY_READS": "1"}, usage=MemoryUsage())
    _caps_upload(c)
    page = _caps_upload(c)
    assert page.status_code == 429
    return page.text


@respx.mock
def _pages(tmp_path) -> dict[str, str]:
    for d in ("s", "p", "e", "j", "k", "v", "a", "m", "l"):
        (tmp_path / d).mkdir()
    sign_in = _accounts_client(tmp_path / "a")[0]
    missing = _web_client(tmp_path / "m", [], [])
    return {
        "spot": _spot_page(tmp_path / "s"),
        "plants": _plants(tmp_path / "p", with_a_plant=True),
        "plants empty": _plants(tmp_path / "e", with_a_plant=False),
        "judge": _judge_client(tmp_path / "j").get("/judge").text,
        "judge in": _judge_client(tmp_path / "k").post("/judge", data={"code": CODE}).text,
        "privacy": _web_client(tmp_path / "v", [], []).get("/privacy").text,
        "sign in": sign_in.get("/auth/sign-in").text,
        "sign in link": sign_in.get("/auth/callback?token_hash=abc&type=email").text,
        "not found": missing.get("/no-such-page", headers={"accept": "text/html"}).text,
        "limit": _limit(tmp_path / "l"),
    }


def test_every_page_has_the_module_once_and_holds_nothing_as_served(tmp_path):
    for name, page in _pages(tmp_path).items():
        assert page.count(MODULE) == 1, name
        assert page.count(ON) == 1, name
        markup = page.replace(style.CSS, "").replace(_script(page), "")
        # only the script adds them: with no script nothing is ever held
        assert "reveal-on" not in markup and "is-in" not in markup, name


def test_each_page_reveals_its_blocks_below_the_first_screen_only(tmp_path):
    """What moves, page by page. The band and what is pulled up over its edge are the first
    screen, so they never carry a hook; a page that is all band (the emailed link, a
    missing page, the limit for today) has nothing to reveal, and that is right."""
    hooks = {name: _hooks(page) for name, page in _pages(tmp_path).items()}
    # the crop rows rise in turn as they arrive (their flags settle just after: spot.css)
    assert hooks["spot"] and set(hooks["spot"]) == {("picks tone-good", "stagger")} | (
        {("picks tone-check", "stagger")} & set(hooks["spot"])
    )
    assert hooks["plants"] == [("plant-grid", "stagger"), ("account", "rise")]
    assert hooks["plants empty"] == [("card plants-empty", "rise"), ("account", "rise")]
    assert hooks["judge"] == [("judge-picks", "stagger"), ("judge-staged", "rise")]
    assert hooks["judge in"] == hooks["judge"]
    assert hooks["privacy"] == [("privacy-text", "stagger")]
    assert hooks["sign in"] == [("muted sign-in-note", "rise")]
    for still in ("sign in link", "not found", "limit"):
        assert hooks[still] == [], still
    for name, found in hooks.items():
        for kept in ("page-band", "band-overlap", "verdict", "sheet", "spot-hero", "judge-code"):
            assert not any(kept in c for c, _ in found), (name, kept)


@respx.mock
def test_only_the_top_crop_lists_stagger_not_the_folded_rest(tmp_path):
    page = _spot_page(tmp_path)
    for tier in ("good-now", "worth-a-try"):
        if f'id="{tier}"' not in page:
            continue
        body = page.split(f'<section class="tier" id="{tier}">', 1)[1].split("</section>", 1)[0]
        top, *rest = body.split('<details class="more">', 1)
        assert top.count('data-reveal="stagger"') == 1, tier
        assert all("data-reveal" not in r for r in rest), tier  # folded rows never wait
    side = page.split('<aside class="spot-side">', 1)[1].split("</aside>", 1)[0]
    assert "data-reveal" not in side


def test_the_privacy_text_keeps_its_headings_and_lists_in_one_column(tmp_path):
    page = _web_client(tmp_path, [], []).get("/privacy").text
    text = page.split('<div class="privacy-text" data-reveal="stagger">', 1)[1]
    text = text.split("</div>\n", 1)[0]
    assert text.lstrip().startswith("<h2>What is kept</h2>")
    for h in ("Cookies", "Who processes what", "Deleting your account", "Contact"):
        assert f"<h2>{h}</h2>" in text, h
    # its first heading is a first child now (margin 0): the block keeps its 40 px instead
    assert ".privacy-page .privacy-text { margin-top: 40px; }" in style.CSS
    assert "h2 { font-size: 26px; margin-top: 40px; }" in style.CSS
    # the wrapper is what follows the band now, so it keeps the reading column
    assert ":is(.sign-in-page, .privacy-page) .page-band ~ * { max-width: var(--measure); }" in (
        style.CSS
    )


def test_a_crop_rows_flags_settle_onto_it_just_after_it_rises():
    """Each flag (Sun: part shade, Frost: …) settles from 90 % onto its row a beat after
    the row rises, one by one, so the eye lands on what is not fine about that crop. A
    scale, so the chips never shift what is round them; never a fade."""
    sheet = (style.STATIC / "pages" / "spot.css").read_text(encoding="utf-8")
    rules = [r for r in _rules(sheet) if "reveal-on" in r[1]]
    assert rules
    for at, sel, body in rules:
        assert sel.startswith("html.reveal-on .spot-page "), sel
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
        assert "opacity" not in body and "display" not in body and "height" not in body
    settle = next(b for _, s, b in rules if s.endswith(".picks > li.is-arriving .chip"))
    assert "reveal-settle .3s" in settle and "backwards" in settle
    assert "transform-origin: left" in settle
    # after its row: the row's own delay, then 160 ms, the next flag 60 ms later
    assert "calc(var(--reveal-delay, 0ms) + 160ms)" in settle
    second = next(b for _, s, b in rules if s.endswith(".chip:nth-child(2)"))
    assert "calc(var(--reveal-delay, 0ms) + 220ms)" in second
    assert "@keyframes reveal-settle { from { transform: scale(.9); } }" in sheet
    # a held crop row is the shared rise's; spot.css adds no held state of its own
    assert not any(":not(.is-in)" in s for _, s, _ in rules)


def test_the_new_reveal_rules_are_scoped_to_their_page():
    for _, sel, _ in _reveal_rules():
        if ".chip" in sel:
            assert ".spot-page " in sel, sel


# ---------- the wait page: streamed, not a Jinja page, so CSS alone ----------

WAIT = (style.STATIC / "pages" / "wait.css").read_text(encoding="utf-8")


def _step_rules() -> list[tuple[tuple[str, ...], str, str]]:
    return [r for r in _rules(WAIT) if "step-rise" in r[2]]


def test_each_streamed_step_rises_onto_the_line_as_it_lands():
    """A plain step, a missed-weather line and the error each rise 8 px as
    the browser inserts them, once, by CSS alone: there is no held state for a script to
    release, so a step is never hidden and the stream is never waited on."""
    rules = _step_rules()
    sels = [s for _, s, _ in rules]
    assert sels == [
        ".progress-steps ol > li:not(.twin, .advisor, .fact)",
        ".progress-steps > .err",
    ]
    for at, sel, body in rules:
        assert at == ("@media (prefers-reduced-motion: no-preference)",), sel
        assert body == "animation: step-rise .3s cubic-bezier(0.2,0,0,1);", sel
    assert "@keyframes step-rise { from { transform: translateY(8px); } }" in WAIT


def test_the_wait_steps_hold_nothing_and_never_fade():
    frames = WAIT.split("@keyframes step-rise {", 1)[1].split("}\n", 1)[0]
    assert "opacity" not in frames and "translateY(8px)" in frames
    # no rule sets a starting transform or hides a step: only the keyframes move it
    for _, sel, body in _rules(WAIT):
        if "progress-steps ol > li" in sel or sel.startswith(".progress-steps > .ready"):
            assert "opacity" not in body and "visibility" not in body, sel
            assert "transform" not in body or "@keyframes" in sel, sel
    # the twin's and the advisors' lines keep their own arrival, not a second one
    assert ".progress li.twin, .progress li.advisor { animation: arrive .4s ease-out both; }" in (
        WAIT
    )


def test_the_wait_page_streams_no_reveal_hooks_or_module():
    def work(say):
        say("Reading the photo")
        say("Found basil")
        return "/answers/abc"

    body = "".join(_collect(work))
    assert "<li>Reading the photo</li>" in body  # a plain step, the class the rule names
    markup = body.replace(style.CSS, "")
    assert "data-reveal" not in markup and MODULE not in markup
    assert "reveal-on" not in markup and "is-in" not in markup
    assert '<div class="ready" id="ready">' in markup


def test_the_ready_card_never_moves_so_its_dock_is_measured_true():
    """Review of part 2: _done's script measures the ready card the moment it lands, to dock
    it if it is not wholly in view; mid-rise it read 8 px low. The card does not rise."""
    assert not any(".ready" in s for _, s, _ in _step_rules())
    assert "r.getBoundingClientRect()" in "".join(_collect(lambda say: "/answers/abc"))
    assert stream  # the streamed page, not base.html


def test_every_new_rule_keeps_to_the_shared_limits():
    """16 px at most, 250 to 400 ms, transform only, on every page's new motion."""
    for name in ("step-rise", "reveal-settle"):
        frames = CSS.split(f"@keyframes {name} {{", 1)[1].split("}\n", 1)[0]
        assert "opacity" not in frames and "transform" in frames, name
        moves = [abs(int(m)) for m in re.findall(r"translate[XY]?\((-?\d+)px\)", frames)]
        assert all(m <= 16 for m in moves), name
    for _, _, body in [*_step_rules(), *[r for r in _reveal_rules() if "reveal-settle" in r[2]]]:
        secs = float(re.search(r"(?:step-rise|reveal-settle) (\.\d+)s", body)[1])
        assert 0.25 <= secs <= 0.4, body
