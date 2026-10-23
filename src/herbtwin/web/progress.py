"""The streamed upload page (spec D58). A photo read can take about 100 s, and Cloudflare
drops a connection after ~125 s with no bytes, so the page sends a line per stage and an
HTML comment every 10 s while a stage is quiet. When the read is done the page stays put and
offers the next page with a button (21 Oct, Kash: "stay on that screen so we ask the user
to click next to find out results")."""

from __future__ import annotations

import asyncio
import contextvars
import html
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from herbtwin.advice_context import NOT_AVAILABLE
from herbtwin.answer import short_sign
from herbtwin.light import need_of
from herbtwin.pipeline import (
    CHECKING_A_PAGE,
    STOPPED_LINES,
    AdvisorReplied,
    CareFound,
    PlantFound,
    Progress,
    SeasonFound,
    TwinTested,
    WeatherFound,
    WeatherMissed,
)
from herbtwin.plant_model import is_tender
from herbtwin.receipt import ON_TF
from herbtwin.schemas import LAST_WATERED_TEXT, SOIL_FEEL_TEXT, BackupRead, about_problem
from herbtwin.stages.advise import PANEL_TEMPERATURES
from herbtwin.stages.problem import signs as problem_signs
from herbtwin.web.style import CSS, MARK

log = logging.getLogger(__name__)

Work = Callable[[Progress], str]  # gets a `say` callback, returns the next page

KEEPALIVE_S = 10.0
# Cloud Run ends a request at 300 s (the deploy's --timeout) and cuts the stream
# mid-page, so the page gives up a little before that and says so.
READ_DEADLINE_S = 270.0
TOO_LONG = "the photo read took too long"
KEEPALIVE = "<!-- still working -->\n"
PAD = 1024  # some browsers wait for about 1 KB before drawing anything
# reads run here, not on the shared request threads. A read carries on if the tab closes,
# but on Cloud Run (CPU billed per request) it may then crawl until the next request.
_READS = ThreadPoolExecutor(max_workers=8, thread_name_prefix="photo-read")


# a quiet step can last 90 s (a silent photo model, then its backup; or the advisor model
# on a busy evening, 40-90 s after the photo was done, 18 Oct): show the page is alive, and
# name the step still running, not one the page already shows as done
SLOW_S = 45
# no new step for this long: the stream may have dropped, so say the read still finishes
# (only then: the page opens on its steps, not a paragraph; 19 Oct small print, W1)
STALL_S = 45
SLOW_PHOTO = "a busy photo model can take up to 2 minutes, and we switch to a backup on our own."
SLOW_ADVICE = "the advisor model is busy right now. Its 3 answers show above as they come back."
SLOW_ANY = "this step is slow right now."
SLOW_FOR = {  # the running step (the newest line) -> what is slow
    "Reading the photo": SLOW_PHOTO,
    "Looking closer at the leaves": SLOW_PHOTO,
    "Reading the spot": SLOW_PHOTO,
    "Thinking about what it needs": SLOW_ADVICE,
    "advisor": SLOW_ADVICE,  # an advisor line: the other asks are still out
}
WAITED_JS = (
    "<script>(()=>{const t=Date.now(),p=document.getElementById('waited'),"
    f"slow={json.dumps(SLOW_FOR)},"
    "i=setInterval(()=>{if(document.querySelector('#next,.err')){clearInterval(i);"
    "p.hidden=true;return}"
    "const st=document.getElementById('stalled');"
    f"if(st&&Date.now()-(window.herbtwinAt||t)>{STALL_S}e3)st.hidden=false;"
    # no running count of seconds (21 Oct, Kash): only a slow step is worth a line, timed
    # from when that step began, so a new step clears it
    f"if(Date.now()-(window.herbtwinAt||t)<{SLOW_S}e3){{p.hidden=true;return}}p.hidden=false;"
    "const li=[...document.querySelectorAll('.progress-steps ol>li')].pop(),"
    "k=li?(li.classList.contains('advisor')?'advisor':((li.firstChild||{}).textContent||'')):'';"
    f"p.textContent='Taking longer than usual: '+(slow[k]||{json.dumps(SLOW_ANY)})"
    "},1000)})()</script>"
)


# The newest step is the one being worked on. Chrome does not re-match `li:last-of-type`
# while the list is still streaming, so each step carries a call that moves the `now` class
# onto it; without script the page falls back to `:last-of-type`, right once loaded.
NOW_JS = (
    "<script>document.documentElement.classList.add('js');window.herbtwinAt=Date.now();"
    "function herbtwinNow(){window.herbtwinAt=Date.now();"
    # a new step ends a stall: the text comes back only on the next one
    "const st=document.getElementById('stalled');if(st)st.hidden=true;"
    "const s=document.querySelectorAll('.progress-steps ol>li');"
    "s.forEach((li,i)=>li.classList.toggle('now',i===s.length-1));"
    # the step now, named at the top of the card above the questions (22 Oct site walk: on a
    # phone the steps began ~1.4 screens down). An advisor's step without its early pick,
    # which could argue with the answer
    "const n=document.getElementById('wait-now-step'),li=s[s.length-1];if(n&&li){"
    "const t=((li.firstChild||{}).textContent||'').trim();"
    "n.textContent=li.classList.contains('advisor')?t.split(':')[0]:t}"
    "if(window.herbtwinNext)herbtwinNext()}"
    # our own data for the plant (SeasonFound, WeatherFound) arrives as a step; with script
    # its card moves to the side column, without it the card stays in the list
    "function herbtwinAside(id){const e=document.getElementById(id),"
    "a=document.getElementById('wait-side');if(e&&a&&e.firstElementChild){"
    # a card said again (a place typed on the wait: its weather) takes the old one's place
    "a.querySelectorAll('.'+id).forEach(o=>o.remove());"
    "a.append(e.firstElementChild);a.hidden=false;e.remove()}}</script>"
)
NOW_CALL = "<script>herbtwinNow()</script>"

