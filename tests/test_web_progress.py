import asyncio
import contextvars
import json
import threading
import time

from fastapi import HTTPException

from herbtwin.web.progress import KEEPALIVE, PAD, stream


def _collect(work, **kw) -> list[str]:
    async def go():
        return [chunk async for chunk in stream(work, **kw)]

    return asyncio.run(go())


def test_lines_arrive_in_order_then_the_jump():
    def work(say):
        say("Reading the photo")
        say("Found basil")
        return "/answers/abc"

    chunks = _collect(work)
    body = "".join(chunks)
    assert len(chunks[0].encode()) >= PAD  # browsers start drawing
    at = [
        body.index(s) for s in ("<li>Reading the photo", "<li>Found basil", "<li>Done", 'id="next"')
    ]
    assert at == sorted(at)
    assert '<a id="next" href="/answers/abc" class="big">See your answer</a>' in body
    assert "<h2>Your answer is ready</h2>" in body


def test_a_finished_read_waits_for_a_tap_not_a_jump():
    # 21 Oct, Kash: "stay on that screen so we ask the user to click next to find out
    # results". The band and the tab's title say it; a status line tells a screen reader
    end = _collect(lambda say: "/answers/abc")[-1]
    # no jump by itself: the only replace is inside the button's click handler
    before_click = end.split("addEventListener('click'", 1)[0]
    assert "location.replace" not in before_click and "location.href" not in end
    assert "document.title=s+' · herbtwin'" in end and "w.textContent=s+'.'" in end
    assert ".focus(" not in end  # the person may be typing an answer on this page
    assert end.index("remove('now')") < end.index("document.title")  # nothing pulses on
    assert "r.classList.add('docked')" in end  # in view wherever the person has scrolled
    assert "paddingBottom=r.offsetHeight" in end  # the bar never covers the foot


def test_the_ready_bar_docks_and_respects_reduced_motion():
    from herbtwin.web.style import CSS

    assert ".progress-steps .ready.docked { position: fixed;" in CSS
    assert "@media (prefers-reduced-motion: no-preference) { .progress-steps .ready.docked" in CSS


def test_the_step_line_and_the_current_step_ignore_the_scripts_between_steps():
    # each step is followed by its herbtwinNow() script, so `li:last-child` never matched:
    # the line ran on past the last step, and without script no step was marked
    from herbtwin.web.style import CSS

    assert ".progress ol > li:not(:last-of-type)::after" in CSS
    assert ".progress li:not(:last-child)" not in CSS and "ol:last-of-type li:last-child" not in CSS


def test_the_ready_line_and_button_follow_where_the_read_lands():
    from herbtwin.web.progress import _done

    for target, said, button in (
        ("/answers/abc", "Your answer is ready", "See your answer"),
        ("/spots/abc", "Your answer is ready", "See your answer"),
        ("/answers/abc/plant", "One question first", "Choose your plant"),
        ("/taps/abc", "One question first", "Tap your plant"),
    ):
        end = _done(target)
        assert f"<h2>{said}</h2>" in end and f'class="big">{button}</a>' in end, target


def test_the_band_has_a_status_line_for_the_ready_message():
    from herbtwin.web.progress import HEAD

    assert '<p class="vh" id="wait-said" role="status"></p>' in HEAD


def test_a_quiet_stage_gets_a_keep_alive():
    def work(say):
        time.sleep(0.25)
        return "/answers/abc"

    chunks = _collect(work, keepalive_s=0.05)
    assert KEEPALIVE in chunks[1:-1]


def test_a_crash_says_so_without_the_details(caplog):
    def work(say):
        say("Reading the photo")
        raise RuntimeError("boom secret")

    body = "".join(_collect(work))
    assert "That didn't work: something went wrong on our side. " in body
    assert '<a href="/">Try again</a>' in body
    assert "boom secret" not in body and 'id="next"' not in body
    assert "boom secret" in caplog.text


def test_a_refusal_gives_its_own_reason():
    def work(say):
        raise HTTPException(503, "History is not available right now.")

    body = "".join(_collect(work))
    assert "That didn't work: History is not available right now. " in body


def test_model_text_in_a_line_is_escaped():
    def work(say):
        say("Found <b>basil</b>")
        return "/answers/abc"

    body = "".join(_collect(work))
    assert "<b>basil</b>" not in body and "Found &lt;b&gt;basil&lt;/b&gt;" in body


