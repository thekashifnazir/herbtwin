"""The spot answer (spot spec sections 3 to 7, D67 to D72): "What can I grow here?".

read_spot_photo does everything that costs a call or a fetch, once: the spot read (one
vision call), the 1 km location priors, the typical coldest night and the light at the
photo's moment. decide_spot is code only and runs again whenever the person answers a
question or corrects a chip, so a later compass tap or squeeze needs no new call.
Raw GPS never leaves where.py: everything here uses the rounded Location.
"""

from __future__ import annotations

import calendar
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from herbtwin.crops import Crop, load_calendar
from herbtwin.grow import PER_TIER, GrowSpot, grow_list, rank
from herbtwin.light import read_light
from herbtwin.schemas import (
    AnalysisRecord,
    Aspect,
    FrostNormals,
    GrowList,
    GrowPick,
    LightReading,
    Location,
    PhRange,
    PotSize,
    Spot,
    SpotRead,
    SpotSetting,
    StageFailure,
    Told,
)
from herbtwin.spot_priors import GridCell, lookup
from herbtwin.spot_questions import (
    COMPASS_FIRST,
    compass_offered,
    squeeze_asked,
    squeeze_note,
    texture_prior,
)
from herbtwin.stages.climate import ClimateError, typical_coldest_night
from herbtwin.stages.environment import EnvironmentError_, fetch_environment
from herbtwin.stages.spot import SpotReadError, read_spot
from herbtwin.sun import cross_check, direction_matters, sun_hours
from herbtwin.tracing import StageTracer, bind
from herbtwin.where import exif_exposure, in_uk, photo_date, resolve_location, strip_metadata

log = logging.getLogger(__name__)

GROUND = ("raised_bed", "open_ground")
CONTAINERS = ("pot", "trough")
SHOWN_TIERS = ("good_now", "worth_a_try")  # the tiers whose rest the page folds away
WEATHER_DAYS_BACK = 13
NO_MAPS = "Soil and frost maps are not available here (they cover Great Britain)."
NO_PLACE = (
    "We couldn't tell where this is, so there's no list yet. Add a town or postcode, or use "
    "your location, and try again."
)
LEAD_NOTE = (
    "Old town gardens can hold lead from past paint, fuel and coal ash. For food grown in "
    "the ground, a soil test settles it (the UK allotment screening level is 80 mg/kg); "
    "raised beds filled with bought soil avoid it."
)
BGS = (
    "Soil texture and lime: contains British Geological Survey materials © UKRI (Soil Parent "
    "Material Model 1 km, OGL)."
)
UKCEH = "Topsoil pH: UKCEH Countryside Survey (Henrys et al. 2012, NERC EIDC, OGL)."
HADUK = "Frost and sunshine normals 1991-2020: Met Office HadUK-Grid, via CEDA (OGL)."
ERA5 = "Coldest nights: Open-Meteo.com, ERA5-Land (CC BY 4.0)."
CALENDAR = "Sow and plant months: our UK crop calendar, with each crop's sources linked."
ATTRIBUTIONS = (BGS, UKCEH, HADUK, ERA5, CALENDAR)


@dataclass
class SpotRun:
    """Everything read once for a spot. decide_spot never changes it."""

    record_id: str
    taken_at: datetime
    taken_at_source: str
    location: Location | None
    read: SpotRead
    cell: GridCell | None
    coldest_c: float | None
    light: LightReading | None
    notes: list[str] = field(default_factory=list)
    failures: list[StageFailure] = field(default_factory=list)
    history_aspect: Aspect | None = None  # a signed-in person's earlier tap at this place
    read_by_backup: bool = False  # the backup photo model read it: the page asks the setting


@dataclass(frozen=True)
class SpotTold:
    """The person's answers under a spot answer: the two questions (in Told, validated
    there) and corrections to the setting and pot-size chips."""

    told: Told = field(default_factory=Told)
    setting: SpotSetting | None = None
    pot_size: PotSize | None = None


def _say(progress, line: str) -> None:
    if progress is not None:
        try:
            progress(line)
        except Exception:  # noqa: BLE001 - progress is a courtesy; the answer matters more
            log.exception("progress hook failed")


