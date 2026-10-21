"""The worked case (spot spec section 6, S3): one tap plus defaults against the full solve
of the test garden (ref section 6). The taps are what a person would record: the facing
from the solve (garden axis 191 degrees true; pot-row wall facing 101) and the solve's own
horizon elevation in that direction. Generic public point: Cambridge University Botanic
Garden (not the garden).

Finding (plan S3): one tap reproduces the solve within 1.5 h at 8 of 12 table cells. The
strip bed's March (the east fence) and the corner pot (a fence right beside it) are beyond
one tap; there the range still holds the solve's class, so the list says "borderline"
rather than a wrong class."""

from datetime import date

import pytest

from herbtwin.schemas import Aspect
from herbtwin.sun import class_of, day_hours, horizon, sun_hours, sun_path

# Cambridge University Botanic Garden, a public point. Day length depends on latitude:
# Kew Gardens, further south, gives the corner pot a June low of 6.0 h ("sun") against
# the solve's 5.5 h ("part_shade"), so this test keeps a point further north.
POINT = (52.1934, 0.1275)
DAYS = (date(2026, 3, 21), date(2026, 6, 21), date(2026, 12, 21))  # the solve's dates
SPOTS = {  # name: (heading, pitch, wall behind), solve's (Mar/Sep, Jun, Dec) hours
    "strip bed": ((191, 30, True), (3.6, 9.0, 0.4)),
    "herb trough": ((191, 29, False), (7.0, 11.0, 0.8)),
    "pot row": ((101, 13, True), (6.0, 8.0, 0.8)),
    "corner pot": ((226, 30, True), (1.4, 5.5, 0.0)),
}
WITHIN = {  # table cells one tap reproduces within 1.5 h
    ("strip bed", 1),
    ("strip bed", 2),
    ("herb trough", 0),
    ("herb trough", 1),
    ("herb trough", 2),
    ("pot row", 0),
    ("pot row", 2),
    ("corner pot", 2),
}


def _hours(tap):
    profile = horizon(*tap)
    return [day_hours(sun_path(*POINT, d), profile) for d in DAYS]


@pytest.mark.parametrize(("spot", "i"), sorted(WITHIN))
def test_one_tap_reproduces_the_solve_within_1_5_hours(spot, i):
    tap, solved = SPOTS[spot]
    assert _hours(tap)[i] == pytest.approx(solved[i], abs=1.5)


ORDER = ("shade", "part_shade", "sun")


@pytest.mark.parametrize("spot", SPOTS)
def test_the_june_range_always_holds_the_solved_class(spot):
    (heading, pitch, wall), solved = SPOTS[spot]
    s = sun_hours(*POINT, Aspect(heading_deg=heading, pitch_deg=pitch, source="compass"), wall)
    low, _, high = s.months[5]
    rank = ORDER.index
    assert rank(class_of(low)) <= rank(class_of(solved[1])) <= rank(class_of(high))


def test_the_corner_pot_is_borderline_not_wrong():
    s = sun_hours(*POINT, Aspect(heading_deg=226, pitch_deg=30, source="compass"), True)
    assert s.borderline and class_of(s.months[5][0]) == "part_shade"