def test_closing_the_page_early_does_not_stop_the_read():
    finished = threading.Event()

    def work(say):
        time.sleep(0.1)
        finished.set()
        return "/answers/abc"

    async def go():
        gen = stream(work, keepalive_s=5)
        await gen.__anext__()  # the head only, then the person closes the tab
        await gen.aclose()

    asyncio.run(go())
    assert finished.wait(2)


def _order(work, settle) -> list[str]:
    """What happened, in order: "settle" and the kind of each chunk."""
    seen: list[str] = []

    async def settling():
        seen.append("settle")
        await settle()

    async def go():
        async for chunk in stream(work, settle=settling):
            seen.append("jump" if 'id="next"' in chunk else "failed" if "didn't" in chunk else "-")

    asyncio.run(go())
    return seen


async def _nothing():
    return True


def test_traces_are_flushed_before_the_jump():
    seen = _order(lambda say: "/answers/abc", _nothing)
    assert seen.count("settle") == 1 and seen.index("settle") < seen.index("jump")


def test_traces_are_flushed_before_the_failure_line():
    def work(say):
        raise RuntimeError("boom")

    seen = _order(work, _nothing)
    assert seen.index("settle") < seen.index("failed")


def test_a_broken_flush_still_jumps(caplog):
    async def broken():
        raise RuntimeError("langsmith down")

    assert "jump" in _order(lambda say: "/answers/abc", broken)
    assert "trace flush failed" in caplog.text


def test_the_read_runs_in_the_requests_context():
    # the photo read's tracers must see the request (and so its traces get waited for)
    marker: contextvars.ContextVar[str] = contextvars.ContextVar("marker", default="none")
    marker.set("request")
    seen = []

    def work(say):
        seen.append(marker.get())
        return "/answers/abc"

    _collect(work)
    assert seen == ["request"]


def test_the_first_chunk_says_where_the_answer_goes_if_the_page_stalls():
    # a phone switching between Wi-Fi and mobile data can drop the stream mid-read; the
    # read finishes anyway, and a signed-in answer is kept in My plants
    first = _collect(lambda say: "/answers/abc")[0]
    assert 'href="/plants"' in first and "Stuck? The read still finishes" in first
    # 19 Oct small print (W1): hidden until no new step for STALL_S; shown without script
    from herbtwin.web.progress import STALL_S

    assert '<p class="muted" id="stalled" hidden>' in first and "<noscript>" in first
    assert f">{STALL_S}e3)st.hidden=false" in first
    assert "window.herbtwinAt=Date.now()" in first  # each new step resets the clock
    now = first.split("function herbtwinNow(){")[1].split("}")[0]
    assert "st.hidden=true" in now  # and hides the stall text until the next stall


def test_a_read_past_the_deadline_says_so_and_offers_a_retry():
    # Cloud Run ends a request at 300 s and cuts the stream mid-page: the page must say
    # the read failed before that, not sit on "Reading the photo" for ever.
    release = threading.Event()

    def work(say):
        say("Reading the photo")
        release.wait(5)
        return "/answers/abc"

    try:
        body = "".join(_collect(work, keepalive_s=0.05, deadline_s=0.2))
    finally:
        release.set()
    assert "That didn't work: the photo read took too long. " in body
    assert '<a href="/">Try again</a>' in body and 'id="next"' not in body


def test_the_progress_page_has_the_band_and_an_inked_steps_card():
    # 17 Oct: the streamed page was the old plain style while every page around it had the
    # green band; judges see it on every upload
    from herbtwin.web import progress

    head = progress.HEAD
    assert '<body class="has-band">' in head
    assert '<div class="page-band"><h1>Working on your photo</h1>' in head
    assert '<div class="card ink band-overlap progress-steps">' in head
    for page in (
        head + progress._line("Reading the photo") + progress._done("/answers/x"),
        head + progress._failed("the photo read took too long"),
        progress.SPOT_HEAD + progress._done("/spots/x"),
        # the spot flow puts its question form between two step lists
        progress.SPOT_HEAD + '</ol>\n<form class="tray"></form>\n<ol>\n' + progress._done("/s"),
        head + progress._failed(progress.TOO_LONG),  # the read deadline's ending
    ):
        assert page.count("<div") == page.count("</div>")  # every chunk closes what it opened
        assert "Weather data by Open-Meteo.com" in page


