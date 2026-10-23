"""Photo -> Observation. The VLM sees; it does not recommend."""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from pydantic import ValidationError

from herbtwin.adapters.base import AdapterError, ModelAdapter, TokenOverrun, extract_json
from herbtwin.schemas import LEAF_COLOURS, Observation

SYSTEM = (
    "You are a careful horticulturist looking at one photo of a potted culinary herb in a UK "
    "garden. Report only what is visible. Do not guess a problem if the plant looks fine: set "
    "fine_leave_it=true in that case. Scores are integers 0 (none) to 3 (severe). "
    "water_stress is posture only: leaves or stems drooping or limp. decline is dead, dried, "
    "brown or crisp tissue, scored separately from posture: a plant can be upright and in "
    "decline, or drooping and otherwise healthy. leaf_colour is the share of yellow leaves "
    "(green, some_yellow, mostly_yellow, or not_visible). "
    "setting is indoor or outdoor when the photo shows it, else unknown. container is pot "
    "(any pot, trough or planter) or ground (bed, border, lawn) when visible, else unknown. "
    "pot_fit, for a plant in a pot: too_small when it has clearly outgrown the pot (roots "
    "out of the drainage holes or over the rim, a root ball that is all roots, or a plant "
    "far wider and taller than its pot and top-heavy), snug when it fills the pot, roomy "
    "when the pot has plenty of space; unknown when there is no pot or you cannot tell. "
    "low_light is signs of too little light: 0 none, 1 slightly stretched or pale, 2 "
    "clearly leggy (long bare stems between the leaves), pale, or leaning to one side "
    "towards the light. A compact, green plant is 0; score it only from the plant's own "
    "shape and colour, never from how bright the photo is. "
    "photo_quality is poor when the photo is blurred, dark, the plant is small in the frame, "
    "or several plants share it; say which in quality_note. "
    "scene is one_plant when the photo is about one kind of plant: a single plant, or a "
    "patch, clump, row or field of the same plant however much of the frame it fills, even "
    "with a few weeds or other plants at the edges. scene is bed_or_border only when "
    "several different kinds of plant grow together in a bed, border, plot or planter, or "
    "the photo shows bare ground or compost ready for planting; no_plant when there is "
    "neither. "
    "If there is no plant in the photo, set is_plant=false. "
    "Reply with JSON only, matching the schema."
)
USER = (
    "Identify the plant and describe its condition. Give at most 3 species candidates, "
    "keep symptoms and leaf_cues to short phrases, and keep notes under 30 words."
)
# up to three photos of the same plant (21 Oct, a gardener tester): said only when there is
# more than one, so a single photo is read with exactly the words it always was
MORE_PHOTOS = (
    "There are {n} photos of the same plant. The first is the main photo; the others are "
    "closer looks, such as a leaf, the stem or the soil and pot. Name the plant from all of "
    "them, and score its condition and soil from whatever any photo shows. Judge "
    "photo_quality and scene from the first photo only."
)
Photos = Sequence[tuple[bytes, str]]  # (bytes, mime) each
log = logging.getLogger(__name__)
# a bad reading slower than this leaves the backup no room: with its one call (up to 90 s
# live) the photo read stays inside the page's 270 s (web/progress.py READ_DEADLINE_S);
# slow advice after it can still meet the page's own "took too long"
BACKUP_WITHIN_S = 120.0
# no reading yet after this long: the backup reads the same photo alongside the first model
# and the first usable reading wins. Live, 21 Oct (Cloud Run + LangSmith, 10 days): GLM's
# read took 9.9 s at the median and 35 s at p95, and a backup that only started after a
# slow or bad GLM reply made the 70-90 s answers. 14 s is past most good reads (so few pay
# for two calls) and well before the slow tail
HEDGE_AFTER_S = 14.0
# reads in flight that may race (web/progress.py runs 8 at once): two threads each, the
# first model's and the backup's. A loser keeps its thread until its call ends (it cannot
# be stopped mid-request, and its reply is still traced), so with no slot free a read
# runs the old way, one model after the other, rather than queue behind them
_RACE_SLOTS = 8
_RACERS = ThreadPoolExecutor(max_workers=2 * _RACE_SLOTS, thread_name_prefix="photo-race")
_FREE = threading.BoundedSemaphore(2 * _RACE_SLOTS)
OBSERVE_MAX_TOKENS = 4096  # vision models that reason before answering ran out at 1024
# several photos: the live 3-photo read (21 Oct) thought for 3,825 of 4,096 tokens
OBSERVE_MORE_MAX_TOKENS = 6144
OBSERVE_SCHEMA = {
    "type": "object",
    "properties": {
        "species": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "common_name": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "common_name", "confidence"],
            },
        },
        "is_plant": {"type": "boolean"},
        "water_stress": {"type": "integer", "minimum": 0, "maximum": 3},
        "decline": {"type": "integer", "minimum": 0, "maximum": 3},
        "leaf_colour": {"type": "string", "enum": list(LEAF_COLOURS)},
        "heat_light_stress": {"type": "integer", "minimum": 0, "maximum": 3},
        "fine_leave_it": {"type": "boolean"},
        "symptoms": {"type": "array", "items": {"type": "string"}},
        "leaf_cues": {"type": "array", "items": {"type": "string"}},
        "soil_surface": {"type": "string", "enum": ["dry", "moist", "wet", "not_visible"]},
        "notes": {"type": "string"},
        "setting": {"type": "string", "enum": ["indoor", "outdoor", "unknown"]},
        "container": {"type": "string", "enum": ["pot", "ground", "unknown"]},
        "pot_fit": {"type": "string", "enum": ["roomy", "snug", "too_small", "unknown"]},
        "low_light": {"type": "integer", "minimum": 0, "maximum": 2},
        "photo_quality": {"type": "string", "enum": ["good", "poor"]},
        "quality_note": {"type": "string"},
        "scene": {"type": "string", "enum": ["one_plant", "bed_or_border", "no_plant"]},
    },
    "required": [
        "species",
        "is_plant",
        "water_stress",
        "decline",
        "leaf_colour",
        "heat_light_stress",
        "fine_leave_it",
        "symptoms",
        "leaf_cues",
        "soil_surface",
        "setting",
        "container",
        "photo_quality",
        "scene",
    ],
}


