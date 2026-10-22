"""Typed boundaries between stages. Everything here is JSON round-trippable."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from herbtwin.seasonal import SeasonalNorm
from herbtwin.stages.trusted_check import Form

Action = Literal[
    "water_now", "water_lightly", "move_to_shade", "move_to_sun", "bring_indoors", "do_nothing"
]
ACTIONS: tuple[Action, ...] = (
    "water_now",
    "water_lightly",
    "move_to_shade",
    "move_to_sun",
    "bring_indoors",
    "do_nothing",
)


# The nine classes expert answers were labelled in (plan 2b, D16). Frozen: evaluation,
# action extraction and the confidence fit score in these, so results stay comparable.
CoarseAction = Literal[
    "water",
    "dont_water",
    "move_light",
    "shelter",
    "treat_or_remove",
    "prune",
    "leave_normal",
    "ask_first",
    "other",
]
COARSE_ACTIONS: tuple[CoarseAction, ...] = CoarseAction.__args__  # type: ignore[attr-defined]
COARSE_ACTION_DEFINITIONS: dict[str, str] = {
    "water": "water the plant now or more often",
    "dont_water": "water less, stop watering, let it dry out, or improve drainage",
    "move_light": "move it to more or less light or sun",
    "shelter": "protect from cold, frost, wind, rain or heat; bring indoors",
    "treat_or_remove": "treat a pest or disease, spray, remove affected parts or the plant",
    "prune": "cut back, deadhead, pinch out or harvest",
    "leave_normal": "nothing is wrong or it is normal for the plant or season; leave it",
    "ask_first": "needs more information, a closer look, or a lab test before acting",
    "other": "any other action (feed, repot, change soil, buy a new plant, ...)",
}

# What an answer tells the person to do (phase B, D43): the nine above plus eight finer
# actions that phase A folded into "other" or "ask_first". Wider than Action (the twin's
# six simulated actions).
CareAction = Literal[
    "water",
    "dont_water",
    "move_light",
    "shelter",
    "treat_or_remove",
    "prune",
    "leave_normal",
    "ask_first",
    "feed",
    "repot",
    "change_soil",
    "check_pests",
    "isolate",
    "mulch",
    "humidity",
    "rotate",
    "other",
]
CARE_ACTIONS: tuple[CareAction, ...] = CareAction.__args__  # type: ignore[attr-defined]
CARE_ACTION_DEFINITIONS: dict[str, str] = {
    **{k: v for k, v in COARSE_ACTION_DEFINITIONS.items() if k != "other"},
    "feed": "give it fertiliser or plant food",
    "repot": "move it to a bigger pot or pot it on",
    "change_soil": "replace or refresh the compost or soil, or top-dress it",
    "check_pests": "look under the leaves and along the stems for pests before acting",
    "isolate": "keep it away from other plants so a pest or disease does not spread",
    "mulch": "spread mulch over the soil to keep in moisture or protect the roots",
    "humidity": "raise the humidity around it (indoors): group plants, a tray of wet pebbles",
    "rotate": "turn the pot regularly so it grows evenly toward the light",
    "other": "any other action not listed (buy a new plant, ...)",
}
COARSE_ACTION: dict[str, CoarseAction] = {
    **{a: a for a in COARSE_ACTIONS},
    "check_pests": "ask_first",
    "isolate": "treat_or_remove",
    "feed": "other",
    "repot": "other",
    "change_soil": "other",
    "mulch": "other",
    "humidity": "other",
    "rotate": "other",
}


def coarse(action: str) -> CoarseAction:
    """The phase A class an action is scored as (D43). KeyError for an unknown action."""
    return COARSE_ACTION[action]


LeafColour = Literal["green", "some_yellow", "mostly_yellow", "not_visible"]
LEAF_COLOURS: tuple[LeafColour, ...] = ("green", "some_yellow", "mostly_yellow", "not_visible")


Setting = Literal["indoor", "outdoor", "unknown"]
Container = Literal["pot", "ground", "unknown"]
PhotoQuality = Literal["good", "poor"]
Scene = Literal["one_plant", "bed_or_border", "no_plant"]
# has the plant outgrown its pot (21 Oct, a gardener's question): too_small feeds repot advice
PotFit = Literal["roomy", "snug", "too_small", "unknown"]


class SpeciesCandidate(BaseModel):
    name: str
    common_name: str
    confidence: float = Field(ge=0, le=1)


class Observation(BaseModel):
    species: list[SpeciesCandidate]
    is_plant: bool
    water_stress: int = Field(ge=0, le=3)  # posture only: drooping leaves or stems
    # dead, dried or brown tissue; defaults keep recordings made before plan 2 parseable
    decline: int = Field(0, ge=0, le=3)
    leaf_colour: LeafColour = "not_visible"
    heat_light_stress: int = Field(ge=0, le=3)
    fine_leave_it: bool
    symptoms: list[str]
    leaf_cues: list[str]
    soil_surface: Literal["dry", "moist", "wet", "not_visible"]
    notes: str = ""
    # phase A; defaults keep recordings made before them parseable
    setting: Setting = "unknown"
    container: Container = "unknown"
    photo_quality: PhotoQuality = "good"
    quality_note: str = ""  # why the photo is poor: blurred, dark, plant small, several plants
    # what the photo is of (16 Oct): a bed gets the spot answer offered; a bed with no plant
    # named (bare ground) gets only that, since there is no plant to advise on
    scene: Scene = "one_plant"
    pot_fit: PotFit = "unknown"

    @property
    def bare_bed(self) -> bool:
        return self.scene == "bed_or_border" and not self.species

    @property
    def in_bed(self) -> bool:
        """Growing in a bed or border. The scene says different kinds share the frame, which
        pots of different herbs on a patio do too (Kash's live test, 21 Oct): a pot the read
        saw is a pot, so the bed wording and the bed offer need a container other than pot."""
        return self.scene == "bed_or_border" and self.container != "pot"


def _trusted(url: str) -> bool:
    # here, not at the top: search imports advice_context, which imports this module
    from herbtwin.search import TRUSTED, is_trusted

    return is_trusted(url, TRUSTED)


class WebHow(BaseModel):
    """How to deal with a problem our outcome rows don't cover, as one sentence quoted from a
    trusted gardening page a web search found (stages/web_how.py). Never a model's words:
    shown in quotation marks with its site, and never sent to the advisor."""

    quote: str = Field(max_length=300)
    url: str  # https, on a trusted site
    found_with: str  # the search provider that found the page: "tavily", "exa", "tinyfish"

    @field_validator("url")
    @classmethod
    def _trusted_page(cls, v: str) -> str:
        """Checked again on every read, a stored answer's included: it becomes a link."""
        if not _trusted(v):
            raise ValueError("not an https page on a trusted site")
        return v


class PageSentence(BaseModel):
    """One sentence of a trusted page, as written, and Stage 1's reading of it
    (stages/trusted_extract.py); form None: no reading, so it never backs anything."""

    text: str = Field(max_length=400)
    form: Form | None = None
    heading: str | None = Field(None, max_length=200)  # the page's heading above it
    # the plant state (trusted_page.gated) Nemotron said it backs, read with our advice
    # (stages/trusted_backs.py); asked only when the code agreed. None: not asked, or no
    backed: str | None = Field(None, max_length=600)


class TrustedCheck(BaseModel):
    """A trusted page's sentences, read into forms while the advisors think
    (stages/trusted_page.py). quote is the page's own sentence that backs this answer's
    action, decided by code (stages/trusted_check.decide) once the answer is known; it is
    never stored, so a refine or a stored answer rebuilt is decided again with no new search
    or model call. Never sent to the advisor."""

    url: str  # https, on a trusted site
    found_with: Literal["tavily"]
    sentences: list[PageSentence] = Field(max_length=12)
    quote: str | None = None
    # the search's other trusted pages about the plant, in its order, for "Read more"
    # (trusted_page.read_more): addresses only, never their words
    pages: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("url")
    @classmethod
    def _trusted_page(cls, v: str) -> str:
        if not _trusted(v):
            raise ValueError("not an https page on a trusted site")
        return v

    @field_validator("pages")
    @classmethod
    def _trusted_pages(cls, v: list[str]) -> list[str]:
        if not all(_trusted(u) for u in v):
            raise ValueError("not an https page on a trusted site")
        return v


def about_problem(url: str, name: str) -> bool:
    """The page's own path names the problem, every word of it ("rosemary beetle" in
    /biodiversity/rosemary-beetle, "powdery mildew" in /disease/powdery-mildews): a page
    about that problem. A grow-your-own page for another plant, or a bare site, is not
    (22 Oct site walk: rosemary beetle's "Signs from" linked the RHS sage page)."""
    path = re.sub(r"[^a-z0-9]+", "-", urlsplit(url).path.lower())
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if w not in {"and", "the", "of"}]
    stems = [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words]
    return bool(stems) and all(w in path for w in stems)