def test_each_streamed_step_marks_itself_the_current_one():
    # 17 Oct: Chrome does not re-match `li:last-child` while the list streams, so no step
    # was highlighted until the page had finished; each step now moves `now` onto itself
    from herbtwin.web.progress import HEAD, SPOT_HEAD

    def work(say):
        say("Reading the photo")
        say("Found basil")
        return "/answers/x"

    chunks = _collect(work)
    for line in ("Reading the photo", "Found basil", "Done"):
        assert any(c.startswith(f"<li>{line}</li><script>herbtwinNow()</script>") for c in chunks)
    for head in (HEAD, SPOT_HEAD):
        script = head.split("<script>document.documentElement.classList.add('js');", 1)[1]
        assert "function herbtwinNow()" in script.split("</script>", 1)[0]
        assert head.index("function herbtwinNow()") < head.index("<ol>")  # defined before any step


def test_the_current_step_style_follows_the_class_and_falls_back_without_script():
    from herbtwin.web.style import CSS

    fallback = "html:not(.js) .progress-steps:not(:has(> .err, > .ready)) ol:last-of-type"
    assert f".progress li.now, {fallback} > li:last-of-type {{" in CSS
    assert f".progress li.now::before, {fallback} > li:last-of-type::before {{" in CSS
    assert (
        "@media (prefers-reduced-motion: reduce) { .progress li::before { animation: none !important; } }"
        in CSS
    )


def test_a_failed_read_leaves_no_step_marked_current():
    def work(say):
        say("Reading the photo")
        raise RuntimeError("boom")

    end = _collect(work)[-1]
    assert "classList.remove('now')" in end and end.index("remove('now')") < end.index(
        'class="err"'
    )


def test_the_steps_name_no_models():
    # 21 Oct, Kash: plain step names, not "GLM-5.3-Flash reads the photo" (the 18 Oct
    # notes); the answer page and Credits still name the models
    body = "".join(_collect(lambda say: (say("Reading the photo"), "/answers/abc")[1]))
    assert "<li>Reading the photo</li>" in body and 'class="model"' not in body


def test_a_photo_read_streams_plain_steps_and_each_advisor_ask(tmp_path):
    import json

    from fastapi.testclient import TestClient

    from herbtwin.adapters.mock import MockAdapter
    from herbtwin.config import load_settings
    from herbtwin.pipeline import Deps
    from herbtwin.tracing import TraceStore
    from herbtwin.web.app import create_app
    from tests.test_web import ADV, JPEG, OBS

    env = {
        "HERBTWIN_OBSERVE_MODEL": "zai-org/GLM-5.3-Flash",
        "HERBTWIN_ADVISE_MODEL": "nvidia/nemotron-3-super-120b-a12b",
    }
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)]),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 3),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    page = TestClient(create_app(deps)).post(
        "/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}
    )
    assert "<li>Reading the photo</li>" in page.text
    assert "GLM-5.3-Flash" not in page.text and "weighs each choice" not in page.text
    # the three asks, each as it came back (idea 2, 18 Oct)
    assert page.text.count('<li class="advisor">') == 3 and "Advisor 3 of 3: " in page.text


def test_the_twins_choices_show_on_the_wait_better_first():
    # idea 2 (18 Oct): the wait shows the twin's real verdicts; words carry the meaning,
    # the marks are hidden from screen readers
    from herbtwin.pipeline import TwinTested

    tested = TwinTested((("water", "same"), ("shelter", "better"), ("move_light", "worse")))
    body = "".join(_collect(lambda say: (say(tested), "/answers/abc")[1]))
    assert "Tried 3 choices on your plant's twin, against leaving it" in body
    at = [body.index(s) for s in ("Protect it", "Water it", "Move it to better light")]
    assert at == sorted(at)
    assert '<span class="test better">Protect it <b><span aria-hidden="true">✓ </span>' in body
    assert '<span class="test worse">' in body and '<span class="test same">' in body


