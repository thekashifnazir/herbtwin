"""The gardener's test of the live site (21 Oct): say the light we measured, in plain words
and only when we have it, and say honestly who "the advisors" are."""

import html
import re
from datetime import datetime

from herbtwin.light import light_said
from herbtwin.schemas import LightReading
from herbtwin.stages.advise import PANEL_TEMPERATURES, advisors_said
from tests.test_web_answer_page import _full_plan, _render


def _reading(now="bright_shade", hour=14, minute=5):
    return LightReading(
        fraction=0.4, now=now, local_time=datetime(2026, 10, 15, hour, minute), lux=8000,
        sky_wm2=150, route="shutter",
    )  # fmt: skip


def test_light_is_said_as_a_moment_against_that_hours_sky():
    # against the actual sky, cloud and all: never "sun" or "bright" (review of this PR)
    said = light_said(_reading())
    assert (
        said
        == "Light at 14:05: part shade, about 40% of open-sky light (measured from your photo)."
    )
    full = light_said(_reading("direct_sun", 9, 30))
    assert full == "Light at 09:30: as bright as the open sky (measured from your photo)."
    deep = _reading("deep_shade")
    deep.fraction = 0.12
    assert light_said(deep).startswith("Light at 14:05: deep shade, about 12% of open-sky light")
    assert light_said(None) is None


def test_the_page_shows_the_light_only_when_we_measured_it(tmp_path):
    rec = _full_plan(tmp_path)
    rec.light = None
    assert 'class="note light-read"' not in _render(rec)
    rec.light = _reading()
    page = html.unescape(_render(rec))
    band = page.split('<div class="page-band">', 1)[1].split('<div class="answer-cols', 1)[0]
    assert '<p class="note light-read">Light at 14:05: part shade, about 40%' in band


def test_the_advisors_are_described_as_what_they_are():
    n = len(PANEL_TEMPERATURES)
    assert n == 3
    said = advisors_said(model="NVIDIA Nemotron 3 Super")
    # three answers from one model to the same question, never three experts
    assert said == (
        "Who advised: NVIDIA Nemotron 3 Super was asked the same question three times, each on"
        " its own, from the same read of your photo, weather and care facts. We call each answer"
        " an advisor: when they agree, we're surer."
    )
    assert advisors_said(model=None).startswith("Who advised: one model was asked the same")


def test_specialist_advisors_name_their_roles():
    # the slot for real specialist advisors (devpost-submission's test): names drop in
    said = advisors_said(roles=["soil and water", "pests and disease", "season and weather"])
    assert said == (
        "Who advised: three specialist advisors, for soil and water, pests and disease, and"
        " season and weather, each from the same read of your photo, weather and care facts."
        " When they agree, we're surer."
    )
    assert advisors_said(roles=["soil and water"]).startswith(
        "Who advised: one specialist advisor, for soil and water, each"
    )


def test_how_we_worked_it_out_starts_with_who_advised(tmp_path):
    rec = _full_plan(tmp_path)
    page = html.unescape(_render(rec, advised_by="NVIDIA Nemotron 3 Super"))
    details = page.split('<h2 id="details">How we worked it out</h2>', 1)[1]
    assert re.match(
        r"\s*<p class=\"advisors\">Who advised: NVIDIA Nemotron 3 Super was asked", details
    )
    rec.answer.advisor_roles = ["soil and water", "pests and disease", "season and weather"]
    assert "three specialist advisors, for soil and water" in html.unescape(_render(rec))


def test_an_answer_saved_before_advisor_roles_still_loads(tmp_path):
    from herbtwin.schemas import Answer

    old = _full_plan(tmp_path).answer.model_dump(mode="json")
    old.pop("advisor_roles")
    assert Answer.model_validate(old).advisor_roles == []
