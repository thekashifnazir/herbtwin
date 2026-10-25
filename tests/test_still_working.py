"""Every wait that searches or re-checks shows it is working, as Claude Code does (24 Oct,
Kash: "Can't you do wait times like you do for Claude from when it starts but plant related";
Toloka study, 23 Oct: 3 of 11 found the Ask box slow): a pulsing dot, a plant word that
changes every few seconds and the seconds since it began, then what is really happening.
The running count is back on purpose (21 Oct had none). Checked in a browser with a fast
clock on 24 Oct."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from herbtwin.web.progress import page_head
from herbtwin.web.waiting_words import EVERY_S, WAIT_JS, WORDS
from tests.test_web_answer_page import _full_plan, _render

TEMPLATES = Path(__file__).parents[1] / "src/herbtwin/web/templates"


def test_the_words_are_plant_ones_and_the_count_is_from_the_start():
    assert WORDS[0] == "Germinating" and "Photosynthesising" in WORDS and len(WORDS) >= 6
    assert f"W[Math.floor(s/{EVERY_S})%W.length]" in WAIT_JS  # a new word every few seconds
    assert '"… "+s+"s"' in WAIT_JS  # seconds since it began, as Claude Code shows
    # a screen reader hears only what is really happening
    assert 'fun.setAttribute("aria-hidden","true")' in WAIT_JS
    assert "stop.say=say;return stop" in WAIT_JS  # the caller stops it, or says a new status


def test_every_wait_on_the_answer_page_uses_it(tmp_path):
    assert "<script>{{ wait_js }}</script>" in (TEMPLATES / "base.html").read_text("utf-8")
    page = _render(_full_plan(tmp_path), extras_on=True)
    assert "window.herbtwinWait=" in page  # carried in the head
    # the questions, with the search named once it starts; stopped once done
    assert "still = window.herbtwinWait(wait, [" in page and "still.say(searching);" in page
    assert "} finally {\n          still();" in page
    # Where to get it (Tavily shops)
    assert '[8, "still searching UK garden shops"]' in page
    assert "const none = () => { still();" in page
    # Tell us more's re-check, the band's town box and the card's quick questions
    assert '[20, "checking the weather and the advice again"]' in page
    assert page.count('window.herbtwinWait(b, [], {label: "Checking the advice"})') == 1
    assert page.count("if (form.still) form.still();") >= 2  # undone on the way back


def test_the_photo_wait_page_shows_it_too():
    head = page_head("stalled")
    assert '<p class="wait-tick" id="wait-tick" aria-hidden="true"></p>' in head
    assert (
        "window.herbtwinWait=" in head
        and "herbtwinWait(document.getElementById('wait-tick'))" in head
    )
    # stopped and hidden once the answer, or an error, is on the page
    assert "if(document.querySelector('#next,.err')){clearInterval(i);stop();" in head


# the helper run for real (review of #523: the pins above match its words, not what it does),
# in node with a fake page and clock; skipped where node is not installed
NODE = shutil.which("node") or next(
    (p for p in ("/opt/node22/bin/node", "/usr/local/bin/node") if Path(p).exists()), None
)
HARNESS = (
    """
let now = 0, timers = [];
Date.now = () => now;
globalThis.setInterval = (f) => { timers.push(f); return timers.length - 1; };
globalThis.clearInterval = (i) => { timers[i] = null; };
const tick = (s) => { for (let k = 0; k < s; k++) { now += 1000; timers.forEach((f) => f && f()); } };
const node = () => ({ textContent: "", attrs: {}, kids: [], parent: null,
  setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
  remove() { if (this.parent) this.parent.kids = this.parent.kids.filter((x) => x !== this); } });
globalThis.document = { createElement: () => node() };
globalThis.window = globalThis;
const el = node();
el.classList = { s: new Set(), add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); } };
el.append = (...k) => { for (const x of k) { x.parent = el; el.kids.push(x); } };
const line = () => el.kids.map((k) => k.textContent).join("");
"""
    + WAIT_JS
    + """
const out = [];
const stop = herbtwinWait(el, [[0, "thinking"], [10, () => "late " + now / 1000]], {label: "Busy"});
out.push(line(), el.attrs["aria-label"], el.kids[0].attrs["aria-hidden"]);
tick(5); out.push(line());
stop.say("searching trusted pages with Tavily"); out.push(line());
tick(5); out.push(line());
stop(); out.push(el.kids.length, el.attrs["aria-label"] === undefined, el.classList.s.has("waiting"));
tick(3); stop.say("after"); out.push(el.kids.length, timers.filter(Boolean).length);
console.log(JSON.stringify(out));
"""
)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_helper_ticks_words_and_seconds_says_its_status_and_stops_clean(tmp_path):
    script = tmp_path / "wait.js"
    script.write_text(HARNESS, "utf-8")
    run = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=30, check=True
    )
    out = json.loads(run.stdout)
    assert out[0] == "Germinating… 0s · thinking"  # from the start, the first mark's status
    assert out[1] == "Busy" and out[2] == "true"  # a label kept; the moving words hidden
    assert out[3] == "Taking root… 5s · thinking"  # a new word every 4 s, the seconds up
    assert out[4] == "Taking root… 5s · searching trusted pages with Tavily"  # said at once
    assert out[5] == "Sprouting… 10s · late 10"  # a mark's function read when it is reached
    assert out[6:9] == [0, True, False]  # stopped: the spans, the label and the class gone
    assert out[9:] == [0, 0]  # nothing left running, and saying after stop changes nothing


def test_the_status_is_never_faded_and_the_shops_word_takes_the_lilac_accent():
    # review of #523: a faded status fell under 4.5:1 on the lilac shops strip
    from herbtwin.web import style

    assert ".wait-real { opacity" not in style.CSS
    assert ".answer-page .extras-said .wait-fun { color: var(--lilac-fg); }" in style.CSS