def test_each_advisor_ask_fills_its_dot_as_it_lands():
    from herbtwin.pipeline import AdvisorReplied

    def work(say):
        say("Thinking about what it needs")
        say(AdvisorReplied(("shelter",), 3))
        say(AdvisorReplied(("shelter", None), 3))
        say(AdvisorReplied(("shelter", None, "leave_normal"), 3))
        return "/answers/abc"

    body = "".join(_collect(work))
    one = '<i class="on new"></i><i></i><i></i>'
    two = '<i class="on"></i><i class="miss new"></i><i></i>'
    three = '<i class="on"></i><i class="miss"></i><i class="on new"></i>'
    lines = [
        f'Advisor 1 of 3: protect it<span class="dots" aria-hidden="true">{one}</span>',
        f'Advisor 2 of 3: no answer<span class="dots" aria-hidden="true">{two}</span>',
        f'Advisor 3 of 3: leave it<span class="dots" aria-hidden="true">{three}</span>',
    ]
    at = [body.index(s) for s in ["<li>Thinking about what it needs", *lines, "<li>Done"]]
    assert at == sorted(at)
    assert body.count('<li class="advisor">') == 3


def test_every_choice_has_words_on_the_wait():
    from herbtwin.schemas import CARE_ACTIONS
    from herbtwin.web.progress import CHOICE

    assert set(CHOICE) == set(CARE_ACTIONS)


def test_the_new_lines_arrive_still_for_reduced_motion():
    from herbtwin.web.style import STATIC

    css = (STATIC / "pages" / "wait.css").read_text()
    reduce = css[css.index("prefers-reduced-motion: reduce") :]
    assert ".progress li.advisor" in reduce and "animation: none" in reduce


def test_a_step_that_cannot_be_drawn_still_reaches_the_answer(caplog):
    from herbtwin.pipeline import TwinTested

    def work(say):
        say(TwinTested((("water", "odd"),)))  # a verdict the page has no mark for
        say("Thinking about what it needs")
        return "/answers/abc"

    body = "".join(_collect(work))
    assert "Thinking about what it needs" in body and '<a id="next" href="/answers/abc"' in body
    assert "wait step could not be drawn" in caplog.text


def test_the_slow_line_names_the_step_still_running():
    # 18 Oct pre-deploy: the advisors took 40-90 s after the photo step was done, and the
    # page said "a busy photo model can take up to 2 minutes" beside a finished photo step
    from herbtwin.web import progress

    assert progress.SLOW_FOR["Reading the photo"] == progress.SLOW_PHOTO
    assert progress.SLOW_FOR["Thinking about what it needs"] == progress.SLOW_ADVICE
    assert progress.SLOW_FOR["advisor"] == progress.SLOW_ADVICE  # an advisor line is newest
    js = progress.WAITED_JS
    assert json.dumps(progress.SLOW_FOR) in js and "classList.contains('advisor')" in js
    assert "photo model" not in js.replace(json.dumps(progress.SLOW_FOR), "")  # map only
    # the newest step's own words, before its model note; an advisor line by its class
    assert "k=li?(li.classList.contains('advisor')?'advisor':((li.firstChild||{}).textContent" in js
    for said in (json.dumps(progress.SLOW_FOR), json.dumps(progress.SLOW_ANY)):
        assert "</" not in said and "<!--" not in said  # never ends the script early


def test_the_wait_page_footer_has_the_site_footers_links():
    # 19 Oct small-print recheck: the streamed page's footer had no Credits link
    import re
    from pathlib import Path

    from herbtwin.web import progress

    base = (Path(progress.__file__).parent / "templates" / "base.html").read_text()
    site = re.findall(
        r'<a href="([^"]+)"', base.split('<footer class="foot">')[1].split("</footer>")[0]
    )
    wait = re.findall(r'<a href="([^"]+)"', progress._END.split('<footer class="foot">')[1])
    assert wait == site and "/about" in wait and "/about#credits" in wait


def test_the_wait_shows_the_photo_back_from_the_first_paint():
    # judge finding #10, 19 Oct: the wait opened on an empty card and never showed the photo
    # back. The photo comes from the tab's own copy (index.html keeps it on send), so it is
    # never sent again or given a URL; the answer page claims that copy, so it stays put
    from herbtwin.web import progress

    for head in (progress.HEAD, progress.SIGNED_OUT_HEAD):
        card = head.split('<div class="card ink band-overlap progress-steps">\n', 1)[1]
        assert card.startswith('<img class="wait-photo" id="wait-photo" alt="Your photo"')
        img = card.split(">", 1)[0]
        assert " hidden" in img and " src=" not in img  # shown only where the tab has a copy
        script = card.split("<script>", 1)[1].split("</script>", 1)[0]
        assert 'sessionStorage.getItem("herbtwin-photo-pending")' in script
        assert 'startsWith("data:image/jpeg;base64,")' in script
        assert "removeItem" not in script  # the answer page after the wait claims it
        assert card.index("</script>") < card.index("<ol>")  # before the first step
    assert 'id="wait-photo"' not in progress.SPOT_HEAD  # a bed photo has no answer page copy