class ObserveError(Exception):
    def __init__(self, message: str, raw: str, *, unusable: bool = False) -> None:
        super().__init__(message)
        self.raw = raw
        self.unusable = unusable  # the model answered, but not with a reading we can use


class _NeitherRead(ObserveError):
    """The first model and the backup raced and neither sent a reading: nothing left to ask."""


# Fields added in plan 2. Live replies must carry them in strict mode; recordings made
# before them still parse through the model defaults.
STRICT_FIELDS = ("decline", "leaf_colour")
# The phase A fields (setting, container, photo_quality), scene and pot_fit are asked for
# but never scored by the eval harness, so a reply without them falls back to its default
# even in strict mode. pot_fit is not even required: a reply may leave it out.


def _parse(raw: str, strict: bool = False) -> Observation:
    text = extract_json(raw)
    obs = Observation.model_validate_json(text)
    if strict:
        missing = [k for k in STRICT_FIELDS if k not in json.loads(text)]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")
    if not obs.is_plant:
        return obs.model_copy(
            update={
                "species": [],
                "water_stress": 0,
                "decline": 0,
                "leaf_colour": "not_visible",
                "heat_light_stress": 0,
                "fine_leave_it": False,
                "scene": "bed_or_border" if obs.scene == "bed_or_border" else "no_plant",
                "pot_fit": "unknown",  # no plant has outgrown nothing
                "low_light": None,  # no plant, no light signs
            }
        )
    if obs.container == "ground" and obs.pot_fit != "unknown":
        return obs.model_copy(update={"pot_fit": "unknown"})  # a plant in the ground has no pot
    return obs