# what comes next and roughly how long it takes, under the step now (22 Oct phone walk,
# Kash: "a static wait message isn't a great user experience"). Rough times from our traces
# (23 Oct): GLM's photo read is 14 s at the median (local, n=28; 9.9 s live on 21 Oct, so
# "10 to 20"), and the 3 advisors run at once, the slowest of 3 taking 6.0 s at the median
# (Nemotron 3 Super, n=111 asks). Matched on the newest step's start, as SLOW_FOR is
ADVISORS_NEXT = f"Next: {len(PANEL_TEMPERATURES)} advisors, about 6 s"
PHOTO_NEXT = "Next: naming your plant, usually 10 to 20 s"
ANSWER_NEXT = "Next: your answer"
# a step -> what comes next, said by a call after its own line, so the page's head never
# lists steps a read may not take; any other step: the advisors are next
NEXT_FOR = {
    "Reading the photo": PHOTO_NEXT,
    "Thinking about what it needs": ANSWER_NEXT,
    CHECKING_A_PAGE: ANSWER_NEXT,
    **dict.fromkeys(STOPPED_LINES, ""),  # the read stops at the photo
}
NEXT_JS = (
    "<script>function herbtwinNext(m){const x=document.getElementById('wait-next');"
    f"if(x)x.textContent=m===undefined?{json.dumps(ADVISORS_NEXT)}:m}}</script>"
)


def _next_call(nxt: str | None) -> str:
    """What comes next after this step, when it is not the advisors (NEXT_FOR)."""
    return "" if nxt is None else f"<script>herbtwinNext({json.dumps(nxt)})</script>"


# the photo you sent, at the top of the steps from the first paint (19 Oct judge walk: the
# wait opened on an empty card). It is the small copy index.html keeps in this tab on send:
# never sent again and never given a URL. Left in place: the answer page claims it. Up to
# two more photos of the same plant (`more`) sit under it, smaller
WAIT_PHOTO = (
    '<img class="wait-photo" id="wait-photo" alt="Your photo" width="112" height="112" hidden>'
    '<span class="wait-more" id="wait-more" hidden></span>'
    "<script>(()=>{try{"
    'const p=JSON.parse(sessionStorage.getItem("herbtwin-photo-pending")||"null"),'
    'i=document.getElementById("wait-photo"),m=document.getElementById("wait-more"),'
    'ok=s=>typeof s==="string"&&s.startsWith("data:image/jpeg;base64,");'
    "if(p&&ok(p.src)&&Date.now()-p.at<6e5){i.src=p.src;i.hidden=false;"
    "(Array.isArray(p.more)?p.more:[]).filter(ok).slice(0,2).forEach((s,k)=>{"
    'const e=document.createElement("img");e.src=s;e.alt="Your photo "+(k+2);'
    "e.width=e.height=52;m.append(e)});m.hidden=!m.children.length}"
    "}catch{}})()</script>\n"  # no storage (private mode): the steps show without it
)


# the step being worked on, one line at the top of the card beside the photo, above the
# questions (22 Oct site walk, Top 5 #5: on a phone nothing in the first screen said work
# was happening). Its height never changes, so it never moves the questions; script only
WAIT_NOW = (
    '<p class="wait-now" id="wait-now"><span class="wait-now-label">Now</span>'
    '<span class="wait-now-step" id="wait-now-step">Starting on your photo</span></p>'
)
# a plant read: what comes next under it (NEXT_FOR); a spot read has steps of its own
WAIT_NEXT = f'<p class="wait-next" id="wait-next">{PHOTO_NEXT}</p>{NEXT_JS}'


def page_head(stalled: str, photo: bool = True, nexts: bool = True) -> str:
    """The first chunk: the page's head, the photo you sent, what to do if it stalls, and
    padding. `nexts`: what comes next under the step now, for a plant read."""
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
        f"<title>Working on your photo · herbtwin</title><style>{CSS}</style>{NOW_JS}</head>\n"
        # the skip link and its target, as base.html has them on every other page
        '<body class="has-band"><a class="skip" href="#content">Skip to content</a>'
        '<header class="site"><div class="wrap">'
        f'<a class="wordmark" href="/">{MARK}herbtwin</a></div></header>\n'
        # the site's look (17 Oct): the green band with the poster heading, then the steps
        # on an inked card pulled up over its edge, as on the answer page it leads to
        '<main class="progress" id="content" tabindex="-1"><div class="wrap wide">'
        '<div class="page-band">'
        "<h1>Working on your photo</h1>\n"
        '<p class="lead">Usually under a minute. Keep this page open.</p>\n'
        f'<p class="waited" id="waited" hidden></p>{WAITED_JS}'
        '<p class="vh" id="wait-said" role="status"></p></div>\n'
        # the steps, and beside them (below on a phone) our own data as it arrives
        '<div class="wait-grid"><aside class="wait-side" id="wait-side" '
        'aria-label="About your plant" hidden></aside>\n'
        '<div class="card ink band-overlap progress-steps">\n'
        + (WAIT_PHOTO if photo else "")
        + WAIT_NOW
        + (WAIT_NEXT if nexts else "")
        # hidden until a stall; without script it shows, as the only way to say it
        + f'<p class="muted" id="stalled" hidden><small>{stalled}</small></p>'
        f'<noscript><p class="muted"><small>{stalled}</small></p></noscript>\n<ol>\n'
        + "<!--"
        + " " * PAD
        + "-->\n"
    )