def test_the_wait_photo_has_its_own_small_square_rule():
    from herbtwin.web.style import CSS

    assert ".progress-steps .wait-photo {" in CSS
    assert ".progress-steps:has(> .wait-photo:not([hidden])) { display: flow-root; }" in CSS


def test_the_ready_page_never_offers_to_send_the_photo_again():
    # #328 review: the old jump replaced the POST page in history; a plain link keeps it,
    # so Back or a reload would offer to resend the form, a second paid read
    end = _collect(lambda say: "/answers/abc")[-1]
    assert """const u="/answers/abc";try{history.replaceState(null,'',u)}""" in end
    click = end.split("n.addEventListener('click',e=>{", 1)[1].split("</script>", 1)[0]
    assert "e.preventDefault();" in click and "gone=1;location.replace(n.href)" in click
    assert ".finally(go)" in click  # after a late reply's refine too: never a plain link
    assert "e.metaKey||e.ctrlKey" in click  # a new-tab click still opens a new tab
    assert '<a id="next" href="/answers/abc"' in end  # the plain link without script


def _season(problems=("basil downy mildew",), month=10):
    from herbtwin.pipeline import SeasonFound

    return SeasonFound(
        "Basil", month, ("leaves <b>blacken</b> after cold (below 10 C); the end of it", "woody stems", "a third"),
        "sow again from March", problems,
    )  # fmt: skip


def _weather(frost=(3, 13), today="Tue 21 Oct: 6 to 13 °C, 2 mm"):
    from datetime import date

    from herbtwin.advice_context import WeatherFacts
    from herbtwin.pipeline import WeatherFound

    facts = WeatherFacts(31.4, 8, 12.6, 1, 1.2, today, [], list(frost))
    return WeatherFound(date(2026, 10, 21), facts)


def test_our_own_data_shows_as_cards_that_move_beside_the_steps():
    # 21 Oct, Kash: while waiting, show our own data (season, problems, weather), never raw
    # web text. Each card is a step that moves itself into the side column with script
    body = "".join(_collect(lambda say: (say(_season()), say(_weather()), "/answers/a")[2]))
    for key in ("normal", "problems", "weather"):
        assert (
            f'<li class="fact" id="fact-{key}"><section class="card wait-fact fact-{key}"' in body
        )
        assert f"herbtwinAside('fact-{key}')" in body
    assert '<aside class="wait-side" id="wait-side" aria-label="About your plant" hidden>' in body
    assert '<h2 id="fact-normal-h">Normal for basil in October</h2>' in body
    assert "<li>Leaves &lt;b&gt;blacken&lt;/b&gt; after cold</li><li>Woody stems</li></ul>" in body
    assert "A third" not in body  # a glance: the first two signs
    assert "Next: sow again from March." in body
    assert "Problems to watch for in October" in body
    assert "<summary>Basil downy mildew</summary>" in body
    assert ">Today: 6 to 13 °C, 2 mm of rain.</p>" in body
    assert ">Nights at or below 0&nbsp;°C: Sat 24 Oct, Tue 3 Nov.</p>" in body
    assert "risk" not in body.split('id="fact-weather"', 1)[1]  # a fact, not a warning
    assert "Last 14 days: 31 mm of rain, 1 night below 5&nbsp;°C." in body
    assert body.count("<div") == body.count("</div>")


def test_no_problems_this_month_means_no_problems_card_and_no_frost_says_so():
    body = "".join(
        _collect(lambda say: (say(_season(problems=())), say(_weather(frost=())), "/a/b")[2])
    )
    assert "fact-problems" not in body and "fact-normal" in body
    assert "No nights at or below 0&nbsp;°C in the 7-day forecast." in body


def test_a_missing_today_is_left_out_of_the_weather_card():
    from herbtwin.advice_context import NOT_AVAILABLE

    body = "".join(_collect(lambda say: (say(_weather(today=NOT_AVAILABLE)), "/a/b")[1]))
    assert "Today:" not in body and "Weather where you are" in body