def read_spot_photo(
    deps,
    image: bytes,
    mime: str,
    *,
    received: datetime,
    device: tuple[float, float] | None = None,
    place: str | None = None,
    record_id: str | None = None,
    progress=None,
) -> SpotRun:
    """The reading half. Never stops early: a photo that cannot be read, or a spot read
    with no usable reply (sunny photos can reason past max_tokens), leaves the setting
    unknown and the answer comes from the location."""
    record_id = record_id or uuid.uuid4().hex
    tracer = StageTracer(deps.trace_store, record_id)
    taken_at, taken_src = photo_date(image, received)
    location, notes = resolve_location(
        image, device=device, place=place, home=deps.settings.home, client=deps.http
    )
    failures: list[StageFailure] = []
    read = SpotRead()
    reader = bind(deps.observe_adapter, "spot", tracer)
    _say(progress, "Reading the spot")
    try:
        clean = strip_metadata(image, mime)  # no EXIF (GPS, date) reaches a model provider
        uk = location is not None and in_uk(location.lat, location.lon)
        context = f"{'UK, ' if uk else ''}{calendar.month_name[taken_at.month]}"
        read = read_spot(reader, clean, mime, context=context)
    except (ValueError, SpotReadError) as e:
        log.exception("spot read failed run=%s", record_id)
        failures.append(StageFailure(stage="spot", message=str(e), raw=getattr(e, "raw", None)))
    indoors = read.setting == "windowsill"
    cell, coldest = _lookups(deps, location, notes, failures, record_id, progress, not indoors)
    light = None
    if location is not None:
        light = _light(deps, image, location, taken_at, taken_src, received, read, failures)
    return SpotRun(
        record_id=record_id,
        taken_at=taken_at,
        taken_at_source=taken_src,
        location=location,
        read=read,
        cell=cell,
        coldest_c=coldest,
        light=light,
        notes=notes,
        failures=failures,
        read_by_backup=getattr(reader, "used_backup", False),
    )


def _lookups(deps, location, notes, failures, record_id, progress=None, climate=True):
    """The 1 km priors and the typical coldest night (skipped indoors: `climate` False); a
    failure is a note, never a stop."""
    if location is None:
        return None, None
    _say(progress, "Looking up the soil and frost maps")
    cell = lookup(location.lat, location.lon)
    if cell is None:
        notes.append(NO_MAPS)
        return None, None
    if not climate:
        return cell, None
    try:
        return cell, typical_coldest_night(location.lat, location.lon, client=deps.http)
    except ClimateError as e:
        log.exception("coldest night failed run=%s", record_id)
        failures.append(StageFailure(stage="climate", message=str(e)))
        return cell, None


def spot_from_reading(deps, reading, record_id: str | None = None) -> SpotRun:
    """ "About this spot" from a plant answer: its location, date and light, and the
    setting its photo read already gave (pot or ground); no new vision call. The web
    layer passes an id derived from the answer, so a repeat click reuses its spot."""
    return spot_from_record(deps, reading.rec, record_id)


def spot_from_record(deps, rec: AnalysisRecord, record_id: str | None = None) -> SpotRun:
    """The same from the record alone: a bed photo stops after the read, so it has a
    record but no Reading."""
    obs = rec.observation
    setting: SpotSetting = "unknown"
    if obs is not None:
        setting = (
            "windowsill"
            if obs.setting == "indoor"
            else {"pot": "pot", "ground": "open_ground"}.get(obs.container, "unknown")
        )  # type: ignore[assignment]
    rid = record_id or uuid.uuid4().hex
    notes: list[str] = []
    failures: list[StageFailure] = []
    cell, coldest = _lookups(
        deps, rec.location, notes, failures, rid, climate=setting != "windowsill"
    )
    return SpotRun(
        record_id=rid,
        taken_at=rec.taken_at,
        taken_at_source=rec.taken_at_source,
        location=rec.location,
        read=SpotRead(setting=setting),
        cell=cell,
        coldest_c=coldest,
        light=rec.light,
        notes=notes,
        failures=failures,
    )


def record_of(run: SpotRun, spot: Spot, grow: GrowList, told: Told | None) -> AnalysisRecord:
    """The JSON API's record: the spot answer on the usual AnalysisRecord (D70)."""
    return AnalysisRecord(
        record_id=run.record_id,
        taken_at=run.taken_at,
        taken_at_source=run.taken_at_source,
        location=run.location,
        observation=None,
        environment=None,
        pack=None,
        state=None,
        light=run.light,
        told=told,
        spot=spot,
        grow=grow,
        notes=list(spot.notes),
        failures=list(run.failures),
    )


