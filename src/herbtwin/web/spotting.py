"""The spot answer's server memory (spot spec D67): each spot's reading for an hour, and
the person's answers to its questions, which may arrive before the reading finishes (the
direction is asked while the photo is read). Bounded, owner-checked, like AnswerCache.
Also the page's shape: the groups of crops, a short line each, the top picks and what is
not fine about each one."""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from herbtwin.history import HistoryError, StoredSpot
from herbtwin.schemas import GrowList, GrowPick, PickChip, Spot, Told
from herbtwin.spot import LEAD_NOTE, SHOWN_TIERS, SpotRun, SpotTold

log = logging.getLogger(__name__)

TTL = timedelta(hours=1)
MAX_ENTRIES = 500
REUSE_DAYS = 60  # a direction or compass reading at the same rounded place is reused this long
TOP_PICKS = 5  # crops a group shows before "N more"; the rest fold away
NAMED = 3  # crops a group's one-line verdict names before "and N more"
# chip values that say nothing a gardener needs: a row shows only the others ("from next
# month" is already in a coming-up crop's action, "From November: plant out")
FINE = frozenset({"fits", "fine", "not needed", "now", "from next month"})
CHECK = frozenset({"borderline", "fix needed", "fleece", "sources differ", "too shady"})
GROUPS = (  # key, heading, tone (the colour's meaning, always beside the words)
    ("good_now", "Good now", "good"),
    ("worth_a_try", "Worth a try", "check"),
    ("coming_up", "Coming up", "later"),
    ("not_here", "Not here", "no"),
)


@dataclass
class SpotEntry:
    owner: str | None
    at: datetime
    run: SpotRun | None = None  # None while the photo is still being read
    answers: SpotTold = field(default_factory=SpotTold)


def merge(old: SpotTold, new: SpotTold) -> SpotTold:
    """Later answers win field by field; an answer not given keeps the earlier one."""
    told = Told(
        **{**old.told.model_dump(exclude_none=True), **new.told.model_dump(exclude_none=True)}
    )
    return SpotTold(
        told=told, setting=new.setting or old.setting, pot_size=new.pot_size or old.pot_size
    )


class SpotCache:
    def __init__(
        self, clock: Callable[[], datetime], ttl: timedelta = TTL, max_entries: int = MAX_ENTRIES
    ) -> None:
        self._clock, self._ttl, self._max = clock, ttl, max_entries
        self._entries: OrderedDict[str, SpotEntry] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def start(self, spot_id: str, owner: str | None) -> None:
        """Make room for answers before the reading finishes."""
        with self._lock:
            self._entries[spot_id] = SpotEntry(owner, self._clock())
            self._trim()

    def finish(self, run: SpotRun, owner: str | None) -> None:
        with self._lock:
            entry = self._entries.get(run.record_id)
            if entry is None or entry.owner != owner:
                entry = SpotEntry(owner, self._clock())
                self._entries[run.record_id] = entry
            entry.run = run
            self._trim()

    def drop(self, spot_id: str) -> None:
        """Forget a spot whose read failed, so a later visit says it expired instead of
        waiting for a reading that will never come."""
        with self._lock:
            self._entries.pop(spot_id, None)

    def get(self, spot_id: str, owner: str | None) -> SpotEntry | None:
        with self._lock:
            entry = self._entries.get(spot_id)
            if entry is None:
                return None
            if self._clock() - entry.at > self._ttl:
                del self._entries[spot_id]
                return None
            return entry if entry.owner == owner else None

    def answer(self, spot_id: str, owner: str | None, new: SpotTold) -> SpotEntry | None:
        entry = self.get(spot_id, owner)
        if entry is None:
            return None
        with self._lock:
            entry.answers = merge(entry.answers, new)
        return entry

    def _trim(self) -> None:
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)