HEAD = page_head(
    'Stuck? The read still finishes: find it in <a href="/plants">My plants</a> in a minute or two.'
)
# signed out there is no My plants: the finished read is kept for a replay (replays.py)
SIGNED_OUT_HEAD = page_head(
    "Stuck? The read still finishes. Send the same photo again in a few minutes and the "
    "answer comes straight back."
)
# a spot read is never listed in My plants: it lives in the spot cache and the spots table
SPOT_HEAD = page_head(
    "Stuck? Try again in a minute; your photo is not kept.", photo=False, nexts=False
)
SORRY = "something went wrong on our side"


_END = (
    '</div></div></div></main>\n<footer class="foot"><div class="wrap">\n'
    # the same footer as base.html's: its wordmark and links here, the rest from the partial
    '<div class="foot-brand"><span class="foot-mark" aria-hidden="true">herbtwin</span></div>\n'
    '<nav class="foot-links" aria-label="About this site"><a href="/about">About</a>'
    '<a href="/privacy">Privacy</a><a href="/about#credits">Credits</a></nav>\n'
    + (Path(__file__).parent / "templates" / "_maker.html").read_text()
    + "</div></footer>\n</body></html>\n"
)


THINKING = "Thinking about what it needs"


def advisors_note(advisor: str | None) -> str:
    """What the advisors are (21 Oct, Kash: "what are advisors?"), under the step that asks
    them; the model is named only when it is really the one answering."""
    who = f" from {advisor}" if advisor else ""
    return f"Three independent opinions{who}. When they agree, we're surer."


# the photo models by their plain names; a model not listed is never named, and never
# by its raw id (21 Oct, judges: which model does each step?). Neither is an NVIDIA model,
# so each is said to run on Token Factory too (22 Oct, Kash)
PHOTO_MODELS = {
    "zai-org/GLM-5.3-Flash": "GLM-5.3 Flash",
    "deepseek-ai/DeepSeek-V4.1-Flash": "DeepSeek V4.1 Flash",
}
# the backup read it, not the first model (22 Oct phone walk, Kash: "Why were we using
# DeepSeek and then GLM?"): why, in plain words (schemas.BackupRead)
BACKUP_WHY = {
    "slow": "{first} was slow, so our backup {backup} read it, also " + ON_TF,
    "failed": "{first} couldn't read it, so our backup {backup} did, also " + ON_TF,
    "resting": "{first} failed recently, so our backup {backup} read it, also " + ON_TF,
}


def read_by_note(read_by: str | None, backup: BackupRead | None) -> str | None:
    """Who read the photo, as the wait and the answer's model map say it; None for a
    model we don't name."""
    if backup is not None:
        first, second = PHOTO_MODELS.get(backup.first), PHOTO_MODELS.get(backup.backup)
        if first and second:
            return BACKUP_WHY[backup.why].format(first=first, backup=second)
    model = PHOTO_MODELS.get(read_by or "")
    return f"Read by {model} {ON_TF}" if model else None


def _found_line(f: PlantFound) -> str:
    return _line(f"Found {f.name}", read_by_note(f.read_by, f.backup))


def _line(text: str, note: str | None = None) -> str:
    said = f'<span class="note">{html.escape(note, quote=False)}</span>' if note else ""
    return f"<li>{html.escape(text)}{said}</li>{NOW_CALL}{_next_call(NEXT_FOR.get(text))}\n"


# each choice as the wait names it, mid-sentence ("Advisor 1 of 3: protect it")
CHOICE = {
    "water": "water it",
    "dont_water": "hold off watering",
    "move_light": "move it to better light",
    "shelter": "protect it",
    "treat_or_remove": "treat it",
    "prune": "cut it back",
    "leave_normal": "leave it",
    "ask_first": "check first",
    "feed": "feed it",
    "repot": "repot it",
    "change_soil": "refresh the soil",
    "check_pests": "check for pests",
    "isolate": "keep it apart",
    "mulch": "mulch it",
    "humidity": "raise humidity",
    "rotate": "turn the pot",
    "other": "something else",
}
MARKS = {"better": "✓", "same": "=", "worse": "✗"}


