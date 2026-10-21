"""The twin drawn on Compare: each choice's next 2 weeks of soil water as a line, its
cold nights as blue bands (idea 3, 18 Oct judge ideas; after Greg's "Water Level" curve).

The line for a choice is the twin run its verdict was judged on (plant_model's best of
the actions it maps to), so the picture and the "better / same" word always agree. Pure:
the template draws the SVG from these numbers, and a tap on a choice row shows its line.
"""

from __future__ import annotations

from dataclasses import dataclass

from herbtwin.plant_model import TIP, TWIN_FOR, _cold, _peak, is_tender
from herbtwin.schemas import AnalysisRecord, CareAction, RiskStrip

# the SVG's own coordinates (viewBox); the page scales it to the column's width
WIDTH, HEIGHT = 340, 150
LEFT, RIGHT, TOP, BOTTOM = 34, 332, 22, 122
LABEL_MAX_X = 250  # "Frost risk Wed" still fits inside the right edge
# "Frost risk Wed if left out" starting further right would run off the edge: end it there
LEFT_OUT_START_MAX_X = 150


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


@dataclass(frozen=True)
class TwinChart:
    lines: list[Line]
    shown: CareAction  # the line drawn first: the best choice, else leaving it
    today: tuple[float, float]  # the plant's photo sits here
    needs_y: float  # the "needs water" level
    weeks: list[tuple[float, str]]  # x of "Today", "1 week", "2 weeks"


def _y(mm: float, capacity: float) -> float:
    return round(BOTTOM - (BOTTOM - TOP) * min(max(mm / capacity, 0.0), 1.0), 1)


def _said(name: str, strip: RiskStrip, needs: float, cold: str, word: str) -> str:
    low = next((d for d in strip.days if (d.soil_water_mm or 0.0) < needs), None)
    water = f"needs water by {low.date:%A}" if low else "soil stays moist enough"
    return f"{name}: {water}; " + (f"{word} risk {cold}." if cold else f"no {word} risk.")


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
    cap, n = state.capacity_mm, len(base.days)
    step = (RIGHT - LEFT) / n  # the start, then one point at the end of each day

    def x(i: int) -> float:
        return round(LEFT + step * i, 1)

    lines: list[Line] = []
    for row in answer.compare:
        twins = [by[a] for a in TWIN_FOR.get(row.action, ()) if a in by]
        if not twins:
            continue
        strip = min(twins, key=_peak)
        pts = [(x(0), _y(state.water_mm, cap))]
        pts += [(x(i + 1), _y(d.soil_water_mm or 0.0, cap)) for i, d in enumerate(strip.days)]
        cold = [Band(x(i), round(step, 1)) for i, d in enumerate(strip.days) if d.frost >= TIP]
        first = next((d for d in strip.days if d.frost >= TIP), None)
        name = labels.get(row.action) or str(row.action)
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
                said=_said(
                    name, strip, state.needs_water_mm, f"{first.date:%A}" if first else "", word
                ),
            )
        )
    if not lines:
        return None
    better = next((r.action for r in answer.compare if r.vs_leaving_it == "better"), None)
    shown = better if better in {ln.action for ln in lines} else lines[0].action
    return TwinChart(
        lines=lines,
        shown=shown,
        today=(x(0), _y(state.water_mm, cap)),
        needs_y=_y(state.needs_water_mm, cap),
        weeks=[(x(0), "Today")]
        + ([(x(7), "1 week")] if n > 7 else [])
        + [(x(n), "2 weeks" if n == 14 else f"{n} days")],
    )