class ProblemSeen(BaseModel):
    """What the second photo check found (stages/problem.py): one of the plant's listed
    problems, described in our curated words. seen is the model's own words: data only,
    shown nowhere but the evidence fold."""

    name: str  # one of outcomes.problems_for(plant)
    looks_like: str  # our signs text from data/outcomes/problem_signs_uk.json
    source: str  # that entry's source url
    seen: str = Field("", max_length=300)
    # True when the read's own guess shares a word with the name ("Looks like"); False when
    # only the kind matches, disease or pest ("Could be")
    sure: bool = True
    how: WebHow | None = None  # when no outcome row covers treating it; absent before 19 Oct

    @property
    def page(self) -> str:
        """The source as a link: only a page about this problem, else "" and no link. Said
        when shown, not stored, so a saved case keeps its source as it was (review)."""
        return self.source if about_problem(self.source, self.name) else ""

    @field_validator("how", mode="wrap")
    @classmethod
    def _no_bad_quote(cls, v: object, handler: ValidatorFunctionWrapHandler) -> WebHow | None:
        """A stored quote whose link fails the check (a site since dropped from the trusted
        list, an edited row) is left out: the answer still loads, with no link."""
        try:
            return handler(v)
        except ValidationError:
            return None


SpotSetting = Literal["pot", "trough", "raised_bed", "open_ground", "windowsill", "unknown"]
SPOT_SETTINGS: tuple[SpotSetting, ...] = SpotSetting.__args__  # type: ignore[attr-defined]
PotSize = Literal["small", "medium", "large", "unknown"]  # under 5 L, 5-20 L, over 20 L
Medium = Literal["compost", "soil", "unknown"]
CompostKind = Literal["peat", "peat_free", "unknown"]
OrganicMatter = Literal["high", "low_medium", "unknown"]
TextureLean = Literal["sandy", "loamy", "clayey", "unknown"]