def test_the_side_column_script_moves_the_card_and_shows_the_column():
    from herbtwin.web.progress import HEAD

    script = HEAD.split("function herbtwinAside(id){", 1)[1].split("</script>", 1)[0]
    assert "a.append(e.firstElementChild);a.hidden=false;e.remove()" in script
    assert HEAD.index("function herbtwinAside") < HEAD.index("<ol>")


def test_the_ready_card_sits_under_the_steps_and_docks_on_a_phone_or_when_out_of_view():
    # 21 Oct, Kash on a desktop: "why is it down at the bottom?"; then, on rev 00050, did
    # not see it had finished: the card was below the fold and the page does not follow
    from herbtwin.web.progress import _done
    from herbtwin.web.style import CSS

    end = _done("/answers/abc")
    assert (
        '<div class="ready" id="ready"><p class="ready-done">Finished reading your photo.</p>'
        in end
    )
    assert "const b=r&&r.getBoundingClientRect();" in end
    assert (
        "if(r&&(matchMedia('(max-width: 720px)').matches||b.top<0||b.bottom>innerHeight)){"
        "r.classList.add('docked');" in end
    )
    assert "scrollIntoView" not in end and ".focus(" not in end  # never yanks the page
    assert (
        ".progress-steps .ready { margin: 20px 0 4px; padding: 16px 20px; border: 2px solid" in CSS
    )


def test_the_advisors_step_says_what_they_are_and_shows_calls_only():
    # 21 Oct safety review for FINAL: an advisor's own sentence can carry a home spray or a
    # hard cut the answer page would later drop, so the wait shows each call, never its words
    from herbtwin.pipeline import AdvisorReplied
    from herbtwin.web.progress import THINKING

    def work(say):
        say(THINKING)
        say(AdvisorReplied(("prune",), 3))
        return "/answers/abc"

    body = "".join(_collect(work, advisor="NVIDIA Nemotron 3 Super"))
    assert (
        '<li>Thinking about what it needs<span class="note">Three independent opinions from '
        "NVIDIA Nemotron 3 Super. When they agree, we're surer.</span></li>"
    ) in body
    assert '<li class="advisor">Advisor 1 of 3: cut it back<span class="dots"' in body
    assert 'class="why"' not in body
    assert not hasattr(AdvisorReplied(("prune",), 3), "why")  # no words to show
    plain = "".join(_collect(lambda say: (say(THINKING), "/a")[1]))
    assert "Three independent opinions. When they agree" in plain  # no model named


def test_a_problem_chip_opens_on_what_it_looks_like_and_its_source():
    # 21 Oct, Kash: the chips should say what each problem looks like, with a link to read more
    season = _season(problems=("basil downy mildew", "nonesuch"))
    body = "".join(_collect(lambda say: (say(season), "/a/b")[1]))
    chips = body.split('<ul class="chips">', 1)[1].split("</ul>", 1)[0]
    assert chips.startswith(
        "<li><details><summary>Basil downy mildew</summary><p>Looks like: yellow patches"
    )
    assert (
        '<a href="https://hort.extension.wisc.edu/articles/basil-downy-mildew-2/" '
        'target="_blank" rel="noopener">More on hort.extension.wisc.edu'
        '<span class="vh"> (opens in a new tab)</span></a>' in chips
    )
    assert "<li>Nonesuch</li>" in chips  # no signs entry: a plain chip


def test_a_problem_chip_is_a_44px_tap_and_opens_to_the_cards_width():
    from herbtwin.web.style import CSS

    assert ".wait-fact .chips summary { min-height: 44px;" in CSS
    assert ".wait-fact .chips details a { display: inline-flex; align-items: center; min-height: 44px;" in CSS  # fmt: skip
    assert ".wait-fact .chips li:has(> details[open]) { flex-basis: 100%;" in CSS


def test_rain_and_frost_take_the_weather_blue_and_a_mild_dry_day_stays_plain():
    wet = "".join(_collect(lambda say: (say(_weather()), "/a/b")[1]))
    assert '<p class="wet">Today: 6 to 13 °C, 2 mm of rain.</p>' in wet
    assert '<p class="cold">Nights at or below 0&nbsp;°C: Sat 24 Oct, Tue 3 Nov.</p>' in wet
    dry = _weather(frost=(), today="Tue 21 Oct: 9 to 15 °C, 0 mm")
    mild = "".join(_collect(lambda say: (say(dry), "/a/b")[1]))
    assert "<p>Today: 9 to 15 °C, 0 mm of rain.</p>" in mild
    assert 'class="wet"' not in mild and 'class="cold"' not in mild


