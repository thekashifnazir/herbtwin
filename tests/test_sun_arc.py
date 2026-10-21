from herbtwin.schemas import SunHours
from herbtwin.sun_arc import BOTTOM, SCALE_H, TOP, _y, said, sun_arc

# clear-day hours on the 15th, low/mid/high, for a south-facing UK spot (shape, not data)
MIDS = [3.2, 5.0, 7.6, 10.4, 12.8, 13.9, 13.4, 11.4, 8.8, 6.1, 3.9, 2.7]
SUN = SunHours(
    months=[(m - 1.0, m, m + 1.0) for m in MIDS],
    june_class="sun",
    borderline=False,
    method="defaults",
)


def test_the_arc_draws_only_the_months_it_has_on_a_fixed_scale():
    arc = sun_arc(SUN, 10)
    assert len(arc.mid.split()) == 12  # one point per month, Jan to Dec
    assert len(arc.band.split()) == 24  # high there, low back: the range as a band
    ys = [float(p.split(",")[1]) for p in arc.mid.split()]
    assert ys.index(min(ys)) == 5  # June is highest
    xs = [float(p.split(",")[0]) for p in arc.mid.split()]
    assert xs == [12.5 + 25 * i for i in range(12)]  # each over its column of month letters
    assert arc.now == (float(arc.mid.split()[9].split(",")[0]), ys[9])  # October's own point
    assert arc.year == "Clear-day sun over the year: most in June, least in December."


def test_the_scale_is_fixed_and_holds_a_shetland_june():
    # 0 to 19 h whatever the spot, so shade looks like shade; a far-north 18 h June is drawn,
    # not flattened at a 16 h cap
    assert (_y(0), _y(SCALE_H)) == (BOTTOM, TOP)
    assert _y(SCALE_H / 2) == round((TOP + BOTTOM) / 2, 1)
    assert _y(18.0) < _y(16.0)


def test_the_caption_names_the_photo_month_and_the_next_in_hours():
    # after Greg's "Sunlight will increase 20% next month": hours a gardener can check, by
    # month name, and always "on a clear day" (these are not sunshine forecasts)
    assert said(SUN, 10) == (
        "On a clear day here: about 6 h of direct sun in October, about 4 h in November."
    )
    # December rolls over to January
    assert said(SUN, 12) == (
        "On a clear day here: about 3 h of direct sun in December, about 3 h in January."
    )
    shade = SUN.model_copy(update={"months": [(0.0, 0.2, 0.6)] * 11 + [(1.0, 2.0, 3.0)]})
    assert said(shade, 11) == (
        "On a clear day here: under 1 h of direct sun in November, about 2 h in December."
    )


def test_no_sun_estimate_draws_nothing():
    assert sun_arc(None, 10) is None and sun_arc(SUN, 13) is None