class SpotRead(BaseModel):
    """The spot read's reply (spot spec section 5, D70): what one photo shows about where
    something grows. Texture is a lean only, never stated (section 2); compost_kind is a
    lean only, never shown."""

    setting: SpotSetting = "unknown"
    pot_size: PotSize = "unknown"
    medium: Medium = "unknown"
    compost_kind: CompostKind = "unknown"
    colour: str = Field("", max_length=40)  # Munsell-style band, e.g. "10YR 4/3"
    organic_matter: OrganicMatter = "unknown"
    texture_lean: TextureLean = "unknown"
    texture_lean_conf: float = Field(0.0, ge=0, le=1)
    backed_by_wall: bool | None = None  # a wall or fence right behind the spot

    @field_validator("colour", mode="before")
    @classmethod
    def _trim_colour(cls, v: object) -> object:
        # A wordy colour must not fail the whole read; keep the first 40 characters.
        return v.strip()[:40] if isinstance(v, str) else v

    @property
    def container(self) -> Container:
        """The plant answer's coarser Container: pot and trough are pots; raised bed and
        open ground are ground."""
        if self.setting in ("pot", "trough"):
            return "pot"
        if self.setting in ("raised_bed", "open_ground"):
            return "ground"
        return "unknown"


class DailyWeather(BaseModel):
    date: date
    t_min: float
    t_max: float
    rain_mm: float = Field(ge=0)
    et0_mm: float = Field(ge=0)
    radiation_mj: float = Field(ge=0)
    daylight_h: float = Field(ge=0, le=24)
    wet_hours: int = Field(ge=0, le=24)
    is_forecast: bool


class Environment(BaseModel):
    lat: float
    lon: float
    days: list[DailyWeather]
    # open-sky shortwave (W/m²) for the photo's date, hours 0-23 London; the value at hour
    # H is the mean of the hour before H (C1). Empty in records made before C1.
    sky_hours: list[float | None] = Field(default_factory=list)
    # the fixed UTC offset Open-Meteo labelled those hours in; None in records before it
    sky_utc_offset_s: int | None = None
    source: str


LocationSource = Literal["photo", "device", "typed", "sample", "home"]


class Location(BaseModel):
    """Where the plant is, rounded to 2 decimals (about 1 km) on construction (D29)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    source: LocationSource
    label: str = ""

    @field_validator("lat", "lon")
    @classmethod
    def _round(cls, v: float) -> float:
        return round(v, 2)


LightNow = Literal["direct_sun", "bright_shade", "deep_shade"]
LightClass = Literal["sun", "part_shade", "shade"]
LightMissing = Literal[
    "no_exposure", "no_time", "no_sky", "dark", "flash", "implausible", "indoors"
]


class LightReading(BaseModel):
    """Light at the plant at the moment of one photo (C1, D53): photo lux over open-sky
    lux for that place and minute. A moment, not a verdict on the spot."""

    fraction: float = Field(ge=0)
    now: LightNow
    local_time: datetime  # London wall time of the photo, no zone
    lux: float = Field(ge=0)
    sky_wm2: float = Field(ge=0)
    route: Literal["shutter", "brightness"]


AspectSource = Literal["compass", "tapped_direction", "history", "none"]


class Aspect(BaseModel):
    """Which way a spot faces and how high its main obstacle is (spot spec section 4, D68):
    one compass tap, an 8-way tap, or a reading reused from the person's history."""

    heading_deg: float = Field(ge=0, lt=360)
    pitch_deg: float | None = Field(None, ge=-90, le=90)  # None: no pitch (8-way tap)
    accuracy_deg: float | None = Field(None, ge=0)
    source: AspectSource
    taken_on: date | None = None  # a reused reading's date ("using your reading from 3 Oct")


SunMethod = Literal["compass", "direction", "defaults"]
CrossCheck = Literal["agrees", "disagrees", "not_run"]


class SunHours(BaseModel):
    """Clear-day direct-sun hours by month (spot spec section 6, D71): (low, mid, high) on
    the 15th of each month, Jan..Dec. Clear-day hours: never multiplied by sunshine."""

    months: list[tuple[float, float, float]] = Field(min_length=12, max_length=12)
    june_class: LightClass  # the class of June's mid hours (RHS: 6 h sun, 3 h part shade)
    borderline: bool  # June's low and high fall in different classes
    method: SunMethod
    cross_check: CrossCheck = "not_run"

    @property
    def winter_dark(self) -> bool:
        """Under 1 h of direct sun in mid-December: winter growth stops."""
        return self.months[11][1] < 1.0


TextureBand = Literal["sandy", "loamy", "clayey"]
TEXTURE_BANDS: tuple[TextureBand, ...] = ("sandy", "loamy", "clayey")


class TexturePrior(BaseModel):
    """How likely each soil texture band is at a spot (spot spec section 4, D69)."""

    probs: dict[TextureBand, float]
    source: Literal["squeeze", "map", "map+photo", "none"]
    map_class: str | None = None  # the BGS texture words, e.g. "LOAM TO CLAY"
    urban: bool = False

    @property
    def top(self) -> TextureBand:
        return max(TEXTURE_BANDS, key=lambda b: self.probs.get(b, 0.0))

    @property
    def p_clayey(self) -> float:
        return self.probs.get("clayey", 0.0)


class PhRange(BaseModel):
    low: float | None = Field(None, ge=3, le=9)
    high: float | None = Field(None, ge=3, le=9)
    lime: bool | None = None
    source: Literal["ukceh_cs", "kit", "none"]


class FrostNormals(BaseModel):
    """Frost and sun normals at a spot (spot spec section 5): HadUK-Grid 1991-2020 at the
    1 km cell, and the typical coldest night from ERA5-Land (median of 30 annual minima)."""

    air_frost_by_month: list[float] | None = Field(None, min_length=12, max_length=12)
    ground_frost_year: int | None = None
    coldest_month_min_c: float | None = None
    typical_coldest_night_c: float | None = None
    sunshine_year_h: int | None = None
    sources: list[str] = Field(default_factory=list)

    @property
    def air_frost_year(self) -> float | None:
        if self.air_frost_by_month is None:
            return None
        return round(sum(self.air_frost_by_month), 1)


ChipName = Literal["Sun", "Soil", "Frost", "Timing"]


class PickChip(BaseModel):
    name: ChipName
    value: str  # Sun: fits/borderline/unknown; Soil: fits/fix needed/not known;
    # Frost: fine/fleece/not needed/not known; Timing: now/from next month/sources differ
    source: str  # where the value came from: "compass", "maps (BGS)", "HadUK-Grid", ...


PickAction = Literal["sow_outdoors", "plant_out", "sow_indoors", "windowsill"]


class GrowPick(BaseModel):
    crop_id: str
    name: str
    action: PickAction
    do: str  # what to do this month: "Sow outdoors", "Plant out", "Start on a windowsill"
    chips: list[PickChip]
    reasons: list[str]  # why it fits, and what would make it fail
    sources: list[str]  # the calendar row's source links


class GrowList(BaseModel):
    """What to grow here (spot spec section 7, D72). Built from the calendar's facts; no
    model call ranks or writes it."""

    month: int = Field(ge=1, le=12)
    good_now: list[GrowPick] = Field(default_factory=list)
    worth_a_try: list[GrowPick] = Field(default_factory=list)
    coming_up: list[GrowPick] = Field(default_factory=list)
    not_here: list[GrowPick] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class KnowledgePack(BaseModel):
    species: str
    common_name: str
    kc: float = Field(gt=0, le=1.5)
    water_need: str
    sun: str
    frost_damage_c: float
    frost_severe_c: float
    notes: str = ""
    sources: list[str] = Field(default_factory=list)
    verified: bool = False
    found_with: str | None = None  # the search that found its RHS page ("tavily", "tinyfish")


class RiskDay(BaseModel):
    date: date
    water_stress: float = Field(ge=0, le=1)
    frost: float = Field(ge=0, le=1)
    # the bucket at the end of the day, in mm like PlantState.water_mm; None on records
    # saved before 18 Oct (Compare draws it as a line)
    soil_water_mm: float | None = Field(default=None, ge=0)


class RiskStrip(BaseModel):
    action: Action
    days: list[RiskDay]


class PlantState(BaseModel):
    water_mm: float = Field(ge=0)
    capacity_mm: float = Field(gt=0)
    volumetric: float = Field(ge=0, le=1)
    strips: list[RiskStrip]
    needs_water_mm: float | None = Field(default=None, ge=0)  # the twin's watering trigger
    assumptions: list[str] = Field(default_factory=list)


Effect = Literal["raises", "lowers", "missing", "neutral"]
# the input tell_me asks for
TellMe = Literal["location", "soil_feel", "setting", "aspect", "soil_texture"]
# what is wrong with a photo the read called poor and could not name the plant from: the
# answer says so up front and asks for a better one (confidence.photo_issue)
PhotoIssue = Literal["blurry", "dark", "small", "unclear"]


class Factor(BaseModel):
    """One thing that moved confidence, shown in the answer's factor list (D26, D28)."""

    name: str  # "season", "photo_quality", "plant_model", ...
    effect: Effect
    detail: str  # "mentha: normal dieback is normal in October"


class Chip(BaseModel):
    name: str  # one of confidence.CHIPS
    effect: Effect
    why: list[str] = Field(default_factory=list)  # the details behind it, shown beside it


class StageFailure(BaseModel):
    stage: str
    message: str
    raw: str | None = None


class Advice(BaseModel):
    """An answer to a plant question: the actions it recommends and the text shown."""

    actions: list[CareAction]
    primary: CareAction
    answer: str
    ask: str = ""  # a follow-up question, when the answer could change with it
    confidence: Literal["high", "low"] = "high"  # low needs a follow-up question

    @field_validator("actions")
    @classmethod
    def _non_empty_unique(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("no actions listed")
        return sorted(set(v))

    @model_validator(mode="after")
    def _primary_listed(self) -> Advice:
        if self.confidence == "low" and not self.ask.strip():
            raise ValueError("low confidence needs a follow-up question in ask")
        extra = {self.primary} | ({"ask_first"} if self.ask.strip() else set())
        if not extra <= set(self.actions):
            self.actions = sorted({*self.actions, *extra})
        return self


SoilFeel = Literal["dry", "cool", "damp", "wet"]
LastWatered = Literal["today", "1_2_days", "3_7_days", "longer", "not_sure"]
Changed = Literal["moved", "repotted", "new_plant", "nothing"]
SOIL_FEEL_TEXT: dict[str, str] = {
    "dry": "dry",
    "cool": "cool but not moist",
    "damp": "damp",
    "wet": "wet",
}
LAST_WATERED_TEXT: dict[str, str] = {
    "today": "today",
    "1_2_days": "1 to 2 days ago",
    "3_7_days": "3 to 7 days ago",
    "longer": "more than a week ago",
    "not_sure": "not sure",
}
CHANGED_TEXT: dict[str, str] = {
    "moved": "moved",
    "repotted": "repotted",
    "new_plant": "new plant",
    "nothing": "nothing",
}
MAX_QUESTION = 500
Squeeze = Literal["gritty", "smooth", "sticky"]
SQUEEZE_TEXT: dict[str, str] = {
    "gritty": "gritty, falls apart, no ribbon",
    "smooth": "smooth or soapy, ribbon under 2.5 cm",
    "sticky": "sticky, ribbon 2.5 cm or longer",
}
SQUEEZE_BAND: dict[str, TextureBand] = {"gritty": "sandy", "smooth": "loamy", "sticky": "clayey"}
Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class HeadingTap(BaseModel):
    """One compass tap (heading, pitch, accuracy) or an 8-way tap (spot spec section 4).
    User input: validated here, at the boundary."""

    model_config = ConfigDict(extra="forbid")

    heading: float | None = Field(None, ge=0, lt=360, allow_inf_nan=False)
    pitch: float | None = Field(None, ge=-90, le=90, allow_inf_nan=False)
    accuracy: float | None = Field(None, ge=0, le=360, allow_inf_nan=False)
    direction: Direction | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> HeadingTap:
        if (self.heading is None) == (self.direction is None):
            raise ValueError("give a compass heading or a direction, not both or neither")
        if self.direction is not None and (self.pitch is not None or self.accuracy is not None):
            raise ValueError("a direction tap has no pitch or accuracy")
        return self

    def aspect(self) -> Aspect:
        if self.direction is not None:
            from herbtwin.compass import direction_heading

            return Aspect(heading_deg=direction_heading(self.direction), source="tapped_direction")
        return Aspect(
            heading_deg=self.heading,
            pitch_deg=self.pitch,
            accuracy_deg=self.accuracy,
            source="compass",
        )


class Told(BaseModel):
    """What the person told us under the answer (spec section 4). User input: validated
    here, and only ever shown to a model inside the fenced YOU TOLD US block."""

    model_config = ConfigDict(extra="forbid")

    soil_feel: SoilFeel | None = None
    last_watered: LastWatered | None = None
    changed: Changed | None = None
    question: str | None = Field(None, max_length=MAX_QUESTION)
    place: str | None = Field(None, max_length=80)
    squeeze: Squeeze | None = None  # the squeeze test (spot spec section 4)
    heading: HeadingTap | None = None  # the compass or 8-way tap
    # "Wrong? Switch": the person says the read got indoors or outdoors wrong
    setting: Literal["indoor", "outdoor"] | None = None

    @field_validator("question", "place")
    @classmethod
    def _plain_text(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())  # newlines and tabs become single spaces
        if not v.isprintable():
            raise ValueError(f"the {info.field_name} has characters that are not plain text")
        return v or None

    def is_empty(self) -> bool:
        return not (
            self.soil_feel
            or self.last_watered
            or self.changed
            or self.question
            or self.place
            or self.setting
            or self.squeeze
            or self.heading
        )

    def switch_only(self) -> bool:
        """All that was told is the Indoors/Outdoors switch."""
        return bool(self.setting) and self.model_copy(update={"setting": None}).is_empty()


class ActionCard(BaseModel):
    action: CareAction
    when: Literal["today", "this_week", "keep_an_eye"]
    because: str  # one line naming the evidence
    if_you_do: str  # consequence, or "no reliable data on what this changes"
    if_you_do_from: Literal["plant_model", "outcome_table", "norm_rule", "web_search", "none"]
    less_sure: bool  # literature-based consequence
    if_you_do_url: str | None = None  # web_search: the page the quote is from
    found_with: str | None = None  # web_search: the search provider that found it

    @field_validator("if_you_do_url")
    @classmethod
    def _trusted_link(cls, v: str | None) -> str | None:
        """Checked again on every read, as WebHow.url: it becomes a link. A stored one that
        fails is dropped, and the card shows its words with no link."""
        return v if v is None or _trusted(v) else None

    @property
    def site(self) -> str:
        """The quoted page's host, without "www.": "rhs.org.uk"."""
        host = urlsplit(self.if_you_do_url or "").hostname or ""
        return host.removeprefix("www.")


class CompareRow(BaseModel):
    action: CareAction
    vs_leaving_it: Literal["better", "same", "worse", "unknown"]
    why: str


Signal = Literal["posture", "tissue", "colour"]
Change = Literal["more", "less", "same"]
DidIt = Literal["yes", "partly", "no", "skip"]
ScoreResult = Literal[
    "improved", "no_clear_change", "worse", "cant_tell", "not_done", "not_scored_yet"
]


class Prediction(BaseModel):
    """What the main action should do to one signal by the next photo (C2, spec section
    4), saved with the answer so a later score tests what was actually said."""

    action: CareAction
    signal: Signal
    expected: Literal["less", "not_more"]
    window_days: tuple[int, int]  # a follow-up this many days later is checked
    less_sure: bool = False
    before: int | None = None  # the signal in this photo, 0 to 3 (droop or decline)
    source: str


class Look(BaseModel):
    """One of a comparison's four calls, read as the later photo against the earlier."""

    prompt: Literal["plain", "timed"]
    order: Literal["earlier_first", "later_first"]
    raw: str
    change: Change | None  # None when the reply could not be read
    confidence: Literal["low", "medium", "high"] | None


class Comparison(BaseModel):
    signal: Signal
    verdict: Literal["more", "less", "same", "cant_tell"]
    reason: str | None  # why it can't tell, in plain words
    looks: list[Look]
    prompt_version: str
    model: str


class IndoorNow(BaseModel):
    """An indoor answer's month: what is normal on a windowsill or in a room now, and how to
    look after it (indoor_care.py; 21 Oct, a gardener: indoor "doesn't have much info")."""

    month: int = Field(ge=1, le=12)
    normal: str
    tips: list[str]
    sources: list[str]


class Answer(BaseModel):
    """What the page and the JSON API show (spec section 7)."""

    headline: str  # "Leave it. This is normal for October."
    # specialist advisors' roles ("soil and water", …) when such a panel ran; empty for the
    # panel of one model asked three times (stages/advise.advisors_said)
    advisor_roles: list[str] = Field(default_factory=list)
    do: list[ActionCard] = Field(max_length=3)  # primary first, tagged "today"
    dont: ActionCard | None  # the tempting move the plant model rates worse
    watch: str  # from the norm's problem signs: what would change this
    trend: str | None = None  # "droop worse since 3 Oct", from the plant's last visit
    tell_me: str | None  # "Tell us X and we'll tell you Y"
    tell_me_key: TellMe | None = None
    level: Literal["not_sure", "fairly_sure", "sure"]
    level_text: str
    in_ten: int = Field(ge=1, le=10)  # measured hit rate of the level
    factors: list[Factor]
    chips: list[Chip]
    compare: list[CompareRow]  # every choice vs leaving it (closed card on the page)
    runs: list[Advice]  # the advisor replies, for audit
    assumptions: list[str]
    prediction: Prediction | None = None  # C2: what the main action should change
    photo_issue: PhotoIssue | None = None  # a rough read: say so, ask for a better photo
    dont_if_dry: bool = False  # the soil is unknown: the Don't card says to feel it first
    winter_rest: bool = False  # a perennial herb resting: no cut for growth in any reply
    no_cut_growth: bool = False  # resting or seedlings: "You asked" trims cuts for growth too
    tray_check: bool = False  # a pot coming indoors: empty its tray (answer.TRAY_CHECK)
    in_ground: bool = False  # a bed plant: no line says to keep it apart (judge walk, #304)
    # the disease our no-cure rule removes the plant for, when it is named: the photo
    # check's, else the one the advisor named (answer.no_cure_overrides)
    no_cure_of: str | None = None
    # the twin found no dry day ahead, so leaving it leads over the advisors' water call
    # (pipeline.twin_holds_water): the page says so (answer.rule_overrides)
    held_water: bool = False
    indoor: IndoorNow | None = None  # indoors: the month's normal and care tips


SqueezeAsk = Literal["ask", "offer", "no"]


class Spot(BaseModel):
    """What we know about a growing spot (spot spec section 5, D70)."""

    read: SpotRead
    texture: TexturePrior | None = None  # ground only
    ph: PhRange | None = None
    aspect: Aspect | None = None
    sun: SunHours | None = None  # None indoors or with no location
    frost: FrostNormals | None = None
    squeeze: SqueezeAsk = "no"  # the squeeze question: asked, offered in the soil card, or not
    compass: bool = False  # the direction question is still offered under the answer
    direction_matters: bool = False  # which way it faces can change the sun hours here
    notes: list[str] = Field(default_factory=list)


class StepCost(BaseModel):
    """One step of an answer and what it used (herbtwin/receipt.py). `model`: the model id,
    or the service's own name for a step with no model. `ms`: the step's own time. A
    `cost_usd` of None: the model has no listed price, so the cost is not known."""

    stage: str
    model: str
    calls: int = 0
    ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = 0.0


class AnalysisRecord(BaseModel):
    record_id: str
    taken_at: datetime
    taken_at_source: Literal["exif", "assumed"] = "assumed"
    location: Location | None = None
    observation: Observation | None
    environment: Environment | None
    pack: KnowledgePack | None
    state: PlantState | None
    season: SeasonalNorm | None = None
    light: LightReading | None = None  # light at the plant when the photo was taken (C1)
    light_missing: LightMissing | None = None  # why there is no light reading
    answer: Answer | None = None
    told: Told | None = None  # what the person told us, when this answer is a refine
    spot: Spot | None = None  # the spot answer (spot spec D70); None on plant answers
    problem: ProblemSeen | None = None  # a pest or disease the photo check named
    trusted: TrustedCheck | None = None  # a trusted page's sentences (stages/trusted_page.py)
    grow: GrowList | None = None
    refined_from: str | None = None  # the first answer's headline, for "what changed"
    photo_sha256: str | None = None  # the normalized photo's bank key (twin stills)
    receipt: list[StepCost] | None = None  # each step's model, time and cost (receipt.py)
    notes: list[str] = Field(default_factory=list)  # plain-words notes for the page
    failures: list[StageFailure] = Field(default_factory=list)