def _light(deps, image, location, taken_at, taken_src, received, read, failures):
    """C1's light at the photo's moment, for the sun cross-check only."""
    age = (received.date() - taken_at.date()).days
    if taken_src != "exif" or read.setting == "windowsill" or not -1 <= age <= WEATHER_DAYS_BACK:
        return None
    try:
        env = fetch_environment(location.lat, location.lon, on=taken_at.date(), client=deps.http)
    except EnvironmentError_ as e:
        failures.append(StageFailure(stage="environment", message=str(e)))
        return None
    reading, _ = read_light(
        exif_exposure(image),
        taken_at,
        env.sky_hours,
        indoor=False,
        sky_offset_s=env.sky_utc_offset_s,
    )
    return reading


@dataclass(frozen=True)
class SpotView:
    """What the spot page shows: the card, the list (8 a tier) and the rest of good now
    and worth a try, folded away under each tier."""

    spot: Spot
    grow: GrowList
    more: dict[str, list[GrowPick]]


MUNSELL = re.compile(r"(\d+(?:\.\d+)?)?\s*(YR|GY|Y|R|G|N)\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)?")


COLOUR_WORDS = frozenset(
    {
        "brown",
        "grey",
        "gray",
        "black",
        "red",
        "reddish",
        "yellow",
        "yellowish",
        "orange",
        "dark",
        "pale",
    }
)


def soil_colour_words(said: str) -> str:
    """The photo read's soil colour in words: the read may give a Munsell code ("10YR 4/3"),
    which read as jargon on the spot page (18 Oct judge run). Words it gave are kept."""
    said = said.strip()
    for part in said.split(","):  # "dark greyish brown, about 10YR 4/2, damp"
        words = part.strip()
        if not any(ch.isdigit() for ch in words) and COLOUR_WORDS.intersection(
            words.lower().replace("-", " ").split()
        ):
            return words
    m = MUNSELL.search(said)
    if m is None:
        return ""
    step, hue, value, chroma = m.groups()
    v, c = float(value), float(chroma) if chroma else 0.0
    shade = "very dark" if v <= 2 else "dark" if v <= 3 else "pale" if v >= 6 else ""
    if hue == "N" or c == 0:
        tint = "grey"
    elif c <= 1:
        tint = "grey-brown"
    elif hue in ("GY", "G"):
        tint = "greenish grey"
    elif hue == "R" or (hue == "YR" and float(step or 10) <= 5):
        tint = "reddish brown"
    elif hue == "Y":
        tint = "yellowish brown"
    else:
        tint = "brown"
    return f"{shade} {tint}".strip()


def medium_text(spot: Spot) -> str | None:
    """The soil card's first line. Bought compost may be stated; garden soil is stated only
    when the squeeze agrees (the S2 safeguard: one trough close-up was read as soil)."""
    r = spot.read
    if r.setting in (*CONTAINERS, "windowsill"):
        if r.medium == "compost":
            return "Bought compost."
        return "In a container: the soil maps don't apply."
    if r.medium == "compost":
        return "Bought compost."
    if r.medium == "soil":
        squeezed = spot.texture is not None and spot.texture.source == "squeeze"
        return "Garden soil." if squeezed else "Looks like garden soil."
    return None


def credits(spot: Spot, grow: GrowList) -> list[str]:
    """Credit only the sources whose numbers the page shows (none of the maps abroad)."""
    out = []
    if (spot.texture and spot.texture.source in ("map", "map+photo")) or (
        spot.ph and spot.ph.lime is not None
    ):
        out.append(BGS)
    if spot.ph and spot.ph.low is not None:
        out.append(UKCEH)
    f = spot.frost
    if f and (f.air_frost_by_month or f.sunshine_year_h):
        out.append(HADUK)
    if f and f.typical_coldest_night_c is not None:
        out.append(ERA5)
    if grow.good_now or grow.worth_a_try or grow.coming_up or grow.not_here:
        out.append(CALENDAR)
    return out


def decide_spot(
    run: SpotRun, answers: SpotTold | None = None, crops: tuple[Crop, ...] | None = None
) -> tuple[Spot, GrowList]:
    """The spot card and the grow list from one reading and the person's answers. Code
    only: no model call, no fetch."""
    crops = load_calendar() if crops is None else crops
    spot, where = _decide(run, answers or SpotTold(), crops)
    return spot, _listed(run, crops, where)


def _listed(run: SpotRun, crops: tuple[Crop, ...], where: GrowSpot) -> GrowList:
    grow = grow_list(crops, where)
    if run.location is None:  # the true reason, not "this place is outside the UK"
        grow = grow.model_copy(update={"notes": [NO_PLACE]})
    return grow


