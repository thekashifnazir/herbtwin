"""The twin drawn on Compare: each choice's next 2 weeks of soil water as a line, its
cold nights as blue bands (idea 3, 18 Oct judge ideas; after Greg's "Water Level" curve).

22 Oct, Kash: the chart was not obvious to read. It says what it shows in a title, names
each line at its right end in the line's colour (no legend to decode), keeps "needs water"
clear of the lines, and marks every cold window with a snowflake under the axis.

The line for a choice is the twin run its verdict was judged on (plant_model's best of
the actions it maps to), so the picture and the "better / same" word always agree. Pure:
the template draws the SVG from these numbers, and a tap on a choice row shows its line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from herbtwin.plant_model import TIP, TWIN_FOR, _cold, is_tender, judged_by
from herbtwin.schemas import AnalysisRecord, Answer, CareAction, RiskStrip

# the SVG's own coordinates (viewBox); the page scales it to the column's width
WIDTH, HEIGHT = 340, 150
LEFT, RIGHT, TOP, BOTTOM = 34, 332, 22, 122
LABEL_MAX_X = 250  # "Frost risk Wed" still fits inside the right edge
# "Frost risk Wed if left out" starting further right would run off the edge: end it there
LEFT_OUT_START_MAX_X = 150
# a line's name sits just above it (baseline 6 up) or just below it (baseline 15 down), never
# in the cold labels' row at the top nor on the axis; two names stay a line of text apart
ABOVE, BELOW, NAME_GAP = 6.0, 15.0, 14.0
NAME_TOP, NAME_BOTTOM = TOP + 13, BOTTOM - 3
NAME_CHAR = 7.4  # a 14px bold letter's width, about, in viewBox units
NEEDS_W = 72.0  # "needs water": its width in viewBox units
KEY_CHAR = 7.1  # a key letter's width, about: "cold spells" is 78 units
MARK_Y, AXIS_Y_COLD = 139, 159  # the snowflakes' row under the axis, then the week labels
COLD_HEIGHT = 166  # the viewBox height when a snowflake row is drawn (else HEIGHT)


@dataclass(frozen=True)
class Band:
    x: float
    width: float


@dataclass(frozen=True)
class Line:
    action: CareAction
    points: str  # an SVG polyline's points: "x,y x,y ..."
    cold: list[Band]
    cold_label: str  # "Cold risk Wed", or "" when this choice has no cold night
    cold_x: float
    said: str  # the line in words, for screen readers
    left_out: tuple[float, str] = (0.0, "start")  # the faint "if left out" label: x, anchor
    name: str = ""  # the choice's short name, at the line's right end: "Protect it"
    name_y: float = 0.0
    base_name_y: float | None = None  # where "Leave it" sits while this line is drawn
    marks: tuple[float, ...] = ()  # a snowflake under the centre of each cold window
    key: tuple[float, str] | None = None  # the one "cold spells" word: x, anchor
    spell: str = "cold spell"  # "frosty spell" for a hardy plant, as the fold says (#441)
    how: str = ""  # how to read the chart while this line is drawn, under the title
    # the same, on a leave-it answer: leaving it is the advice, green and still dashed
    how_leave: str = ""


@dataclass(frozen=True)
class TwinChart:
    lines: list[Line]
    shown: CareAction  # the line drawn first: the best choice, else leaving it
    today: tuple[float, float]  # the plant's photo sits here
    needs_y: float  # the "needs water" level
    weeks: list[tuple[float, str]]  # x of "Today", "1 week", "2 weeks"
    title: str = ""  # what the chart shows, above it
    needs_label: tuple[float, float] = (0.0, 0.0)  # "needs water": x (start-anchored), y
    height: int = HEIGHT  # the viewBox's: taller when a snowflake row is drawn
    weeks_y: int = 140


def _y(mm: float, capacity: float) -> float:
    return round(BOTTOM - (BOTTOM - TOP) * min(max(mm / capacity, 0.0), 1.0), 1)


def dry_level_mm(trigger_mm: float) -> float:
    """The soil water of a dry day: water_stress at the tipping point. The twin starts to
    count stress at its watering trigger, but a dry day in Compare's rows ("dry by Saturday
    if left") is one at TIP; the dotted "needs water" line is drawn there, so the chart and
    the rows say the same (site walk 2, 22 Oct: "needs water by Thursday" over "No dry days
    or frost in the next 2 weeks")."""
    return trigger_mm * (1 - TIP)


def _said(name: str, strip: RiskStrip, cold: str, word: str) -> str:
    low = next((d for d in strip.days if d.water_stress >= TIP), None)
    water = f"needs water by {low.date:%A}" if low else "soil stays moist enough"
    return f"{name}: {water}; " + (f"{word} risk {cold}." if cold else f"no {word} risk.")


def short_name(label: str) -> str:
    """ "Protect it (shelter or bring in)" -> "Protect it": a line's name must fit its end."""
    return label.split(" (", 1)[0]


def _span(pts: list[tuple[float, float]], name: str) -> tuple[float, float]:
    """The line's highest and lowest y under its name (right-anchored at the end): a sloped
    line must clear the whole word, not only its end."""
    x0 = RIGHT - NAME_CHAR * len(name) - 4
    ys = [y for x, y in pts if x >= x0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
        if ax < x0 <= bx:
            ys.append(ay + (by - ay) * (x0 - ax) / (bx - ax))
    return min(ys), max(ys)


def _names(upper: tuple[float, float], lower: tuple[float, float]) -> tuple[float, float]:
    """The baselines of two names at the right end: the upper line's above it, the lower
    line's below it (above it too when the axis is in the way), a line of text apart; both
    under the lower line when the upper has no room above it and the two run close.
    Each line is given as its (highest, lowest) y under its name."""
    up, low = upper[0] - ABOVE, lower[1] + BELOW
    if low > NAME_BOTTOM:
        low = lower[0] - ABOVE
    if up < NAME_TOP:
        up = upper[1] + BELOW  # no room above: under its own line
        if lower[0] - upper[1] < NAME_GAP + BELOW:
            # ...unless the lower line runs too close under it: then both names go under the
            # lower line, the upper's first (25 Oct final walk: "Water it" on leaving it's
            # line, the strip and the chart alike). Far apart, each stays by its own line
            up, low = lower[1] + BELOW, lower[1] + BELOW + NAME_GAP
    a, b = sorted((up, low))
    if b - a < NAME_GAP:
        mid = (a + b) / 2
        a, b = mid - NAME_GAP / 2, mid + NAME_GAP / 2
    if a < NAME_TOP:
        a, b = NAME_TOP, NAME_TOP + NAME_GAP
    if b > NAME_BOTTOM:
        a, b = NAME_BOTTOM - NAME_GAP, NAME_BOTTOM
    first, second = (a, b) if up <= low else (b, a)
    return round(first, 1), round(second, 1)


def _crosses(pts: list[tuple[float, float]], x0: float, x1: float, y0: float, y1: float) -> bool:
    """Whether a polyline passes through the box [x0, x1] x [y0, y1]."""
    for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
        lo, hi = max(min(ax, bx), x0), min(max(ax, bx), x1)
        if lo > hi:
            continue
        if bx == ax:
            ys = (ay, by)
        else:
            ys = tuple(ay + (by - ay) * (x - ax) / (bx - ax) for x in (lo, hi))
        if min(ys) <= y1 and max(ys) >= y0:
            return True
    return False


def _needs_label(
    needs: float, today: tuple[float, float], shown: list, others: list
) -> tuple[float, float]:
    """ "needs water" just above its dotted line at the left (below it, or further along,
    when a line runs through): the drawn line and leaving it's weigh most."""
    best, score = None, None
    for x in (LEFT + 14, LEFT + 90, LEFT + 160):
        for y in (needs - 5, needs + 14):
            if y - 11 < TOP + 4 or y > BOTTOM - 2:
                continue
            box = (x, x + NEEDS_W, y - 11, y + 2)
            s = sum(10 for p in shown if _crosses(p, *box))
            s += sum(1 for p in others if _crosses(p, *box))
            if x < today[0] + 12 and abs(y - 5 - today[1]) < 16:
                s += 10  # the photo dot on Today
            if score is None or s < score:
                best, score = (x, y), s
    return best or (LEFT + 14, needs - 5)


def _you(name: str) -> str:
    """ "Protect it" -> "if you protect it"."""
    return f"if you {name[:1].lower()}{name[1:]}"


def _how(
    name: str, base_name: str, snow: bool, spell: str = "cold spell", leave_leads: bool = False
) -> str:
    """How to read the chart, from the lines actually drawn: the green one, leaving it's
    dashed one (when it is not the green one), the dotted line, and the snowflakes when
    any show (round 2, 22 Oct, Kash: "explanations"). Leaving it is always the dashed line;
    on a leave-it answer it is the green one too, the other line grey (25 Oct final walk:
    the card's strip and this chart drew the two the opposite ways)."""
    if leave_leads and base_name and base_name != name:
        said = f"Green, dashed: {_you(base_name)}. Grey: {_you(name)}."
    else:
        said = f"Green: {_you(name)}."
        if base_name and base_name != name:
            said += f" Dashed: {_you(base_name)}."
    said += " Below the dotted line, it needs water."
    # one snowflake a run of cold nights, so a spell, as the fold counts them (#441)
    return said + (f" \u2744\ufe0e marks each {spell}." if snow else "")


# the twin's reasons in plain sentences, for the Compare table only: the twin's own strings
# stay as they are, since the chat, the Also do card and the evals read them (round 2, 22 Oct)
_PLAIN = (
    (r"(cold|frost) risk (\w+) if left out; shelter avoids it", "Sheltering it avoids {1}'s {0}"),
    (
        r"(cold|frost) risk (\w+) if left out; indoors avoids it",
        "Bringing it indoors avoids {1}'s {0}",
    ),
    (r"(cold|frost) risk (\w+) if (left out|it stays out)", "{0} could harm it on {1} if {2}"),
    (r"dry by (\w+) if left", "It dries out by {0} if left alone"),
    (r"dry by (\w+) if you wait", "It dries out by {0} if you wait"),
    (r"no difference over the next (.+)", "Makes no difference in the next {0}"),
    (r"less drying than leaving it( out)?", "It dries out less than leaving it{0}"),
    (r"dries faster than leaving it", "It dries out faster than leaving it"),
    (r"stays moist without watering", "It stays moist without watering"),
    (r"extra water risks waterlogged roots", "Extra water could waterlog the roots"),
)


def _clause(text: str) -> str:
    for pattern, said in _PLAIN:
        m = re.fullmatch(pattern, text)
        if m:
            text = said.format(*(g or "" for g in m.groups()))
            break
    return text[:1].upper() + text[1:] + ("" if text.endswith((".", "!", "?")) else ".")


def plain_why(why: str) -> str:
    """ "cold risk Thursday if left out" -> "Cold could harm it on Thursday if left out."
    Sentence case and a full stop; a reason in two parts reads as two sentences."""
    why = why.strip()
    whole = next((p for p, _ in _PLAIN[:2] if re.fullmatch(p, why)), None)
    parts = [why] if whole else [c for c in why.split("; ") if c.strip()]
    return " ".join(_clause(c.strip()) for c in parts)


def _windows(cold: list[int]) -> list[tuple[int, int]]:
    """Runs of consecutive cold days, as (first, last) day indexes."""
    runs: list[tuple[int, int]] = []
    for i in cold:
        if runs and runs[-1][1] == i - 1:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def _key(marks: tuple[float, ...], spell: str = "cold spell") -> tuple[float, str] | None:
    """Where the one "cold spells" word goes in the snowflakes' row: after the first mark
    with room before the next, else before the first, else ending at the right edge."""
    if not marks:
        return None
    key_w = KEY_CHAR * len(f"{spell}s")
    for here, nxt in zip(marks, marks[1:] + (RIGHT + 8,), strict=True):
        if nxt - here - 10 >= key_w:
            return (round(here + 9, 1), "start")
    if marks[0] - LEFT - 10 >= key_w:
        return (round(marks[0] - 9, 1), "end")
    return (RIGHT, "end")


def twin_chart(rec: AnalysisRecord, labels: dict[str, str]) -> TwinChart | None:
    """None when there is nothing true to draw: no twin run, no Compare, or a record
    saved before the days carried their soil water."""
    state, answer, pack = rec.state, rec.answer, rec.pack
    if state is None or answer is None or not answer.compare or pack is None:
        return None
    by = {s.action: s for s in state.strips}
    if "do_nothing" not in by or state.needs_water_mm is None:
        return None
    base = by["do_nothing"]
    if not base.days or any(d.soil_water_mm is None for s in by.values() for d in s.days):
        return None
    word = _cold(is_tender(pack))[0]
    # the snowflakes' word, as the evidence fold counts them (fold_titles, #441)
    spell = "cold spell" if is_tender(pack) else "frosty spell"
    cap, n = state.capacity_mm, len(base.days)
    step = (RIGHT - LEFT) / n  # the start, then one point at the end of each day

    def x(i: int) -> float:
        return round(LEFT + step * i, 1)

    raw: list[tuple] = []
    for row in answer.compare:
        twins = [by[a] for a in TWIN_FOR.get(row.action, ()) if a in by]
        if not twins:
            continue
        strip = min(twins, key=judged_by(row.action))
        pts = [(x(0), _y(state.water_mm, cap))]
        pts += [(x(i + 1), _y(d.soil_water_mm or 0.0, cap)) for i, d in enumerate(strip.days)]
        days = [i for i, d in enumerate(strip.days) if d.frost >= TIP]
        cold = [Band(x(i), round(step, 1)) for i in days]
        marks = tuple(round((x(a) + x(b + 1)) / 2, 1) for a, b in _windows(days))
        first = next((d for d in strip.days if d.frost >= TIP), None)
        name = labels.get(row.action) or str(row.action)
        raw.append((row, strip, pts, cold, marks, first, name))
    left = next((r for r in raw if r[0].action == "leave_normal"), None)
    base_pts, base_name = (left[2], short_name(left[6])) if left else (None, "")
    lines: list[Line] = []
    for row, strip, pts, cold, marks, first, name in raw:
        short = short_name(name)
        here = _span(pts, short)
        if row.action == "leave_normal" or base_pts is None:
            name_y = here[0] - ABOVE if here[0] - ABOVE >= NAME_TOP else here[1] + BELOW
            base_y = None
        else:
            there = _span(base_pts, base_name)
            if pts[-1][1] <= base_pts[-1][1]:
                name_y, base_y = _names(here, there)
            else:
                base_y, name_y = _names(there, here)
        lines.append(
            Line(
                action=row.action,
                points=" ".join(f"{a},{b}" for a, b in pts),
                cold=cold,
                cold_label=f"{word.capitalize()} risk {first.date:%a}" if first else "",
                cold_x=min(cold[0].x, LABEL_MAX_X) if cold else 0.0,
                left_out=(
                    (cold[0].x, "start")
                    if cold and cold[0].x <= LEFT_OUT_START_MAX_X
                    else (RIGHT, "end")
                ),
                said=_said(name, strip, f"{first.date:%A}" if first else "", word),
                name=short,
                name_y=name_y,
                base_name_y=base_y,
                marks=marks,
                key=_key(marks, spell),
                spell=spell,
                how=_how(short, base_name, bool(marks or (left and left[4])), spell),
                how_leave=_how(
                    short, base_name, bool(marks or (left and left[4])), spell, leave_leads=True
                ),
            )
        )
    if not lines:
        return None
    better = next((r.action for r in answer.compare if r.vs_leaving_it == "better"), None)
    shown = better if better in {ln.action for ln in lines} else lines[0].action
    today, needs_y = (x(0), _y(state.water_mm, cap)), _y(dry_level_mm(state.needs_water_mm), cap)
    drawn = [r[2] for r in raw if r[0].action in (shown, "leave_normal")]
    rest = [r[2] for r in raw if r[0].action not in (shown, "leave_normal")]
    cold_any = any(ln.cold for ln in lines)
    when = "2 weeks" if n == 14 else f"{n} days"
    return TwinChart(
        lines=lines,
        shown=shown,
        today=today,
        needs_y=needs_y,
        # one line at 390px: "…over the next 2 weeks" wrapped once cold nights were named
        title=f"Soil water and cold nights, next {when}"
        if cold_any
        else f"Soil water over the next {when}",
        needs_label=_needs_label(needs_y, today, drawn, rest),
        height=COLD_HEIGHT if cold_any else HEIGHT,
        weeks_y=AXIS_Y_COLD if cold_any else 140,
        weeks=[(x(0), "Today")] + ([(x(7), "1 week")] if n > 7 else []) + [(x(n), when)],
    )


# ---------- the main card's twin strip (23 Oct, Kash: "give it a more prominent role … It's
# the whole point of the website, being the twin and what happens"; mock A) ----------
# Leaving it's line against one other choice's, cropped to the band they use, with the
# needs-water line: the chart's own numbers, never a new claim.
STRIP_X, STRIP_W = 20.0, 318.0  # the strip's viewBox runs from just left of Today to the end
STRIP_NAME_UP = 12.0  # a name's letters stand this far above its baseline
STRIP_AXIS = 16.0  # the week labels' baseline under the lowest thing drawn


@dataclass(frozen=True)
class TwinStrip:
    base: Line  # leaving it
    other: Line  # the one choice drawn against it
    lead: CareAction  # the line drawn green: the advice when it is one of the two
    view: tuple[float, float, float, float]  # the viewBox: x, y, width, height
    needs_y: float
    needs_label: tuple[float, float]
    base_name_y: float
    other_name_y: float
    today: tuple[float, float]
    weeks: list[tuple[float, str]]
    weeks_y: float
    title: str  # its label for a screen reader: soil water, and the two lines it draws


def strip_pick(chart: TwinChart, answer: Answer) -> CareAction | None:
    """The one choice the strip draws against leaving it, under the card's own twin line: the
    card's own job, so the green line is always the headline's (review of the strip, 23 Oct:
    "Water it." over a green Protect it line). Only when the card says leave it does it pick
    another: one the twin rated better, else the one whose line differs most from leaving it.
    None when the card's job has no line drawn, or there is no leave-it line to draw against."""
    by = {ln.action: ln for ln in chart.lines}
    base = by.get("leave_normal")
    main = answer.do[0].action if answer.do else None
    if base is None or main is None or main not in by:
        return None
    if main != "leave_normal":
        return main
    others = [ln for ln in chart.lines if ln.action != "leave_normal"]
    if not others:
        return None
    better = [r.action for r in answer.compare if r.vs_leaving_it == "better" and r.action in by]
    better = [a for a in better if a != "leave_normal"]
    if better:
        return better[0]
    ys = [y for _, y in _pts(base.points)]

    def gap(ln: Line) -> float:
        return sum(abs(a - b) for (_, a), b in zip(_pts(ln.points), ys, strict=False))

    return max(others, key=gap).action  # max keeps the first of equals: Compare's order


def twin_backs(answer: Answer) -> bool:
    """Whether the twin backs the card's job: leave it, or a job it rated better than leaving
    it. A "Water it." the twin rates the same as leaving it gets no strip: the card stays as it
    was, its line in its body (review of the strip, 23 Oct: the parsley sample)."""
    main = answer.do[0].action if answer.do else None
    if main == "leave_normal":
        # "Leave it, but protect it before the cold night on …" leads with leave_normal yet
        # asks for protection: a green Leave it line would not be its advice (review of #511)
        from herbtwin.answer import _headline_action  # answer imports this module

        return _headline_action(answer.headline) == "leave_normal"
    return any(r.action == main and r.vs_leaving_it == "better" for r in answer.compare)


def cold_job(chart: TwinChart, answer: Answer) -> bool:
    """Whether the card's job wins on the cold: "Bring it indoors to a bright windowsill." (a
    tender plant from October to March, our rule), or a Protect it whose line misses cold
    nights that leaving it has. The strip draws soil water only, so it gets none: its green
    Protect it line sat drier than Leave it (indoors, no rain) with no cold night to say why
    (23 Oct judge walk, a flowering basil). A Protect it that wins on drying keeps it."""
    from herbtwin.answer import TENDER_HEADLINE  # answer imports this module

    if not answer.do or answer.do[0].action != "shelter":
        return False
    if answer.headline == TENDER_HEADLINE:
        return True
    by = {ln.action: ln for ln in chart.lines}
    base, kept = by.get("leave_normal"), by.get("shelter")
    return base is not None and kept is not None and len(kept.cold) < len(base.cold)


def twin_strip(chart: TwinChart | None, answer: Answer) -> TwinStrip | None:
    """The strip's geometry from the chart's own lines, or None: no chart, the twin does not
    back the card's job, the job wins on the cold (cold_job), or no pair to draw. The green
    line is the card's job."""
    if chart is None or not twin_backs(answer) or cold_job(chart, answer):
        return None
    pick = strip_pick(chart, answer)
    if pick is None:
        return None
    by = {ln.action: ln for ln in chart.lines}
    base, other = by["leave_normal"], by[pick]
    lead = answer.do[0].action
    pts = [_pts(base.points), _pts(other.points)]
    base_y = other.base_name_y if other.base_name_y is not None else base.name_y
    needs_label = _needs_label(chart.needs_y, chart.today, pts, [])
    ys = [y for line in pts for _, y in line] + [chart.needs_y]
    top = min(*ys, base_y - STRIP_NAME_UP, other.name_y - STRIP_NAME_UP, needs_label[1] - 11)
    low = max(*ys, base_y + 3, other.name_y + 3, needs_label[1] + 3)
    top, weeks_y = round(top - 4, 1), round(low + STRIP_AXIS, 1)
    first, second = (base, other) if lead == base.action else (other, base)
    return TwinStrip(
        base=base,
        other=other,
        lead=lead,
        view=(STRIP_X, top, STRIP_W, round(weeks_y + 4 - top, 1)),
        needs_y=chart.needs_y,
        needs_label=needs_label,
        base_name_y=base_y,
        other_name_y=other.name_y,
        today=chart.today,
        weeks=chart.weeks,
        weeks_y=weeks_y,
        # soil water only: the strip draws no cold nights, whatever the chart's own title says
        title=f"Soil water over the next {chart.weeks[-1][1]}: {first.name} and {second.name}",
    )


def starting_on(chart: TwinChart, action: CareAction) -> TwinChart:
    """The chart drawn first on another of its lines (the strip's, so the card and the twin's
    section show the same pair), with "needs water" placed clear of that line, not the one it
    would have started on."""
    if action == chart.shown or action not in {ln.action for ln in chart.lines}:
        return chart
    drawn = [_pts(ln.points) for ln in chart.lines if ln.action in (action, "leave_normal")]
    rest = [_pts(ln.points) for ln in chart.lines if ln.action not in (action, "leave_normal")]
    return replace(
        chart, shown=action, needs_label=_needs_label(chart.needs_y, chart.today, drawn, rest)
    )


def _pts(points: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in (p.split(",") for p in points.split())]
