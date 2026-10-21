import asyncio
from datetime import UTC, date, datetime, timedelta

from herbtwin.schemas import Aspect, HeadingTap, SpotRead, Told
from herbtwin.spot import SpotRun, SpotTold
from herbtwin.web.progress import PAD, SPOT_HEAD, stream
from herbtwin.web.spotting import SpotCache, history_note, merge

T0 = datetime(2026, 10, 4, 9, tzinfo=UTC)


def _run(rid="a" * 32):
    return SpotRun(record_id=rid, taken_at=T0, taken_at_source="exif", location=None,
                   read=SpotRead(), cell=None, coldest_c=None, light=None)  # fmt: skip


def test_an_early_tap_waits_for_the_reading():
    now = [T0]
    cache = SpotCache(lambda: now[0])
    cache.start("a" * 32, None)
    tap = SpotTold(told=Told(heading=HeadingTap(heading=190, pitch=25)))
    assert cache.answer("a" * 32, None, tap) is not None
    cache.finish(_run(), None)
    entry = cache.get("a" * 32, None)
    assert entry.run is not None and entry.answers.told.heading.heading == 190


def test_owner_checked_and_expires():
    now = [T0]
    cache = SpotCache(lambda: now[0])
    cache.finish(_run(), "user-1")
    assert cache.get("a" * 32, None) is None and cache.get("a" * 32, "user-2") is None
    assert cache.answer("a" * 32, None, SpotTold()) is None
    now[0] = T0 + timedelta(hours=2)
    assert cache.get("a" * 32, "user-1") is None


def test_a_dropped_spot_is_gone():
    cache = SpotCache(lambda: T0)
    cache.start("a" * 32, None)
    cache.drop("a" * 32)
    assert cache.get("a" * 32, None) is None
    cache.drop("missing")  # dropping twice is harmless


def test_later_answers_win_field_by_field():
    first = SpotTold(told=Told(squeeze="sticky"), setting="raised_bed")
    later = SpotTold(told=Told(heading=HeadingTap(direction="S")), pot_size="large")
    got = merge(first, later)
    assert got.told.squeeze == "sticky" and got.told.heading.direction == "S"
    assert (got.setting, got.pot_size) == ("raised_bed", "large")
    assert merge(got, SpotTold(told=Told(squeeze="gritty"))).told.squeeze == "gritty"


def test_bounded():
    cache = SpotCache(lambda: T0, max_entries=2)
    for i in range(3):
        cache.start(str(i) * 32, None)
    assert cache.get("0" * 32, None) is None and cache.get("2" * 32, None) is not None


def test_the_spot_head_never_mentions_my_plants_and_the_card_follows_it():
    """A spot read is never listed in My plants (plan amendment 2)."""

    async def go():
        work = lambda say: "/spots/x"  # noqa: E731
        return [c async for c in stream(work, head=SPOT_HEAD, extra="<form>card</form>")]

    chunks = asyncio.run(go())
    assert chunks[0] == SPOT_HEAD and len(SPOT_HEAD.encode()) >= PAD
    assert "My plants" not in SPOT_HEAD and "/plants" not in SPOT_HEAD
    assert "your photo is not kept" in SPOT_HEAD
    assert chunks[1] == "</ol>\n<form>card</form>\n<ol>\n"


def test_the_history_note_names_the_kind_of_reading():
    run, on = _run(), date(2026, 10, 3)
    run.history_aspect = Aspect(heading_deg=180, source="history", taken_on=on)
    assert history_note(run) == "Using the direction you picked here on 3 Oct."
    run.history_aspect = Aspect(heading_deg=191, pitch_deg=30, source="history", taken_on=on)
    assert history_note(run) == "Using your compass reading from 3 Oct."
    run.history_aspect = None
    assert history_note(run) is None


def _pick(name, **chips):
    from herbtwin.schemas import GrowPick, PickChip

    return GrowPick(crop_id=name.lower(), name=name, action="plant_out", do="Plant out",
                    chips=[PickChip(name=k, value=v, source="x") for k, v in chips.items()],
                    reasons=[], sources=["http://a.example/x", "https://www.rhs.org.uk/g"])  # fmt: skip


def test_a_row_shows_only_the_conditions_that_are_not_fine():
    from herbtwin.web.spotting import _row

    row = _row(_pick("Garlic", Sun="fits", Soil="fix needed", Frost="not known", Timing="now"))
    assert [(c.name, c.value, tone) for c, tone in row.flags] == [
        ("Soil", "fix needed", "check"),
        ("Frost", "not known", "quiet"),
    ]
    assert row.source == "https://www.rhs.org.uk/g" and row.host == "rhs.org.uk"


def test_groups_take_the_folded_rest_and_say_themselves_in_a_line():
    from herbtwin.schemas import GrowList
    from herbtwin.web.spotting import groups

    shown = [_pick(n) for n in ("Onion (sets)", "Chives", "Sea kale", "Mint", "Sorrel")]
    rest = [_pick(n) for n in ("Sage", "Thyme")]
    grow = GrowList(month=10, good_now=shown, coming_up=[_pick("Quince")])
    good, coming = groups(grow, {"good_now": rest})
    assert [g.key for g in (good, coming)] == ["good_now", "coming_up"]  # empty groups gone
    assert len(good.top) == 5 and [r.pick.name for r in good.rest] == ["Sage", "Thyme"]
    assert good.line == "onion, chives, sea kale and 4 more"
    assert coming.line == "quince" and coming.tone == "later" and not coming.rest


def test_the_lead_note_is_split_from_the_others():
    from herbtwin.spot import LEAD_NOTE
    from herbtwin.web.spotting import split_lead

    assert split_lead(["a", LEAD_NOTE, "b"]) == (["a", "b"], LEAD_NOTE)
    assert split_lead(["a"]) == (["a"], None)


def test_the_wait_page_says_when_a_step_is_slow_without_counting_seconds():
    # 13-14 Oct: a silent photo model held "Reading the photo" for 90 s with nothing moving;
    # 21 Oct, Kash: no running "12 s so far", only the slow step's line
    from herbtwin.web.progress import HEAD, SLOW_S

    for head in (HEAD, SPOT_HEAD):
        assert 'id="waited" hidden' in head and "s so far" not in head
        assert (
            f"Date.now()-(window.herbtwinAt||t)<{SLOW_S}e3)" in head
            and "Taking longer than usual" in head
        )
        assert "#next,.err" in head  # stops once the page ends
