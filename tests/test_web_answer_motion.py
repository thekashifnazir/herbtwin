"""Design wave 1, M1 and M2 (Kash, 19 Oct: "we don't have any animations… Maybe we could
introduce some scroll effects?"): a load-in and scroll reveals, CSS only, opt-in, and never
moving text while it is read. Livelier on 21 Oct (Kash: "load in speeds… different
animations to make it more engaging"): the cards come in one after another with a bigger
rise, the Compare line draws itself and the folds slide open."""

import re

from herbtwin.web import style
from tests.test_answer_walk_fixes import _render
from tests.test_web_answer_reveal import _rules, _secs
from tests.test_web_twin_chart import _cold_basil, _record

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
OPT_IN = "prefers-reduced-motion: no-preference"
# the twin's section rises as the twin pictures did, which it now holds (23 Oct)
CARDS = ":is(.plan, .side) > :is(.seen-problem, .twin-sec, .also, .dont, .watch, .by-part, .next-step, .ask, .details)"


def _moving(sel_part):
    return [(at, s, b) for at, s, b in _rules(CSS) if sel_part in s and "animation" in b]


def _opted_in(at) -> bool:
    return any(OPT_IN in a for a in at)


def _keyframes() -> dict[str, str]:
    return dict(re.findall(r"@keyframes ([\w-]+) \{ from \{ ([^}]*) \} \}", CSS))


def test_the_band_and_the_main_card_rise_in_on_load_only_when_motion_is_welcome():
    band = _moving(".page-band > :is(.latin, .where)") + _moving(".page-band > h1")
    card = [r for r in _moving(".main-action") if r[1].endswith(".main-action")]
    assert band and card
    for at, sel, _ in band + card:
        assert _opted_in(at), sel
    assert "@keyframes band-rise { from { opacity: 0; transform: translateY(10px); } }" in CSS
    assert "@keyframes card-rise { from { opacity: 0; transform: translateY(22px); } }" in CSS


def _delay(body: str) -> float:
    """The first animation's delay: the longhand's first value, else the shorthand's second time."""
    if "animation-delay:" in body:
        return _secs(re.search(r"animation-delay: (\d*\.?\d+m?s)", body).group(1))
    first = re.split(r",(?![^()]*\))", body)[0]  # commas outside cubic-bezier(...)
    times = re.findall(r"(\d*\.?\d+m?s)\b", first)
    return _secs(times[1]) if len(times) > 1 else 0.0


def test_the_cards_in_view_on_load_come_in_one_after_another():
    # 21 Oct: the main card first, then the card under it (or, on a desktop, the right
    # column's first card), then the rest; each a little after the one before
    rules = [(at, s, b) for at, s, b in _rules(CSS) if "animation" in b and _opted_in(at)]

    def last(sel: str) -> str:
        return [b for _, s, b in rules if s == sel][-1]

    main = last(".answer-page .main-action")
    rest = last(f".answer-page {CARDS}")
    nxt = last(".answer-page .plan > .main-action + *, .answer-page .side > .ask")
    delays = [_delay(main), _delay(nxt), _delay(rest)]
    assert delays == sorted(delays) and len(set(delays)) == 3, delays
    # each card's own rise is 0.35 to 0.45 s, and the last of them is still by about 0.55 s
    # the load rise only fills backwards for the cards: still and untransformed once done
    load = [b for _, s, b in rules if s == f".answer-page {CARDS}" and "card-rise" in b]
    assert len(load) == 2  # without scroll timelines, and with them (under the reveal)
    assert all("card-rise .38s cubic-bezier(0.2,0,0,1) backwards" in b for b in load)
    lengths = [_secs(re.search(r"card-rise (\d*\.?\d+s)", b).group(1)) for b in (main, *load)]
    assert all(0.35 <= n <= 0.45 for n in lengths), lengths
    main_len, card_len = lengths[0], max(lengths[1:])
    assert round(max(delays[0] + main_len, delays[2] + card_len), 3) <= 0.55


def test_cards_below_reveal_on_scroll_and_are_still_before_they_are_read():
    reveal = [r for r in _moving(CARDS) if "card-reveal" in r[2]]
    assert len(reveal) == 1
    at, sel, body = reveal[0]
    assert _opted_in(at)
    assert any("animation-timeline: view()" in a for a in at)  # @supports: else no change
    # the load rise runs first, then the scroll's reveal; the reveal fills backwards only,
    # so a card already in view on load keeps its load rise
    assert "card-rise .38s cubic-bezier(0.2,0,0,1) backwards, card-reveal linear backwards" in body
    assert "animation-timeline: auto, view()" in body
    assert "animation-range: normal, entry 0% entry 70%" in body  # still by 70% in view
    # a rise only, never a fade (23 Oct: at .001 its words failed axe until scrolled to),
    # and never display:none or a script waiting to show it
    assert "@keyframes card-reveal { from { transform: translateY(22px); } }" in CSS
    assert ".main-action" not in sel  # the first screen is never revealed on scroll
    # on a desktop the right column's first card is on the first screen: it rises on load
    ask = [r for r in _moving(".side > .ask") if "animation-name" in r[2]]
    assert ask and ask[0][2] == "animation-name: card-rise, none;"
    assert any("min-width: 960px" in a for a in ask[0][0]) and _opted_in(ask[0][0])


