"""19 Oct home pass, PR 2: "Made with" (the models in view as cards, the licences folded)
and the first-load animation (the hero rises in, then the twin splits, once a session)."""

import re

from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.tracing import TraceStore
from herbtwin.web import style
from herbtwin.web.app import TEMPLATES, create_app
from tests.test_web import OCT_4
from tests.test_web_home import _home


def _home_with(tmp_path, env: dict) -> str:
    s = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12", **env})
    deps = Deps(
        observe_adapter=MockAdapter([]), advise_adapter=MockAdapter([]), settings=s,
        trace_store=TraceStore(tmp_path / "t.db"), cache_dir=tmp_path / "p", workers=1,
    )  # fmt: skip
    return TestClient(create_app(deps, clock=lambda: OCT_4)).get("/").text


def _cards(html: str) -> list[tuple[str, str]]:
    cards = html.split('<ul class="made-cards">', 1)[1].split("</ul>", 1)[0]
    return re.findall(r'<span class="job">([^<]+)</span><strong>([^<]+)</strong>', cards)


def test_made_with_shows_the_six_in_view_with_nvidia_first():
    made = str(
        TEMPLATES.env.get_template("_credits.html").module.made_with(voice_on=True, tavily_on=True)
    )
    assert _cards(made) == [
        ("Decides", "NVIDIA Nemotron 3 Super"),
        ("Reads the photo", "GLM-5.3-Flash"),
        ("Answers questions", "NVIDIA Nemotron 3 Nano"),
        ("Searches", "Tavily"),
        ("Speaks", "ElevenLabs"),
        ("Forecasts", "Open-Meteo"),
    ]
    assert "All models run on Nebius Token Factory." in made
    assert made.count('<li class="nv">') == 2  # the two NVIDIA cards carry the green tint
    # the licences stay one tap away, folded: a data table and a photo list with thumbnails
    fold = made.split('<details class="made-credits" id="credits">', 1)[1]
    assert '<dl class="made-data">' in fold and '<ul class="made-photos">' in fold
    assert re.search(r'<li><img src="/static/samples/[^"]+-thumb\.jpg"[^>]*alt=""', fold)
    assert "All downscaled, with metadata removed." in fold  # the CC change notice


def test_tavily_is_credited_only_when_search_uses_it(tmp_path):
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    off = _home_with(tmp_path / "off", {"HERBTWIN_TAVILY_API_KEY": "test-key"})  # key, switch off
    on = _home_with(
        tmp_path / "on", {"HERBTWIN_TAVILY_API_KEY": "test-key", "HERBTWIN_TAVILY_ENABLED": "1"}
    )
    assert ("Searches", "Tavily") not in _cards(off)
    assert ("Searches", "Tavily") in _cards(on)


def test_the_credits_fold_has_its_own_padding_and_stacks_on_a_phone():
    css = style.CSS
    assert ".made-with .made-credits { padding: 0 16px 16px; }" in css
    phone = css.split(".made-with .made-photos img", 1)[1]
    assert ".made-with .made-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in phone
    assert ".made-with .made-data div { grid-template-columns: 1fr; gap: 0; }" in phone


def test_the_first_load_rises_in_once_a_session_and_never_with_reduced_motion(tmp_path):
    home = _home(tmp_path)
    gate = home.split('<div class="home-band">', 1)[0]
    assert 'sessionStorage.getItem("herbtwin-intro-seen")' in gate
    assert 'matchMedia("(prefers-reduced-motion: no-preference)").matches' in gate
    assert 'root.classList.add("first-load")' in gate
    css = style.CSS
    moving = css.split("@media (prefers-reduced-motion: no-preference) { .intro-go .home-page", 1)
    assert len(moving) == 2
    block = moving[1].split("@keyframes", 1)[0]
    assert "animation: intro-rise .4s" in block and "backwards" in block
    # a move only, never a fade: the words show from the first paint (H1, 19 Oct)
    assert "@keyframes intro-rise { from { transform: translateY(16px); } }" in css
    # no pointer-events or overlay: input is live from the first frame
    assert "pointer-events" not in block


def test_on_the_first_load_the_twin_splits_instead_of_the_nudge(tmp_path):
    js = _home(tmp_path).split('const range = document.getElementById("twin-range")', 1)[1]
    js = js.split("})();", 1)[0]
    assert 'const intro = document.documentElement.classList.contains("first-load");' in js
    assert (
        'if (intro) frame.style.setProperty("--cut", "100%");' in js
    )  # opens on the healthy plant
    # 21 Oct, Kash: "make it more engaging": it sweeps 20 points past its place, so the
    # "don't" side shows properly, then settles back on the range's value; 1.4 s in all
    assert "ms = 1400" in js and "past = Math.max(0, to - 20)" in js
    assert "(1 - (1 - x) ** 3)" in js  # the settle eases out onto the value
    assert 'frame.classList.add("swept")' in js  # the grip pops once it lands
    assert "if (touched) set(); else if (intro) sweep(); else nudge();" in js  # one or the other
    sweep = js.split("const sweep = () => {", 1)[1].split("};", 1)[0]
    assert 'sessionStorage.setItem("herbtwin-slider-hinted", "1")' in sweep  # no nudge after it


def test_nemotron_ultra_is_credited_only_while_the_trusted_page_check_runs(tmp_path):
    for sub in ("on", "off", "mock"):
        (tmp_path / sub).mkdir()
    made = str(TEMPLATES.env.get_template("_credits.html").module.made_with(check_on=True))
    assert ("Checks the answer", "NVIDIA Nemotron 3 Ultra") in _cards(made)
    on = {"HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_TAVILY_ENABLED": "1",
          "HERBTWIN_SEARCH_ENABLED": "1", "HERBTWIN_BACKEND": "tokenfactory",
          "HERBTWIN_NEBIUS_API_KEY": "k", "HERBTWIN_ADVISE_MODEL": "m",
          "HERBTWIN_OBSERVE_MODEL": "m"}  # fmt: skip
    assert "Nemotron 3 Ultra" in _home_with(tmp_path / "on", on)
    off = {**on, "HERBTWIN_TRUSTED_CHECK": "0"}
    assert "Nemotron 3 Ultra" not in _home_with(tmp_path / "off", off)
    assert "Nemotron 3 Ultra" not in _home_with(tmp_path / "mock", {})