def view_spot(
    run: SpotRun, answers: SpotTold | None = None, crops: tuple[Crop, ...] | None = None
) -> SpotView:
    """decide_spot plus the rest of each shown tier past the 8 on the list (recall of the
    fitting RHS picks is 0.33 within the 16 shown, 0.90 within the full tiers)."""
    crops = load_calendar() if crops is None else crops
    spot, where = _decide(run, answers or SpotTold(), crops)
    grow = _listed(run, crops, where)
    ranked = where.in_uk and bool(crops) and where.setting != "windowsill"
    r = rank(crops, where) if ranked else {}
    return SpotView(spot, grow, {t: r.get(t, [])[PER_TIER:] for t in SHOWN_TIERS})


def _decide(run: SpotRun, answers: SpotTold, crops: tuple[Crop, ...]) -> tuple[Spot, GrowSpot]:
    fixes: dict[str, str] = {
        k: v for k, v in (("setting", answers.setting), ("pot_size", answers.pot_size)) if v
    }
    if answers.setting in CONTAINERS:
        fixes["medium"] = "compost"  # a pot or trough the photo misread holds bought compost
    read = run.read.model_copy(update=fixes)
    told, loc, cell = answers.told, run.location, run.cell
    notes = list(run.notes)
    indoors = read.setting == "windowsill"
    listed = loc is not None and in_uk(loc.lat, loc.lon)  # no list, no questions
    # the mapped ground: in the ground and not bought compost (a bed filled with compost is
    # not the soil the maps describe)
    mapped = read.setting in GROUND and read.medium != "compost"
    texture = texture_prior(cell, read, told.squeeze) if mapped else None
    if mapped and (note := squeeze_note(texture_prior(cell, read, None), told.squeeze)):
        notes.append(note)
    if mapped and cell is not None and cell.urban:
        notes.append(LEAD_NOTE)
    ph = None
    if mapped and cell is not None:
        lo, hi = cell.ph if cell.ph else (None, None)
        ph = PhRange(low=lo, high=hi, lime=cell.lime, source="ukceh_cs" if cell.ph else "none")
    frost = None
    if not indoors and (cell is not None or run.coldest_c is not None):
        frost = FrostNormals(
            air_frost_by_month=list(cell.air_frost_by_month)
            if cell and cell.air_frost_by_month
            else None,
            ground_frost_year=cell.ground_frost_year if cell else None,
            coldest_month_min_c=cell.coldest_month_min_c if cell else None,
            typical_coldest_night_c=run.coldest_c,
            sunshine_year_h=cell.sunshine_year_h if cell else None,
            sources=["Met Office HadUK-Grid 1991-2020"]
            + (["ERA5-Land"] if run.coldest_c is not None else []),
        )
    aspect = None if indoors else (told.heading.aspect() if told.heading else run.history_aspect)
    matters = (
        loc is not None
        and not indoors
        and direction_matters(loc.lat, loc.lon, read.backed_by_wall, run.taken_at.year)
    )
    # an 8-way pick with the same horizon all round changes nothing: the hours stay the
    # defaults' and the page says why; a compass tap carries a pitch, so it always counts
    used = aspect if aspect is not None and (matters or aspect.pitch_deg is not None) else None
    sun = None
    if loc is not None and not indoors:
        sun = sun_hours(loc.lat, loc.lon, used, read.backed_by_wall, run.taken_at.year)
        sun = cross_check(sun, run.light, loc.lat, loc.lon, used, read.backed_by_wall)
    grow_spot = GrowSpot(
        month=run.taken_at.month,
        year=run.taken_at.year,
        setting=read.setting,
        pot_size=read.pot_size,
        sun=sun,
        frost=frost,
        ph=ph,
        texture=texture,
        in_uk=listed,
        compost=read.setting in GROUND and read.medium == "compost",
    )
    asked = "no"
    if listed and texture is not None and told.squeeze is None:
        asked = squeeze_asked(read, texture, grow_spot, crops)
    spot = Spot(
        read=read,
        texture=texture,
        ph=ph,
        aspect=aspect,
        sun=sun,
        frost=frost,
        squeeze=asked,
        compass=listed and compass_offered(read, aspect, matters or COMPASS_FIRST),
        direction_matters=matters,
        notes=notes,
    )
    return spot, grow_spot