def _twin_line(t: TwinTested) -> str:
    """The twin's verdict on each choice, the ones that beat leaving it first. The marks are
    decoration: the words say it."""
    rank = {"better": 0, "same": 1, "worse": 2}
    tests = "".join(
        f'<span class="test {v}">{html.escape(CHOICE.get(a, a).capitalize())} '
        f'<b><span aria-hidden="true">{MARKS[v]} </span>{v}</b></span>'
        for a, v in sorted(t.verdicts, key=lambda av: rank[av[1]])
    )
    n = len(t.verdicts)
    said = f"Tried {n} choice{'s' if n != 1 else ''} on your plant's twin, against leaving it"
    return f'<li class="twin">{said}<span class="tests">{tests}</span></li>{NOW_CALL}\n'


def _advisor_line(r: AdvisorReplied) -> str:
    """One advisor ask back: what it chose, and a dot per ask, filled as each lands."""
    last = r.said[-1]
    chose = CHOICE.get(last, last) if last else "no answer"
    n = len(r.said)
    dots = "".join(
        f'<i class="{"on" if a else "miss"}{" new" if i == n - 1 else ""}"></i>'
        for i, a in enumerate(r.said)
    ) + "<i></i>" * max(0, r.of - n)
    return (
        f'<li class="advisor">Advisor {len(r.said)} of {r.of}: {html.escape(chose)}'
        f'<span class="dots" aria-hidden="true">{dots}</span></li>{NOW_CALL}'
        f"{_next_call(ANSWER_NEXT)}\n"
    )


MONTHS = (
    "January February March April May June July August September October November December"
).split()
SHOWN_NORMAL = 2  # what's normal: the first few signs, so the card stays a glance


def _fact(key: str, title: str, body: str) -> str:
    """A card of our own data, as a step that moves itself beside the steps."""
    return (
        f'<li class="fact" id="fact-{key}"><section class="card wait-fact fact-{key}" '
        f'aria-labelledby="fact-{key}-h"><h2 id="fact-{key}-h">{html.escape(title)}</h2>'
        f"{body}</section></li><script>herbtwinAside('fact-{key}')</script>\n"
    )


def _plain(text: str) -> str:
    return html.escape(text[:1].upper() + text[1:])


def _problem_chip(name: str) -> str:
    """A problem to watch for: a chip that opens on what it looks like and where we read it
    (21 Oct, Kash), from data/outcomes/problem_signs_uk.json. With no signs, a plain chip."""
    row = problem_signs().get(name.lower(), {})
    looks, source = row.get("signs"), row.get("source") or ""
    if not about_problem(source, name):  # only a page about it (whitefly has none: 22 Oct)
        source = ""
    if not looks:
        return f"<li>{_plain(name)}</li>"
    site = (urlsplit(source).hostname or "").removeprefix("www.")
    more = (
        f'<p><a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">'
        f'More on {html.escape(site)}<span class="vh"> (opens in a new tab)</span></a></p>'
        if source.startswith("https://") and site
        else ""
    )
    return (
        f"<li><details><summary>{_plain(name)}</summary>"
        # one full stop, whether or not the row ends in its own
        f"<p>Looks like: {html.escape(looks.rstrip('.'))}.</p>{more}</details></li>"
    )


def _season_cards(f: SeasonFound) -> str:
    """What's normal for the plant this month, then the problems to watch for now."""
    month = MONTHS[f.month - 1]
    # each sign as the answer page lists it: the sign itself, without its add-ons
    items = "".join(f"<li>{_plain(short_sign(t))}</li>" for t in f.normal[:SHOWN_NORMAL])
    nxt = f'<p class="muted">Next: {html.escape(f.next_change)}.</p>' if f.next_change else ""
    out = _fact("normal", f"Normal for {f.name.lower()} in {month}", f"<ul>{items}</ul>{nxt}")
    if f.problems:
        names = "".join(_problem_chip(p) for p in f.problems)
        out += _fact(
            "problems",
            f"Problems to watch for in {month}",
            f'<ul class="chips">{names}</ul><p class="muted"><small>From our own plant '
            "data for this month.</small></p>",
        )
    return out


LIGHT = {"sun": "full sun", "part_shade": "part shade", "shade": "shade"}


def _degrees(c: float) -> str:
    return f"{c:g}".replace("-", "\u2212") + "&nbsp;°C"


def _care_card(f: CareFound) -> str:
    """The plant's light, water and cold, as the advisors get them (22 Oct phone walk,
    Kash: "Should get more info while waiting"). Only what the pack really says: no light
    from a lux band, and no frost line from generic thresholds (an unverified pack)."""
    pack, lines = f.pack, []
    if need := need_of(pack.sun):
        light = " or ".join(LIGHT[k] for k in LIGHT if k in need)
        lines.append(f"<li><b>Light:</b> {light}</li>")
    water = pack.water_need.strip()
    if water.lower().startswith("rhs:"):
        soil = water[4:].strip().removeprefix("moisture ").strip()
        lines.append(f"<li><b>Soil:</b> {html.escape(soil)}</li>")
    elif water.lower() in ("low", "moderate", "high"):
        lines.append(f"<li><b>Water:</b> {water.lower()} need</li>")
    if pack.verified:
        cold = "Cold" if is_tender(pack) else "Frost"
        lines.append(f"<li><b>{cold}:</b> damaged below {_degrees(pack.frost_damage_c)}</li>")
    if not lines:
        return ""
    rhs = any("rhs.org.uk" in src for src in pack.sources)
    said = "From its RHS page." if rhs else "From our own plant data."
    return _fact(
        "care",
        f"What {f.name.lower()} needs",
        f'<ul>{"".join(lines)}</ul><p class="muted"><small>{said}</small></p>',
    )