def observe(
    adapter: ModelAdapter,
    image: bytes,
    mime: str,
    few_shot: list[str] | None = None,
    *,
    strict: bool = False,
    clock: Callable[[], float] = time.monotonic,
    more: Photos = (),
    hedge_after_s: float | None = HEDGE_AFTER_S,
    won_by: Callable[[str | None], None] | None = None,
    first_failed: Callable[[], None] | None = None,
) -> Observation:
    """One vision call (plus one repair). `more`: up to two more photos of the same plant,
    sent with the main one in that same call, with more room to answer; a provider that
    takes one image per call reads the main photo alone, and so does a read of several
    still unusable after its repair when there is no backup model. strict=True, used by the eval harness, treats a
    reply missing a plan 2 field as invalid instead of filling the default, so an omitted
    decline score is never counted as "no decline". A reply still unusable after its repair
    gets one call to the backup photo model, when there is one and time is left for it.
    A read with no reading after `hedge_after_s` races the backup (see _race); strict reads
    never do, so an eval scores the model it names. `won_by` hears the model whose
    reading won a race (the loser's call is traced too, and may be traced after it);
    `first_failed` hears that the backup won it after the first model had failed, not only
    been slow (the wait says which: pipeline.backup_read)."""
    start = clock()
    if more and not _takes_several(adapter):
        log.warning("%s takes one image per call: reading the main photo only", adapter.name)
        more = ()
    photos = [(image, mime), *more]
    try:
        if hedge_after_s is None or strict:
            return _read(adapter, photos, few_shot, strict)
        return _race(adapter, photos, few_shot, strict, hedge_after_s, won_by, first_failed)
    except ObserveError as e:
        several = len(photos) > 1
        raced = isinstance(e, _NeitherRead)  # the backup has had its call already
        if not several and (raced or not e.unusable):
            raise
        took = clock() - start
        if took > BACKUP_WITHIN_S:
            log.warning("no usable reading after %.0f s: no time left for a backup", took)
            raise
        backup = adapter.backup_for_unusable() if e.unusable and not raced else None
        if backup is not None:
            return _read(backup, photos, few_shot, strict, repair=False)
        if not several:
            raise
        # several photos and still no reading (cut off twice, or the call refused): the main
        # photo alone, as one photo is always read, rather than no answer at all
        log.warning("no reading of %d photos (%s): reading the main photo alone", len(photos), e)
        return _read(adapter, photos[:1], few_shot, strict, repair=False)


def _race(
    adapter: ModelAdapter,
    photos: Photos,
    few_shot: list[str] | None,
    strict: bool,
    hedge_after_s: float,
    won_by: Callable[[str | None], None] | None = None,
    first_failed: Callable[[], None] | None = None,
) -> Observation:
    """The first model's read (with its repair) and, when it has no reading after
    `hedge_after_s`, the backup's one call on the same photos: the first usable reading
    wins and the other call is left to finish on its own (it is still traced under its own
    model). A first reply that is unusable before then raises as it always did, so
    observe() hands the photo to the backup at once. Both failing raises _NeitherRead (for
    several photos observe() then reads the main photo alone, as it always did)."""
    if type(adapter).backup_to_race is ModelAdapter.backup_to_race:
        return _read(adapter, photos, few_shot, strict)  # no backup to race
    first = _start(_read, adapter, photos, few_shot, strict)
    if first is None:  # every slot busy: one model after the other, as before
        return _read(adapter, photos, few_shot, strict)
    done, _ = wait([first], timeout=hedge_after_s)
    second = None
    # the backup's slot is taken before it is asked for: with none free the first model
    # keeps its own fallback (on an error, and backup_for_unusable after a bad reply)
    if not done and _FREE.acquire(blocking=False):
        backup = adapter.backup_to_race()
        if backup is None:
            _FREE.release()
        else:
            second = _submit(_read, backup, photos, few_shot, strict, repair=False)
            if second is None:  # the pool is shutting down: the backup was never asked
                adapter.racing = adapter.used_backup = False
    if second is None:  # read in time, no backup to race, or no room for it
        return first.result()
    errors: dict[Future, ObserveError] = {}
    racing = {first, second}
    while racing:
        done, racing = wait(racing, return_when=FIRST_COMPLETED)
        for job in (first, second):  # the first model's reading wins a tie
            if job not in done:
                continue
            try:
                obs = job.result()
            except ObserveError as e:
                errors[job] = e
                continue
            # racing, the first lane only ever asks the first model (FallbackAdapter.racing)
            lane = backup if job is second else getattr(adapter, "first", adapter)
            model = getattr(lane, "model", None)
            log.info("photo read by %s after a race", model)
            if won_by is not None:
                won_by(model)
            if job is second and first in errors and first_failed is not None:
                first_failed()
            return obs
    # both have failed (the loop ends only once both are done); as when the backup is
    # asked after the first model, its error is the one raised
    last = errors[second]
    raise _NeitherRead(str(last), last.raw, unusable=last.unusable) from last