def test_the_normal_and_weather_cards_carry_their_colour_at_aa_in_light_and_dark():
    from herbtwin.web.style import CSS
    from tests.test_web_home import _contrast, _tokens

    body = "".join(_collect(lambda say: (say(_season()), say(_weather()), "/a/b")[2]))
    assert '<section class="card wait-fact fact-normal"' in body
    assert '<section class="card wait-fact fact-weather"' in body
    assert ".wait-fact.fact-normal h2 { color: var(--ok); }" in CSS
    assert ".wait-fact.fact-weather h2 { color: var(--sky-fg); }" in CSS
    assert ".wait-fact .wet { color: var(--sky-fg);" in CSS
    assert ".wait-fact .cold { padding: 6px 10px; border-radius: 8px; background: var(--sky); color: var(--sky-fg);" in CSS  # fmt: skip
    card, ok, sky, sky_fg = (_tokens(t)[:2] for t in ("card", "ok", "sky", "sky-fg"))
    for theme in (0, 1):  # light, dark
        assert _contrast(ok[theme], card[theme]) >= 4.5
        assert _contrast(sky_fg[theme], card[theme]) >= 4.5
        assert _contrast(sky_fg[theme], sky[theme]) >= 4.5


def test_the_ready_card_says_the_questions_still_count_while_one_is_open():
    # 21 Oct, Kash: the answer was ready before they had answered both questions
    from herbtwin.web.progress import _done

    end = _done("/answers/abc")
    assert (
        '<p class="ready-still" id="ready-still" hidden>You can still answer the questions '
        "above: we'll use them when you open your answer.</p></div>" in end
    )
    script = end.split("<script>", 1)[1]
    assert "v.hidden=!q||q.hidden||[...q.querySelectorAll('fieldset')]" in script
    assert ".every(x=>x.querySelector('input:checked'));pad()};o();" in script
    assert script.index("o();") < script.index("r.classList.add('docked')")  # before it docks
    # a photo that asks which plant first asks these again under its answer
    assert "ready-still" not in _done("/taps/abc").split("<script>", 1)[0]


def test_a_signs_row_ending_in_a_full_stop_gets_one_not_two(monkeypatch):
    # #369 review: "Looks like: …" added its own full stop after the row's
    from herbtwin.web import progress

    row = {"signs": "white spots.", "source": "https://www.rhs.org.uk/disease/x"}
    monkeypatch.setattr(progress, "problem_signs", lambda: {"mould": row})
    assert "<p>Looks like: white spots.</p>" in progress._problem_chip("mould")


def test_the_docked_bar_keeps_the_foot_clear_as_its_still_ask_line_hides():
    # #369 review: the foot's padding was set once, so it stayed a line too tall once the
    # last question was answered and "You can still answer…" hid
    from herbtwin.web.progress import _done

    script = _done("/answers/abc").split("<script>", 1)[1]
    assert (
        "const pad=()=>{if(r&&r.classList.contains('docked'))"
        "document.body.style.paddingBottom=r.offsetHeight+'px'};" in script
    )
    assert "input:checked'));pad()};" in script  # each change of the line re-measures
    assert script.count("paddingBottom=") == 1  # and docking uses the same measure
    assert "document.body.classList.add('has-dock');pad()}" in script


def test_the_found_step_names_the_photo_model_by_its_plain_name_only():
    # 21 Oct (judging video, 32:38): which model read the photo, never a raw model id
    from herbtwin.pipeline import PlantFound
    from herbtwin.web.progress import _step

    glm = _step(PlantFound("basil", "zai-org/GLM-5.3-Flash"))
    assert glm.startswith('<li>Found basil<span class="note">Read by GLM-5.3 Flash</span></li>')
    backup = _step(PlantFound("basil", "deepseek-ai/DeepSeek-V4.1-Flash"))
    assert '<span class="note">Read by DeepSeek V4.1 Flash</span>' in backup
    for unnamed in ("mock", "some/new-model", None):
        line = _step(PlantFound("basil", unnamed))
        assert line.startswith("<li>Found basil</li>") and "Read by" not in line