def _day(d) -> str:
    return f"{d:%a} {d.day} {d:%b}"  # "Mon 3 Nov", as the answer page writes a date


RAIN_MM = re.compile(r"(\d+(?:\.\d+)?) mm")


def _weather_card(w: WeatherFound) -> str:
    """The weather at their place: today, frost in the week ahead, the last 14 days. Rain
    today and frost nights are said in the weather blue; a mild, dry day stays plain."""
    f = w.facts
    lines = []
    if f.today and f.today != NOT_AVAILABLE:
        today = f.today.split(": ", 1)[-1]  # "6 to 13 °C, 2 mm", its date dropped
        wet = (m := RAIN_MM.search(today)) is not None and float(m.group(1)) > 0
        said = f"Today: {html.escape(today)} of rain."
        lines.append(f'<p class="wet">{said}</p>' if wet else f"<p>{said}</p>")
    if f.frost_days_ahead:
        days = ", ".join(_day(w.on + timedelta(days=d)) for d in f.frost_days_ahead)
        # a plain fact, never a warning: whether a night hurts this plant is the twin's
        # call, with the plant's own damage temperature (#334 review: hardy sage, -1 °C)
        lines.append(f'<p class="cold">Nights at or below 0&nbsp;°C: {days}.</p>')
    else:
        lines.append("<p>No nights at or below 0&nbsp;°C in the 7-day forecast.</p>")
    nights = f"{f.cold_nights_14} night{'s' if f.cold_nights_14 != 1 else ''}"
    lines.append(
        f'<p class="muted">Last 14 days: {f.rain_14_mm:.0f} mm of rain, {nights} below 5&nbsp;°C.</p>'
    )
    return _fact("weather", "Weather where you are", "".join(lines))


# the weather step's outcome when it did not come back: an amber "check first" line, never
# the green of a step done (22 Oct site walk)
WEATHER_MISSED = {
    "fetch_failed": "Weather unavailable this time",
    "no_location": "No place given: skipping the weather",
    "place_not_found": "Couldn't find that place: skipping the weather",
    "photo_too_old": "Photo taken too long ago: skipping the weather",
}


# no place, or one we could not find: the quick questions ask where it is (asks_card)
ASK_PLACE_ON = frozenset({"no_location", "place_not_found"})
ASK_PLACE = "<script>if(window.herbtwinAskPlace)herbtwinAskPlace()</script>"
# the weather is being fetched for a place we have: an unanswered place question goes
PLACE_KNOWN = "<script>if(window.herbtwinPlaceKnown)herbtwinPlaceKnown()</script>"
CHECKING_WEATHER = "Checking the weather where you are"


def _missed_line(m: WeatherMissed) -> str:
    said = WEATHER_MISSED.get(m.why, WEATHER_MISSED["fetch_failed"])
    ask = ASK_PLACE if m.why in ASK_PLACE_ON else ""
    return f'<li class="missed">{html.escape(said)}</li>{NOW_CALL}{ask}\n'


CHECKING = "Checking the advice with what you told us…"
NOT_SURE = "not_sure"
# what a reply was about, in the thanks line ({what}), so a tap on one question never reads
# as answering both; "not sure" on the soil sends no soil reading
WHAT = {"soil_feel": "the soil", "last_watered": "watering", "place": "where it is"}
ASKED_NOW = "Thanks: we'll use your answer about {what}."
ASKED_LATER = "Thanks: we'll check the advice with your answer about {what} when you open it."
# "not sure" sends no reading for that question ({none}: what we go without)
NONE = {"soil_feel": "a soil reading", "last_watered": "when you last watered"}
ASKED_NONE = "Fine: we'll go without {none}."
ASKED_KEPT = (
    "Noted. Your answer already used your first answer about {what}; change it under the answer."
)
ASK_FAILED = "That didn't send. You can tell us under your answer."
ASKED_BELOW = "Thanks: we'll use it for the plant you tap."
# the plant was already tapped and its answer took the replies (review of #504)
ASKED_TAPPED = "That came after you picked your plant: tell us again under its answer."
# the reply lines the server sends whole, as `said` (app.wait_told): the page says them as
# they are, so what a reply hears is tested without a browser (#508 review)
SAID_BY_SERVER = {"tapped": ASKED_TAPPED}
# 22 Oct site walk: one short line, so the questions start higher on a phone
STARTED = "Optional. Your answers make the advice closer."
# watering in short words, so the pills sit two to a row on a phone (22 Oct site walk);
# the same values as LAST_WATERED_TEXT, which the answer page still words in full
WATERED_SHORT = LAST_WATERED_TEXT | {
    "1_2_days": "1–2 days ago",
    "3_7_days": "3–7 days ago",
    "longer": "over a week ago",
}
# on the ready card while a quick question is still open (progress._done)
STILL_ASK = "You can still answer the questions above: we'll use them when you open your answer."
SEE_WAIT_S = 30  # "See your answer" waits this long for a late reply's check, then opens it
# the read stopped at the photo, or failed: nothing for the questions to change
DROP_ASKS = "<script>(f=>{if(f)f.hidden=true})(document.getElementById('wait-asks'))</script>"