def history_note(run: SpotRun) -> str | None:
    """Says which earlier reading stands in: an 8-way pick has no pitch, a compass tap has."""
    a = run.history_aspect
    if a is None or a.taken_on is None:
        return None
    on = f"{a.taken_on.day} {a.taken_on:%b}"
    if a.pitch_deg is None:
        return f"Using the direction you picked here on {on}."
    return f"Using your compass reading from {on}."


def reuse_aspect(person, run: SpotRun, now: datetime) -> None:
    """A signed-in person's 8-way or compass reading at the same rounded place in the last
    60 days stands in until they answer again (section 4). History down: no reuse."""
    if person is None or run.location is None:
        return
    try:
        got = person.store.recent_aspect(run.location, now - timedelta(days=REUSE_DAYS))
    except HistoryError:
        log.exception("could not read earlier spots; not reusing a direction")
        return
    if got is not None:
        aspect, at = got
        run.history_aspect = aspect.model_copy(update={"source": "history", "taken_on": at.date()})


def remember_spot(person, run: SpotRun, answers: SpotTold, spot: Spot, grow: GrowList) -> None:
    """Keep a signed-in person's spot answer, with only a reading they gave this time."""
    if person is None:
        return
    tap = answers.told.heading.aspect() if answers.told.heading else None
    row = StoredSpot(
        id=str(uuid.UUID(run.record_id)),
        taken_at=run.taken_at,
        place=run.location,
        aspect=tap,
        spot=spot,
        grow=grow,
    )
    try:
        person.store.save_spot(row)
    except HistoryError:
        log.exception("could not save the spot answer")


@dataclass(frozen=True)
class Row:
    """One crop on the page: only the conditions that are not fine, and one source."""

    pick: GrowPick
    flags: list[tuple[PickChip, str]]  # each with its tone: "check" (amber) or "quiet"
    source: str | None  # the first https source, shown as one small link
    host: str | None


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    tone: str  # good, check, later, no
    rows: list[Row]

    @property
    def top(self) -> list[Row]:
        return self.rows[:TOP_PICKS]

    @property
    def rest(self) -> list[Row]:
        return self.rows[TOP_PICKS:]

    @property
    def line(self) -> str:
        """The group in a line: "garlic, shallot, chives and 29 more"."""
        names = [short_name(r.pick.name) for r in self.rows[:NAMED]]
        left = len(self.rows) - len(names)
        if left:
            return f"{', '.join(names)} and {left} more"
        return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def short_name(name: str) -> str:
    """A crop as it reads mid-sentence: no bracketed varieties, lower case after a capital
    word ("Onion (overwintering...)" -> "onion"); an acronym or a proper name stays."""
    name = name.split(" (", 1)[0].strip()
    return name[:1].lower() + name[1:] if name[1:2].islower() else name


def flags(pick: GrowPick) -> list[PickChip]:
    """The chips worth reading: never "Sun: fits", "Soil: fits", "Frost: fine", "Timing: now"."""
    return [c for c in pick.chips if c.value not in FINE]


def _row(pick: GrowPick) -> Row:
    url = next((u for u in pick.sources if u.startswith("https://")), None)
    host = url.split("/")[2].removeprefix("www.") if url else None
    marked = [(c, "check" if c.value in CHECK else "quiet") for c in flags(pick)]
    return Row(pick=pick, flags=marked, source=url, host=host)


def groups(grow: GrowList, more: dict[str, list[GrowPick]]) -> list[Group]:
    """Every group with a crop in it, each in full: the shown tiers' folded rest included."""
    out = []
    for key, title, tone in GROUPS:
        picks = list(getattr(grow, key)) + (list(more.get(key, [])) if key in SHOWN_TIERS else [])
        if picks:
            out.append(Group(key, title, tone, [_row(p) for p in picks]))
    return out


def split_lead(notes: list[str]) -> tuple[list[str], str | None]:
    """The lead-in-soil note leaves the top of the page for the soil details."""
    return [n for n in notes if n != LEAD_NOTE], LEAD_NOTE if LEAD_NOTE in notes else None