def _start(fn: Callable[..., Observation], *args, **kwargs) -> Future | None:
    """`fn` on a racer thread; None when no slot is free."""
    if not _FREE.acquire(blocking=False):
        log.info("no free photo-race slot: reading one model after the other")
        return None
    return _submit(fn, *args, **kwargs)


def _submit(fn: Callable[..., Observation], *args, **kwargs) -> Future | None:
    """`fn` on a racer thread, in this context, holding a slot already taken (given back
    when it ends); None when the pool is shutting down."""
    try:
        job = _RACERS.submit(contextvars.copy_context().run, fn, *args, **kwargs)
    except RuntimeError:
        _FREE.release()
        return None
    job.add_done_callback(lambda _: _FREE.release())
    return job


def _takes_several(adapter: ModelAdapter) -> bool:
    """Whether this provider sends several images in one call (the base class refuses)."""
    return type(adapter).complete_with_images is not ModelAdapter.complete_with_images


def _look(adapter: ModelAdapter, user: str, photos: Photos) -> str:
    """One call to the photo model: the single-photo call as it always was, or every photo
    in one call. A reply cut off at max_tokens comes back empty, so it is repaired like any
    other reply that is not the reading."""
    if len(photos) == 1:
        image, mime = photos[0]
        return adapter.complete_with_image(
            SYSTEM, user, image, mime, OBSERVE_SCHEMA, max_tokens=OBSERVE_MAX_TOKENS
        )
    system = SYSTEM.replace("looking at one photo of", "looking at photos of")
    try:
        return adapter.complete_with_images(
            system, user, list(photos), OBSERVE_SCHEMA, max_tokens=OBSERVE_MORE_MAX_TOKENS
        )
    except TokenOverrun:
        log.warning("read of %d photos cut off at %d tokens", len(photos), OBSERVE_MORE_MAX_TOKENS)
        return ""


def _read(
    adapter: ModelAdapter,
    photos: Photos,
    few_shot: list[str] | None,
    strict: bool,
    *,
    repair: bool = True,
) -> Observation:
    user = USER
    if len(photos) > 1:
        user += " " + MORE_PHOTOS.format(n=len(photos))
    if few_shot:
        user += "\n\nExamples of the expected scoring:\n" + "\n".join(few_shot)
    try:
        raw = _look(adapter, user, photos)
    except AdapterError as e:
        raise ObserveError(f"vision model call failed: {e}", "") from e
    try:
        return _parse(raw, strict)
    except (ValueError, ValidationError) as first:
        if not repair:
            raise ObserveError(f"observe output invalid: {first}", raw, unusable=True) from first
        again = (
            f"{user}\n\nYour previous reply was not valid JSON for the schema:\n---\n{raw}\n---\n"
            f"Problem: {first}\nReply again with JSON only."
        )
        try:
            raw2 = _look(adapter, again, photos)
        except AdapterError as e:
            raise ObserveError(f"vision model call failed on repair: {e}", raw) from e
        try:
            return _parse(raw2, strict)
        except (ValueError, ValidationError) as second:
            raise ObserveError(
                f"observe output invalid after repair: {second}", raw2, unusable=True
            ) from second


def to_prompt_summary(obs: Observation) -> str:
    """Compact text for downstream prompts."""
    top = obs.species[0] if obs.species else None
    return json.dumps(
        {
            "species": top.name if top else None,
            "confidence": top.confidence if top else 0,
            "water_stress": obs.water_stress,
            "decline": obs.decline,
            "leaf_colour": obs.leaf_colour,
            "heat_light_stress": obs.heat_light_stress,
            "fine_leave_it": obs.fine_leave_it,
            "symptoms": obs.symptoms,
            "soil_surface": obs.soil_surface,
            "setting": obs.setting,
            "container": obs.container,
            "pot_fit": obs.pot_fit,
            "photo_quality": obs.photo_quality,
        }
    )