def _choices(name: str, legend: str, choices: dict[str, str]) -> str:
    boxes = "".join(
        f'<label><input type="radio" name="{name}" value="{html.escape(v, quote=True)}"> '
        f"{_plain(text)}</label>"
        for v, text in choices.items()
    )
    return f'<fieldset><legend>{html.escape(legend)}</legend><div class="choices">{boxes}</div></fieldset>'


PLACE_ASK = "Where is it? (UK town or postcode)"
# the heading as it counts the questions: the place question shows or not
ASKS_HEAD = "While you wait: {n} quick questions"


def _place_ask(shown: bool) -> str:
    """Where the plant is, when the upload gave no place (22 Oct phone walk, Kash: "I
    thought we normally got more info": no place, so no weather, no twin and no Compare).
    Sent with its button or Enter; a place sent before the advisors start is used in this
    answer (pipeline.placed_late), after that when the answer opens, as a refine."""
    return (
        f'<fieldset class="wait-place" id="wait-place"{"" if shown else " hidden"}>'
        # named by its legend: a <label> here would draw as one of the choice pills
        f'<legend id="wait-place-l">{html.escape(PLACE_ASK)}</legend>'
        '<div class="place-row"><input type="text" id="wait-place-in" name="place" '
        'aria-labelledby="wait-place-l" maxlength="80" autocomplete="postal-code" '
        'enterkeyhint="send">'
        '<button type="submit" class="small">Use this place</button></div>'
        '<p class="muted"><small>For the weather and the twin\'s forecast.</small></p>'
        "</fieldset>"
    )


def asks_card(wait_id: str, ask_place: bool = False) -> str:
    """The quick questions, while the photo is read (21 Oct, Kash: "use the wait"). Each tap
    is sent at once; nothing waits on them. By script only: without it the form would leave
    this page, and the answer page asks the same two. `ask_place`: the upload gave no place,
    so where it is comes first; a read that finds no place asks it too (ASK_PLACE)."""
    told, see = f"/waits/{wait_id}/told", f"/waits/{wait_id}/see"
    said = json.dumps(
        {
            "now": ASKED_NOW,
            "later": ASKED_LATER,
            "below": ASKED_BELOW,
            "kept": ASKED_KEPT,
        }
    )
    return (
        f'<form class="tray wait-asks" id="wait-asks" method="post" action="{told}" hidden>'
        f'<h2 id="wait-asks-h">{ASKS_HEAD.format(n="three" if ask_place else "two")}</h2>'
        # the read starts at once and nothing waits on these (21 Oct, Kash thought it had
        # started without them): say so, and that a reply any time before the answer counts
        f'<p class="muted">{STARTED}</p>'
        + _place_ask(ask_place)
        + _choices(
            "soil_feel",
            "Push a finger 2 cm into the soil. How does it feel?",
            {**SOIL_FEEL_TEXT, NOT_SURE: "not sure"},  # as on the watering one (Kash)
        )
        + _choices("last_watered", "When did you last water it?", WATERED_SHORT)
        + '<p class="sent" role="status"></p></form>'
        "<script>(()=>{const f=document.getElementById('wait-asks');"
        "if(!f||!window.fetch||!window.FormData)return;f.hidden=false;"
        f"const p=f.querySelector('.sent'),said={said};let t=null,last=Promise.resolve();"
        # cleared, then said a beat later: a screen reader announces a repeat line again
        "const say=m=>{p.textContent='';setTimeout(()=>{p.textContent=m},60)};"
        # a short pause, so arrow keys through the choices send only where they stop
        # each line names what was sent, so a tap on one question never reads as both; "not
        # sure" on either sends no reading for it, and says what we go without
        f"const whats={json.dumps(WHAT)},nones={json.dumps(NONE)},none={json.dumps(ASKED_NONE)};"
        # an empty place is not an answer: never sent as one
        "const send=()=>{t=null;const d=new FormData(f);"
        "if(!String(d.get('place')||'').trim())d.delete('place');const n=[...d.keys()],"
        "u=n.filter(q=>d.get(q)==='not_sure'),k=n.filter(q=>d.get(q)!=='not_sure'),"
        "w=k.map(q=>whats[q]).join(' and ');"
        "last=fetch(f.action,{method:'POST',body:d,headers:{'X-Herbtwin-Fetch':'1'}})"
        ".then(r=>r.ok?r.json():{}).then(j=>{const m=said[j.counted];"
        # a line the server words itself (too late for the tapped plant: SAID_BY_SERVER) is
        # said as it is, whatever the reply was
        f"say(j.said?j.said:!m?{json.dumps(ASK_FAILED)}:j.counted==='kept'"
        "?m.replace('{what}',u.map(q=>whats[q]).join(' and '))"
        ":!w?none.replace('{none}',u.map(q=>nones[q]).join(' or ')):m.replace('{what}',w))})"
        f".catch(()=>say({json.dumps(ASK_FAILED)}));return last}};"
        # "See your answer" sends a reply still waiting first, then asks for the check
        "window.herbtwinFlush=()=>t?(clearTimeout(t),send()):last;"
        # the place's button or Enter sends at once
        "f.addEventListener('submit',e=>{e.preventDefault();"
        # an empty box and nothing chosen: nothing to send
        "if(pi&&!pi.value.trim()&&!f.querySelector('input:checked'))return;"
        f"window.herbtwinSee={json.dumps(see)};clearTimeout(t);send()}});"
        # no place came with the photo or the read: ask where it is; a place on its way
        # (the weather is being fetched) drops the question unless it was answered
        "const pl=document.getElementById('wait-place'),"
        "pi=document.getElementById('wait-place-in'),h=document.getElementById('wait-asks-h');"
        f"window.herbtwinAskPlace=()=>{{if(!pl||f.hidden)return;pl.hidden=false;"
        f"h.textContent={json.dumps(ASKS_HEAD.format(n='three'))}}};"
        "window.herbtwinPlaceKnown=()=>{if(!pl||pi.value.trim())return;pl.hidden=true;"
        f"h.textContent={json.dumps(ASKS_HEAD.format(n='two'))}}};"
        # a typed place waits for its button: each letter is not an answer
        f"f.addEventListener('change',e=>{{if(e.target===pi)return;window.herbtwinSee={json.dumps(see)};"
        "clearTimeout(t);t=setTimeout(send,400)})})()</script>"
    )