def test_motion_moves_only_opacity_and_a_bounded_rise():
    frames = _keyframes()
    rises = {"band-rise", "card-rise", "card-reveal", "name-rise", "fold-open"}
    assert rises <= set(frames)
    for name in rises:
        body = frames[name]
        rise = abs(int(re.search(r"translateY\((-?\d+)px\)", body).group(1)))
        assert rise <= 24 and set(re.findall(r"([\w-]+):", body)) <= {"opacity", "transform"}
    # the cards rise a bit more than they did (16 and 14 px before 21 Oct)
    for name in ("card-rise", "card-reveal"):
        assert 20 <= int(re.search(r"translateY\((\d+)px\)", frames[name]).group(1)) <= 24
    # the ones that are not a rise: the how-sure badge's gentle scale (21 Oct, it replaced
    # the meter's fill) and the chart line's wipe
    assert frames["badge-in"] == "opacity: 0; transform: scale(.92);"
    # the line's wipe: a clip from the right, ending unclipped (no "to" fills after it ends).
    # The clip box is the line's own, so 4 px of room keeps the 3 px stroke's edges and round
    # caps, and a flat line never vanishes mid-wipe (#329 review)
    assert (
        "@keyframes line-draw { from { clip-path: inset(-4px 100% -4px -4px); }"
        " to { clip-path: inset(-4px); } }" in CSS
    )


def test_the_how_sure_badge_settles_in_and_no_meter_fills():
    # 21 Oct, gardener test: the 2-step meter read as "2 out of 2"; the words say it now
    assert "dot-fill" not in CSS and "meter-fill" not in CSS
    settle = _moving(".sure .badge")
    assert len(settle) == 1 and _opted_in(settle[0][0])
    assert "badge-in" in settle[0][2]


def test_the_compare_line_draws_itself_as_it_arrives_or_a_choice_is_tapped(tmp_path):
    page = _render(_cold_basil(_record(tmp_path)))
    svg = page.split('<figure class="twin-chart"', 1)[1].split("</svg>", 1)[0]
    lines = re.findall(r'<g class="twin-line[^"]*"[^>]*>.*?</g>', svg, flags=re.S)
    assert len(lines) >= 3
    # no pathLength: where a browser ignores it on a polyline, a dash of "1" left the line
    # dotted on iOS (21 Oct review); the wipe needs nothing on the line itself
    assert all("pathLength" not in g for g in lines)
    # the shared reveal's held line (test_web_reveal) only waits; this is the draw
    draw = [r for r in _moving("polyline") if "reveal-on" not in r[1]]
    assert len(draw) == 1
    at, sel, body = draw[0]
    assert _opted_in(at)
    # the shown line: tapping another choice moves .on and redraws. Never waiting for a fold
    # to open: since 23 Oct the chart sits in the twin's section, never in a fold
    assert sel == ".answer-page .twin-chart .twin-line.on polyline"
    assert "line-draw" in body and ".base" not in sel
    # backwards only: unclipped once drawn; and no dashes on the line, moving or not
    assert body.rstrip(";").endswith("backwards")
    assert not [r for r in _rules(CSS) if "twin-line" in r[1] and "stroke-dash" in r[2]]


def test_every_fold_slides_open():
    fold = _moving("details[open] > :not(summary)")
    assert len(fold) == 1 and _opted_in(fold[0][0])
    assert "fold-open" in fold[0][2]
    assert "@keyframes fold-open { from { opacity: 0; transform: translateY(-8px); } }" in CSS


def test_the_plant_name_never_fades_and_its_font_is_preloaded():
    # #307 review: from opacity 0 the name showed in the fallback face, then swapped
    assert "@keyframes name-rise { from { transform: translateY(10px); } }" in CSS
    h1 = next(b for _, s, b in _rules(CSS) if s.endswith(".page-band > h1") and "animation" in b)
    assert "name-rise" in h1
    base = (style.STATIC.parent / "templates" / "base.html").read_text(encoding="utf-8")
    assert (
        '<link rel="preload" href="/static/fonts/fira-condensed-800.woff2" as="font" '
        'type="font/woff2" crossorigin>'
    ) in base
