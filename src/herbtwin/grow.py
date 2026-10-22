"""What could I grow here now? (spot spec section 7, D72). Pure code over the crop
calendar: the month's window, hard filters (container, sun, frost, hardiness, mild areas,
pH), a soil demotion, two tiers, and the source disagreements shown. No model call ranks
or writes the list; every line is built from the row's facts."""

from __future__ import annotations

import calendar as cal
from dataclasses import dataclass, replace

from herbtwin.crops import RATING_MIN_C, SOURCE_NAMES, Crop
from herbtwin.schemas import (
    FrostNormals,
    GrowList,
    GrowPick,
    LightClass,
    PhRange,
    PickAction,
    PickChip,
    PotSize,
    SpotSetting,
    SunHours,
    TexturePrior,
)
from herbtwin.sun import class_of

FROST_NIGHTS = 0.5  # a frost-tender crop goes out only below this many air frosts a month
MILD_AIR_FROST = 30.0  # air-frost nights a year at or below which a place is a mild area
CLAY_LINE = 0.5  # P(clayey) at or above which soil-sensitive crops are demoted
ACID_LINE = 6.0
PER_TIER = 8
SUN_MARGIN_H = 1.0  # June hours over the crop's class threshold that count as comfortable
POT_LITRES: dict[str, float | None] = {"small": 5, "medium": 20, "large": None}
POT_DEPTH_CM: dict[str, float | None] = {"small": 15, "medium": 25, "large": None}
NEED: dict[str, LightClass] = {
    "full": "sun",
    "full_or_part": "part_shade",
    "part_or_shade": "shade",
}
NEED_HOURS = {"full": 6.0, "full_or_part": 3.0, "part_or_shade": 0.0}
NEED_TEXT = {"full": "full sun (6 h in June)", "full_or_part": "at least part shade (3 h in June)"}
RANK = {"shade": 0, "part_shade": 1, "sun": 2}
OVER_WINTER = frozenset({9, 10, 11, 12, 1, 2})  # an outdoor start these months sits out the winter
DO = {
    "sow_outdoors": "Sow outdoors",
    "plant_out": "Plant out",
    "sow_indoors": "Start on a windowsill",
}
WINDOW_OF = {"sow_outdoors": "sow", "sow_indoors": "sow", "plant_out": "plant_out"}
WARM_SEASONS = frozenset({2026})
WARM_NOTE = (
    "This season is running warm (Met Office record), so sowing and planting dates may run late."
)
OUTSIDE_UK = "The planting calendar is for the UK, so there is no list for this place."
NO_CALENDAR = "The planting calendar is not available right now."
WINDOWSILL_NOTE = "A windowsill gets the any-time crops only; there is no sun estimate indoors."
DARK_H = 0.5  # clear-day hours at or under this show as 0 in the spot card's table
DARK_AHEAD = 3  # the dark-months note shows when this month or the next two are dark
TIER_RANK = {"good": 0, "try": 1, "out": 2}
DISAGREE_SOURCES = ("rhs_raw", "garden_organic")


BASE_LAST_FROST = 4  # mid-England: the last month with 0.5+ air-frost nights (calendar baseline)
BASE_FIRST_FROST = 10  # and the first in autumn


def _frost_late(by_month: list[float], window: frozenset[int], m: int) -> bool:
    """A tender crop's outdoor month is too early (or too late) here when it falls in the
    first (last) months of its window by as many months as this spot's last spring (first
    autumn) frost is later (earlier) than the baseline; outside the window, the plain rule."""
    if by_month[m - 1] < FROST_NIGHTS:
        return False
    if m not in window:
        return True
    spring = [i + 1 for i in range(6) if by_month[i] >= FROST_NIGHTS]
    autumn = [i + 1 for i in range(6, 12) if by_month[i] >= FROST_NIGHTS]
    lag = max(0, (max(spring) if spring else 0) - BASE_LAST_FROST)
    lead = max(0, BASE_FIRST_FROST - (min(autumn) if autumn else 13))
    early = any((m - k - 2) % 12 + 1 not in window for k in range(lag))
    late = any((m + k) % 12 + 1 not in window for k in range(lead))
    return early or late


@dataclass(frozen=True)
class GrowSpot:
    month: int
    year: int
    setting: SpotSetting
    pot_size: PotSize = "unknown"
    sun: SunHours | None = None
    frost: FrostNormals | None = None
    ph: PhRange | None = None
    texture: TexturePrior | None = None
    in_uk: bool = True
    compost: bool = False  # a bed filled with bought compost: not the soil the maps describe

    @property
    def in_pot(self) -> bool:
        return self.setting in ("pot", "trough")

    @property
    def on_compost(self) -> bool:
        return self.in_pot or (self.in_ground and self.compost)

    @property
    def in_ground(self) -> bool:
        return self.setting in ("raised_bed", "open_ground")


@dataclass
class _Verdict:
    tier: str
    action: PickAction
    reasons: list[str]
    chips: dict[str, PickChip]

    def out(self, reason: str) -> None:
        self.tier = "out"
        self.reasons.insert(0, reason)

    def demote(self, reason: str) -> None:
        if self.tier == "good":
            self.tier = "try"
        self.reasons.append(reason)


def month_name(m: int) -> str:
    return cal.month_name[m]


def month_span(months: frozenset[int] | set[int]) -> str:
    """Months as runs, wrapping past December: {11, 12, 1, 2, 3} -> "November to March"."""
    ms = sorted(months)
    if not ms:
        return "none"
    if len(ms) == 12:
        return "all year"
    starts = [m for m in ms if (m - 2) % 12 + 1 not in months]
    runs = []
    for start in starts:
        end = start
        while end % 12 + 1 in months:
            end = end % 12 + 1
        runs.append(
            month_name(start) if start == end else f"{month_name(start)} to {month_name(end)}"
        )
    return ", ".join(runs)


def winter_dark_note(sun: SunHours, month: int) -> str | None:
    """The months with no direct sun, as the table shows them, when one of them is this
    month or the next two: "No direct sun from November to January here: ..."."""
    dark = {m for m in range(1, 13) if sun.months[m - 1][1] <= DARK_H}
    ahead = {(month - 1 + k) % 12 + 1 for k in range(DARK_AHEAD)}
    if not dark & ahead:
        return None
    if len(dark) == 12:
        return "No direct sun at any time of year here: pick crops for shade."
    span = month_span(dark)
    when = f"from {span}" if " to " in span and "," not in span else f"in {span}"
    return f"No direct sun {when} here: growth stops, so pick for a spring harvest."


def _differ(crop: Crop, action: PickAction, m: int) -> str | None:
    """Both windows named when this month is inside RHS's window and not Garden
    Organic's, or the other way round (the logged disagreements, ref section 6). The
    source whose window holds this month comes first: the closed "±" shows only it."""
    window = WINDOW_OF.get(action)
    if window is None:
        return None
    have = {
        n: crop.windows_by_source[n][window]
        for n in DISAGREE_SOURCES
        if window in crop.windows_by_source.get(n, {})
    }
    if len(have) < 2 or len({m in w for w in have.values()}) == 1:
        return None
    ordered = sorted(have.items(), key=lambda nw: m not in nw[1])
    return " ".join(f"{SOURCE_NAMES[n]}: {month_span(w)}." for n, w in ordered)


def _actions(crop: Crop, m: int) -> list[PickAction]:
    """What the calendar says to do this month; a month only one of RHS and Garden
    Organic lists (the rhubarb case) still counts, as a disagreement."""
    out: list[PickAction] = []
    if m in crop.sow_outdoors:
        out.append("sow_outdoors")
    if m in crop.plant_out:
        out.append("plant_out")
    if m in crop.sow_indoors:
        out.append("sow_indoors")
    if not out:
        out = [a for a in ("plant_out", "sow_outdoors") if _differ(crop, a, m)]
    return out


def _judge(crop: Crop, action: PickAction, spot: GrowSpot) -> _Verdict:
    m = spot.month
    v = _Verdict("good", action, [], {})
    outdoor = action in ("sow_outdoors", "plant_out")
    # container
    if spot.in_pot:
        if crop.ground_only:
            v.out("grows in the ground only")
        elif spot.pot_size == "unknown":
            need = [
                f"{crop.min_litres:g} L" if crop.min_litres else "",
                f"{crop.min_depth_cm:g} cm deep" if crop.min_depth_cm else "",
            ]
            text = "needs a pot of at least " + " and ".join(x for x in need if x)
            big = (crop.min_litres or 0) > POT_LITRES["medium"] or (
                crop.min_depth_cm or 0
            ) > POT_DEPTH_CM["medium"]
            if big:  # a tree or big crop: not "good now" in a pot of unknown size
                v.demote(text)
            elif any(need):  # flagged, not demoted: most pots people ask about fit these
                v.reasons.append(text)
        else:
            litres, depth = POT_LITRES[spot.pot_size], POT_DEPTH_CM[spot.pot_size]
            if crop.min_litres and litres is not None and litres < crop.min_litres:
                v.out(f"needs at least {crop.min_litres:g} L; this pot holds under {litres:g} L")
            elif crop.min_depth_cm and depth is not None and depth < crop.min_depth_cm:
                v.out(f"needs a pot at least {crop.min_depth_cm:g} cm deep")
    # sun (RHS classes on June hours)
    need = NEED[crop.sun]
    if spot.sun is None:
        v.chips["Sun"] = PickChip(name="Sun", value="unknown", source="no sun estimate")
        if crop.sun != "part_or_shade":
            v.demote("sun here is not known")
    else:
        low, mid, _ = spot.sun.months[5]
        src = spot.sun.method
        if RANK[class_of(mid)] < RANK[need]:
            v.out(f"needs {NEED_TEXT[crop.sun]}; this spot gets about {mid:.0f} h in June")
            v.chips["Sun"] = PickChip(name="Sun", value="too shady", source=src)
        elif RANK[class_of(low)] < RANK[need]:
            # June's hours against the need, so it reads with the header's "Full sun in
            # summer, give or take" rather than against it (18 Oct judge run)
            # whole hours unless they round to one number ("6 to 6 h" read as enough)
            fmt = ".1f" if f"{low:.0f}" == f"{mid:.0f}" else ".0f"
            v.demote(
                f"sun is borderline for it: about {low:{fmt}} to {mid:{fmt}} h on a clear "
                f"June day, and it wants {NEED_TEXT[crop.sun]}"
            )
            v.chips["Sun"] = PickChip(name="Sun", value="borderline", source=src)
        elif spot.sun.cross_check == "disagrees" and spot.sun.borderline:
            v.demote("sun is borderline for it: the two sun estimates for this spot disagree")
            v.chips["Sun"] = PickChip(name="Sun", value="borderline", source=src)
        else:
            v.chips["Sun"] = PickChip(name="Sun", value="fits", source=src)
    # a spreader in a bed takes it over (18 Oct judge run: a fresh raised bed's Good now
    # led with mint and horseradish); in a pot it is contained
    if crop.spreads and spot.in_ground:
        v.demote("spreads: grow it in a pot sunk into the bed")
    # frost when sowing or planting out: the calendar's windows are timed for mid-England
    # frosts (last air-frost month April), so a tender crop is held back only by the
    # months this spot's frosts run later in spring (or earlier in autumn) than that.
    nights = None
    if spot.frost and spot.frost.air_frost_by_month:
        nights = spot.frost.air_frost_by_month[m - 1]
    if outdoor and crop.frost_tender:
        window = crop.sow_outdoors if action == "sow_outdoors" else crop.plant_out
        if nights is None:
            if m in window and (m - 2) % 12 + 1 not in window:
                v.demote("frost-tender, and frost here is not known: wait a few weeks")
            v.chips["Frost"] = PickChip(name="Frost", value="not known", source="no frost data")
        elif _frost_late(spot.frost.air_frost_by_month, window, m):
            v.out(f"frost-tender: about {nights:g} air frosts in {month_name(m)} here")
        else:
            v.chips["Frost"] = PickChip(name="Frost", value="fine", source="HadUK-Grid")
    # mild areas only
    if outdoor and m in crop.mild_months.get(action, frozenset()):
        year = spot.frost.air_frost_year if spot.frost else None
        if year is None:
            v.demote(
                f"{DO[action].lower()} in {month_name(m)} suits mild areas; frost here is not known"
            )
        elif year > MILD_AIR_FROST:
            v.out(
                f"{DO[action].lower()} in {month_name(m)} is for mild areas; here has about {year:.0f} air frosts a year"
            )
        else:
            v.demote(f"a mild-area window: fine here ({year:.0f} air frosts a year)")
    # hardiness over winter
    if outdoor and m in OVER_WINTER and crop.overwinters in ("y", "with_protection"):
        rating = crop.rating_in_pot() if spot.in_pot else crop.rating
        coldest = spot.frost.typical_coldest_night_c if spot.frost else None
        if rating in RATING_MIN_C and coldest is not None and RATING_MIN_C[rating] > coldest:
            pot = " (one rating less in a pot)" if spot.in_pot else ""
            v.out(
                f"rated {rating}{pot}, hardy to about {RATING_MIN_C[rating]:g} °C; a typical winter here reaches {coldest:g} °C"
            )
        elif crop.overwinters == "with_protection":
            v.chips["Frost"] = PickChip(name="Frost", value="fleece", source="calendar")
            v.reasons.append("fleece it in cold spells")
        elif "Frost" not in v.chips:
            known = rating in RATING_MIN_C and coldest is not None
            v.chips["Frost"] = PickChip(
                name="Frost", value="fine" if known else "not known", source="ERA5-Land"
            )
    v.chips.setdefault("Frost", PickChip(name="Frost", value="not needed", source="calendar"))
    # pH, for acid-lovers
    if crop.ph == "acid_required":
        if spot.on_compost:
            v.reasons.append("use ericaceous compost")
        elif spot.in_ground:
            ph = spot.ph
            if ph and (ph.lime or (ph.low is not None and ph.low > ACID_LINE)):
                v.out("needs acid soil; the maps show lime or a pH above 6")
            elif ph is None or ph.low is None:
                v.demote("needs acid soil: a £5 pH kit settles it")
        else:  # setting not known: never list an acid-lover as good
            v.demote("needs acid soil, or ericaceous compost in a pot")
    # soil fit in the ground: demotes, never excludes (soil can be fixed)
    if spot.in_ground and not spot.compost:
        tex = spot.texture
        if tex is None or tex.source == "none":
            v.chips["Soil"] = PickChip(name="Soil", value="not known", source="no soil data")
        elif tex.p_clayey >= CLAY_LINE and (crop.clay_ok is False or crop.needs_drainage):
            v.demote("on clay: a raised bed, modules or grit")
            v.chips["Soil"] = PickChip(name="Soil", value="fix needed", source=tex.source)
        else:
            v.chips["Soil"] = PickChip(name="Soil", value="fits", source=tex.source)
            if crop.clay_ok and tex.p_clayey >= CLAY_LINE:
                v.reasons.append("suits clay")
    else:
        v.chips["Soil"] = PickChip(name="Soil", value="fits", source="bought compost")
    # timing
    differ = _differ(crop, action, m)
    if differ:
        v.demote(f"sources differ on timing. {differ}")
        v.chips["Timing"] = PickChip(name="Timing", value="sources differ", source="calendar")
    else:
        v.chips["Timing"] = PickChip(name="Timing", value="now", source="calendar")
    return v


def _pick(crop: Crop, v: _Verdict, do: str | None = None) -> GrowPick:
    return GrowPick(
        crop_id=crop.id,
        name=crop.name,
        action=v.action,
        do=do or DO[v.action],
        chips=[v.chips[n] for n in ("Sun", "Soil", "Frost", "Timing") if n in v.chips],
        reasons=v.reasons,
        sources=list(crop.sources),
    )


def _best(crop: Crop, spot: GrowSpot) -> _Verdict | None:
    verdicts = [_judge(crop, a, spot) for a in _actions(crop, spot.month)]
    if not verdicts:
        return None
    return min(verdicts, key=lambda v: (TIER_RANK[v.tier], v.action == "sow_indoors"))


def _order(crop: Crop, spot: GrowSpot, action: PickAction) -> tuple:
    """Sun margin first, as a step (a comfortable hour or more, or not); then outdoor jobs
    before windowsill starts; then evidence (C before D); then annual crops before perennials (a first harvest this year); then
    common crops first (how many independent calendars cover it); then a window that
    opens this month before one already running; then months to the first harvest."""
    margin = spot.sun.months[5][1] - NEED_HOURS[crop.sun] if spot.sun else 0.0
    if crop.days_to_harvest and not crop.perennial:
        to_harvest = crop.days_to_harvest / 30.4
    elif crop.harvest:
        to_harvest = min((h - spot.month) % 12 for h in crop.harvest) + (
            12 if crop.perennial else 0
        )
    else:
        to_harvest = 24
    window = {"sow_outdoors": crop.sow_outdoors, "plant_out": crop.plant_out}.get(
        action, crop.sow_indoors
    )
    opens = spot.month in window and (spot.month - 2) % 12 + 1 not in window
    return (
        margin < SUN_MARGIN_H,
        action == "sow_indoors",
        crop.evidence_tier != "C",
        crop.perennial,
        -min(crop.cross_checks, 3),
        not opens,
        to_harvest,
        crop.name,
    )


def _windowsill(crops: tuple[Crop, ...]) -> list[GrowPick]:
    return [
        GrowPick(
            crop_id=c.id,
            name=c.name,
            action="windowsill",
            do="Sow on the windowsill, any time",
            chips=[PickChip(name="Timing", value="now", source="calendar")],
            reasons=[],
            sources=list(c.sources),
        )
        for c in crops
        if len(c.sow_indoors) == 12
    ]


def rank(crops: tuple[Crop, ...], spot: GrowSpot) -> dict[str, list[GrowPick]]:
    """Every candidate, ordered within its tier: good_now, worth_a_try, coming_up (next
    month's starts not already listed) and not_here (failed a hard filter, by name)."""
    rows: dict[str, list[tuple[tuple, GrowPick]]] = {"good": [], "try": [], "out": []}
    for crop in crops:
        v = _best(crop, spot)
        if v is not None:
            rows[v.tier].append((_order(crop, spot, v.action), _pick(crop, v)))
    listed = {p.crop_id for t in ("good", "try") for _, p in rows[t]}
    nxt = spot.month % 12 + 1
    later = replace(spot, month=nxt)
    coming = []
    for crop in crops:
        v = None if crop.id in listed else _best(crop, later)
        if v is not None and v.tier != "out":
            v.chips["Timing"] = PickChip(name="Timing", value="from next month", source="calendar")
            do = f"From {month_name(nxt)}: {DO[v.action].lower()}"
            coming.append((_order(crop, later, v.action), _pick(crop, v, do)))

    def ordered(r: list[tuple[tuple, GrowPick]]) -> list[GrowPick]:
        return [p for _, p in sorted(r, key=lambda x: x[0])]

    return {
        "good_now": ordered(rows["good"]),
        "worth_a_try": ordered(rows["try"]),
        "coming_up": ordered(coming),
        "not_here": sorted((p for _, p in rows["out"]), key=lambda p: p.name),
    }


def grow_list(crops: tuple[Crop, ...], spot: GrowSpot) -> GrowList:
    """The list the page shows: at most 8 per tier, with the season's notes."""
    notes = [WARM_NOTE] if spot.year in WARM_SEASONS else []
    if not spot.in_uk:
        return GrowList(month=spot.month, notes=[OUTSIDE_UK])
    if not crops:
        return GrowList(month=spot.month, notes=[NO_CALENDAR])
    if spot.setting == "windowsill":  # indoors: no outdoor windows, so no warm-season note
        return GrowList(month=spot.month, good_now=_windowsill(crops), notes=[WINDOWSILL_NOTE])
    if spot.sun is not None and (dark := winter_dark_note(spot.sun, spot.month)):
        notes.append(dark)
    r = rank(crops, spot)
    return GrowList(
        month=spot.month,
        good_now=r["good_now"][:PER_TIER],
        worth_a_try=r["worth_a_try"][:PER_TIER],
        coming_up=r["coming_up"][:PER_TIER],
        not_here=r["not_here"],
        notes=notes,
    )