def _step(said: object, advisor: str | None = None) -> str:
    """One step as the page shows it. A step that can't be drawn is skipped: the read and
    the way on to the answer matter more than one line of the wait."""
    try:
        if isinstance(said, PlantFound):
            return _found_line(said)
        if isinstance(said, TwinTested):
            return _twin_line(said)
        if isinstance(said, AdvisorReplied):
            return _advisor_line(said)
        if isinstance(said, SeasonFound):
            return _season_cards(said)
        if isinstance(said, CareFound):
            return _care_card(said)
        if isinstance(said, WeatherFound):
            return _weather_card(said)
        if isinstance(said, WeatherMissed):
            return _missed_line(said)
        if said in STOPPED_LINES:
            return _line(str(said)) + DROP_ASKS
        if said == THINKING:
            return _line(THINKING, advisors_note(advisor))
        if said == CHECKING_WEATHER:
            return _line(CHECKING_WEATHER) + PLACE_KNOWN
        return _line(str(said))
    except Exception:  # noqa: BLE001 - a bad step must not end the page mid-stream
        log.exception("wait step could not be drawn: %r", said)
        return ""


# where a read lands -> what the page says once it is there, and the button to it. A photo
# of several plants or a plant we could not place asks first; anything else is an answer
READY = {
    "tap": ("One question first", "Tap your plant"),
    "plant": ("One question first", "Choose your plant"),
    "answer": ("Your answer is ready", "See your answer"),
}


def ready_kind(target: str) -> str:
    if target.startswith("/taps/"):
        return "tap"
    return "plant" if target.endswith("/plant") else "answer"


def _done(target: str) -> str:
    kind = ready_kind(target)
    said, button = READY[kind]
    return (
        _line("Done")
        + "</ol>\n"
        + '<div class="ready" id="ready">'
        + '<p class="ready-done">Finished reading your photo.</p>'
        + f"<h2>{said}</h2>"
        # id then href, in that order: scripts/time_reads.py and the tests find it so
        + f'<p><a id="next" href="{html.escape(target, quote=True)}" class="big">'
        + f"{button}</a></p>"
        # an answer only: a photo that asks which plant first asks these again under it
        + (
            f'<p class="ready-still" id="ready-still" hidden>{STILL_ASK}</p>'
            if kind == "answer"
            else ""
        )
        + "</div>\n"
        # no jump (Kash, 21 Oct): the band and the tab's title say it, the status line
        # tells a screen reader once, and focus stays wherever the person is typing
        + "<script>(()=>{document.querySelectorAll('.progress li.now')"
        + ".forEach(li=>li.classList.remove('now'));"
        + f"const s={json.dumps(said)},h=document.querySelector('.page-band h1'),"
        + "l=document.querySelector('.page-band .lead'),w=document.getElementById('wait-said');"
        + "if(h)h.textContent=s;if(l)l.hidden=true;if(w)w.textContent=s+'.';"
        # the line at the top of the card says it too, and stops pulsing
        + "const nw=document.getElementById('wait-now');if(nw){nw.classList.add('finished');"
        + "nw.querySelector('.wait-now-label').textContent='Done';"
        + "document.getElementById('wait-now-step').textContent=s}"
        + "const nx=document.getElementById('wait-next');if(nx)nx.hidden=true;"
        + "const r=document.getElementById('ready');"
        # docked, the page's foot clears the bar at its height now, as its lines come and go
        + "const pad=()=>{if(r&&r.classList.contains('docked'))"
        + "document.body.style.paddingBottom=r.offsetHeight+'px'};"
        # a quick question still open: the card says a reply still counts, until each has one
        + "const q=document.getElementById('wait-asks'),v=document.getElementById('ready-still'),"
        + "o=()=>{if(v)v.hidden=!q||q.hidden||[...q.querySelectorAll('fieldset')]"
        + ".every(x=>x.querySelector('input:checked'));pad()};o();"
        + "if(q)q.addEventListener('change',o);"
        # in the page, right under the steps (21 Oct, Kash: "why is it down at the bottom?");
        # docked to the foot on a phone, where the steps run past the screen, and on a
        # desktop when the card is not wholly in view (21 Oct, Kash missed it below the fold)
        + "const b=r&&r.getBoundingClientRect();"
        + "if(r&&(matchMedia('(max-width: 720px)').matches||b.top<0||b.bottom>innerHeight)){"
        + "r.classList.add('docked');"
        + "document.body.classList.add('has-dock');"
        + "pad()}"
        + "document.title=s+' · herbtwin';"
        # this page came from a POST: a reload or Back would offer to send the photo again,
        # a second paid read. So the entry becomes the next page's URL, and the tap
        # replaces it (a plain link without script; a new-tab or modified click as usual)
        + f"const u={json.dumps(target)};try{{history.replaceState(null,'',u)}}catch(e){{}}"
        + "const n=document.getElementById('next');if(n)n.addEventListener('click',e=>{"
        + "if(e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;"
        # a quick question answered after the advice started: check the advice again with
        # it first (waiting.py), then open the answer
        + "e.preventDefault();if(n.dataset.busy)return;n.dataset.busy=1;let gone=0;"
        + "const go=()=>{if(!gone){gone=1;location.replace(n.href)}};"
        + "if(!window.herbtwinSee)return go();"
        + f"n.textContent={json.dumps(CHECKING)};if(w)w.textContent={json.dumps(CHECKING)};"
        + f"setTimeout(go,{SEE_WAIT_S}e3);"
        + "Promise.resolve(window.herbtwinFlush&&window.herbtwinFlush())"
        + ".then(()=>fetch(window.herbtwinSee,{method:'POST',headers:{'X-Herbtwin-Fetch':'1'}}))"
        + ".finally(go)})})()</script>\n"
        + _END
    )


def _failed(reason: str, retry: str = "/") -> str:
    return (
        "</ol>\n"
        + DROP_ASKS
        # nothing is being worked on now: the last step stops pulsing beside the error
        + "<script>document.querySelectorAll('.progress li.now')"
        ".forEach(li=>li.classList.remove('now'));"
        # no step is being worked on: the error below says what happened
        "(e=>{if(e)e.hidden=true})(document.getElementById('wait-now'));"
        "(e=>{if(e)e.hidden=true})(document.getElementById('wait-next'))</script>\n"
        f'<p class="err">That didn\'t work: {html.escape(reason.rstrip("."))}. '
        f'<a href="{html.escape(retry, quote=True)}">Try again</a></p>\n{_END}'
    )


Settle = Callable[[], Awaitable[object]]


async def _settle(settle: Settle | None) -> None:
    """Send this request's traces while it still has CPU (D64): Cloud Run bills CPU per
    request, so after the last byte a background send may never finish."""
    if settle is None:
        return
    try:
        await settle()
    except Exception:  # noqa: BLE001 - traces never cost the person their answer
        log.exception("trace flush failed")


async def stream(
    work: Work,
    keepalive_s: float = KEEPALIVE_S,
    settle: Settle | None = None,
    extra: str = "",
    head: str = HEAD,
    retry: str = "/",  # where "Try again" starts over
    deadline_s: float = READ_DEADLINE_S,
    advisor: str | None = None,  # the advisor model's name, when it can be named
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    def post(kind: str, value: object) -> None:
        try:
            loop.call_soon_threadsafe(events.put_nowait, (kind, value))
        except RuntimeError:  # the page's loop is gone (tab closed at shutdown)
            log.info("progress dropped after the page closed: %s", kind)

    def run() -> None:
        try:
            target = work(lambda line: post("line", line))
        except HTTPException as e:
            log.warning("photo read refused: %s", e.detail)
            post("error", str(e.detail))
        except Exception:  # noqa: BLE001 - shown as a plain line; the real error is logged
            log.exception("photo read failed")
            post("error", SORRY)
        else:
            post("done", target)

    # in the request's context, so the read's traces count as this request's (D64);
    # started before the head: a closed tab can't stop it
    loop.run_in_executor(_READS, contextvars.copy_context().run, run)
    yield head
    if extra:  # a card to fill the wait (the spot answer's direction question, D67)
        yield "</ol>\n" + extra + "\n<ol>\n"
    deadline = loop.time() + deadline_s
    while True:
        left = deadline - loop.time()
        try:
            kind, value = await asyncio.wait_for(events.get(), max(0.0, min(keepalive_s, left)))
        except TimeoutError:
            if loop.time() < deadline:
                yield KEEPALIVE
                continue
            log.warning("photo read passed %.0f s; telling the page it failed", deadline_s)
            await _settle(settle)
            yield _failed(TOO_LONG, retry)
            return
        if kind == "line":
            yield _step(value, advisor)
        elif kind == "error":
            await _settle(settle)
            yield _failed(str(value), retry)
            return
        else:
            await _settle(settle)  # before the button: the next page is another request
            yield _done(str(value))
            return


def progress_response(
    work: Work,
    settle: Settle | None = None,
    extra: str = "",
    head: str = HEAD,
    retry: str = "/",
    advisor: str | None = None,
) -> StreamingResponse:
    return StreamingResponse(
        stream(work, settle=settle, extra=extra, head=head, retry=retry, advisor=advisor),
        media_type="text/html; charset=utf-8",
        # no-transform: a proxy must not buffer or recompress the stream
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )
