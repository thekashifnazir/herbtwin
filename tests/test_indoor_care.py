"""21 Oct, a gardener's test of the site: an indoor answer "doesn't have much info". Indoors
the outdoor season and the forecast don't apply, so the answer had little beyond the main
card. The indoor care table says what is normal on a windowsill or in a room this month, and
what to do about light, water, air, warmth and repotting, from RHS and extension pages."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.indoor_care import INDOOR_PATH, IndoorCare, indoor_care_for, load_indoor
from herbtwin.pipeline import Deps
from herbtwin.seasonal import plants as norm_plants
from herbtwin.tracing import TraceStore
from herbtwin.web.answer_text import plan_text
from herbtwin.web.app import create_app
from tests.test_web import ADV, OBS, _client, _first

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")

ROWS = json.loads(INDOOR_PATH.read_text())


def test_every_group_covers_each_month_once():
    groups: dict[str, list[int]] = {}
    for row in load_indoor():
        groups.setdefault(row.group, []).extend(row.months)
    assert "any indoor plant" in groups  # the fallback for a plant we have no group for
    for group, months in groups.items():
        assert sorted(months) == list(range(1, 13)), group


def test_each_plant_is_in_one_group_and_known_to_the_season_table():
    seen: dict[str, str] = {}
    for row in load_indoor():
        for plant in row.plants:
            assert seen.setdefault(plant, row.group) == row.group, plant
    # the lookup is by the species matcher's key, the same keys as the season table
    assert set(seen) <= set(norm_plants())
    for herb in ("ocimum basilicum", "petroselinum crispum", "salvia rosmarinus", "mentha"):
        assert herb in seen, herb
    for houseplant in ("spathiphyllum", "aloe vera", "phalaenopsis", "schlumbergera"):
        assert houseplant in seen, houseplant


def test_rows_are_short_cited_and_in_our_words():
    for row in load_indoor():
        where = f"{row.group} {row.months}"
        assert row.sources and all(s.startswith("https://") for s in row.sources), where
        assert 3 <= len(row.tips) <= 5, where
        assert len(row.normal.split()) <= 30, where
        for tip in row.tips:
            assert len(tip.split()) <= 22, (where, tip)
        # an Also-do card comes with its reason and what to expect, or not at all
        assert (row.also_do is None) == (row.because is None) == (row.if_you_do is None), where
        assert row.evidence_tier in ("B", "C")
    # never a feed in the rest months, never a repot outside spring
    for row in load_indoor():
        if row.also_do == "feed":
            assert set(row.months) <= set(range(3, 10)), row.group
        if row.also_do == "repot":
            assert set(row.months) <= {3, 4, 5}, row.group


def test_the_lookup_is_by_key_with_a_fallback():
    basil = indoor_care_for("ocimum basilicum", 10)
    assert basil is not None and "ocimum basilicum" in basil.plants and 10 in basil.months
    assert indoor_care_for("Ocimum Basilicum", 10) == basil  # any case
    for key in (None, "acer palmatum", "not a plant"):
        other = indoor_care_for(key, 1)
        assert other is not None and other.group == "any indoor plant", key
    # a copy: a caller editing it never changes later lookups
    basil.tips.append("x")
    assert "x" not in indoor_care_for("ocimum basilicum", 10).tips  # type: ignore[union-attr]


def test_winter_rows_say_less_water_and_keep_off_radiators():
    for key in ("ocimum basilicum", "spathiphyllum", "aloe vera"):
        jan = indoor_care_for(key, 1)
        assert jan is not None
        said = " ".join(jan.tips).lower()
        assert re.search(r"\bless\b|\bsparingly\b|\brarely\b|\bdry\b", said), key
        assert "radiator" in said, key


def _indoor_page(tmp_path, actions=("water",), setting="indoor"):
    adv = {
        **ADV,
        "actions": list(actions),
        "primary": "water",
        "answer": "The compost looks dry and the leaves are drooping. Water it.",
    }
    obs = {**OBS, "setting": setting, "container": "pot"}
    c = _client(tmp_path, [json.dumps(obs)], [json.dumps(adv)] * 9)
    rid = _first(c)
    return c.get(f"/answers/{rid}").text


def test_an_indoor_answer_says_what_is_normal_indoors_this_month(tmp_path):
    page = _indoor_page(tmp_path)
    oct_ = indoor_care_for("ocimum basilicum", 10)
    assert oct_ is not None
    section = page.split('<section class="indoor-now"', 1)[1].split("</section>", 1)[0]
    assert '<h2 id="indoor-now">Indoors in October</h2>' in section
    assert oct_.normal in section
    for tip in oct_.tips:
        assert tip in section, tip
    assert "From " in section and "rhs.org.uk" in section  # who says so, linked
    # beside the plan since 24 Oct (Kash: "moving the October over to the right"): in the
    # side column, after the questions, before How we worked it out; still in the rater text
    side = page.split('<div class="side">', 1)[1]
    assert (
        side.index('id="chat"') < side.index('class="indoor-now"') < side.index('class="details"')
    )
    assert "Indoors in October" in plan_text(page)


def test_an_indoor_answer_gets_the_months_also_do_card(tmp_path):
    oct_ = indoor_care_for("ocimum basilicum", 10)
    assert oct_ is not None and oct_.also_do is not None and oct_.because is not None
    page = _indoor_page(tmp_path)
    also = page.split('<section class="also"', 1)[1].split("</section>", 1)[0]
    assert oct_.because[:1].upper() + oct_.because[1:] in also
    assert oct_.if_you_do is not None and oct_.if_you_do in also
    assert "From gardening sources:" in also


def test_the_card_is_not_said_twice(tmp_path):
    oct_ = indoor_care_for("ocimum basilicum", 10)
    assert oct_ is not None and oct_.also_do is not None
    page = _indoor_page(tmp_path, actions=("water", oct_.also_do))
    also = page.split('<section class="also"', 1)[1].split("</section>", 1)[0]
    assert also.count('<div class="item">') == 1


def test_an_outdoor_answer_has_no_indoor_section(tmp_path):
    page = _indoor_page(tmp_path, setting="outdoor")
    assert '<section class="indoor-now"' not in page and "Indoors in October" not in page


def test_the_model_is_a_plain_pydantic_row():
    row = IndoorCare.model_validate(ROWS[0])
    assert row.months and row.plants is not None and Path(INDOOR_PATH).name == "indoor_care_uk.json"


JUNE_4 = datetime(2026, 6, 4, 9, tzinfo=UTC)
PEACE_LILY = {
    **OBS,
    "species": [{"name": "Spathiphyllum", "common_name": "peace lily", "confidence": 0.9}],
    "setting": "indoor",
    "container": "pot",
    "symptoms": [],
    "water_stress": 0,
}


def _june_page(tmp_path, primary="water", place: dict[str, str] | None = None, obs=None, at=None):
    """A June peace lily indoors: its row's Also-do card is a feed."""
    adv = {**ADV, "actions": [primary], "primary": primary, "answer": "It looks fine. Water it."}
    tmp_path.mkdir(parents=True, exist_ok=True)
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(obs or PEACE_LILY)]),
        advise_adapter=MockAdapter([json.dumps(adv)] * 9),
        settings=load_settings(place if place is not None else {}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    c = TestClient(create_app(deps, clock=lambda: at or JUNE_4))
    return c.get(f"/answers/{_first(c)}").text


def test_a_thriving_houseplant_gets_the_months_feed_card(tmp_path):
    june = indoor_care_for("spathiphyllum", 6)
    assert june is not None and june.also_do == "feed" and june.because is not None
    page = _june_page(tmp_path)
    also = page.split('<section class="also"', 1)[1].split("</section>", 1)[0]
    assert "<h3>Feed it</h3>" in also and june.because[1:] in also
    assert "Indoors in June" in page


def test_never_a_feed_or_repot_under_a_plant_held_dry_or_checked(tmp_path):
    # review: "Hold off watering" then "Feed it" argued with itself
    for i, primary in enumerate(("dont_water", "treat_or_remove", "isolate")):
        page = _june_page(tmp_path / str(i), primary=primary)
        assert "<h3>Feed it</h3>" not in page, primary
        assert "Indoors in June" in page, primary  # the month's tips still show


def test_no_place_still_gets_the_section_and_abroad_does_not(tmp_path):
    assert "Indoors in June" in _june_page(tmp_path / "none")
    paris = {"HERBTWIN_HOME_LAT": "48.86", "HERBTWIN_HOME_LON": "2.35"}
    page = _june_page(tmp_path / "paris", place=paris)
    assert '<section class="indoor-now"' not in page and "<h3>Feed it</h3>" not in page


def test_the_card_keeps_to_the_plants_own_season_for_the_job(tmp_path):
    """#340 review: an indoor basil in April got "Feed it" from the soft-herb row while
    basil's own feed row says June to September; #301's off-season filter applies here too."""
    april = indoor_care_for("ocimum basilicum", 4)
    assert april is not None and april.also_do == "feed"
    basil = {**PEACE_LILY, "species": OBS["species"]}
    page = _june_page(tmp_path, obs=basil, at=datetime(2026, 4, 4, 9, tzinfo=UTC))
    assert "Indoors in April" in page and "<h3>Feed it</h3>" not in page


def test_the_rater_text_carries_the_indoor_section(tmp_path):
    from herbtwin.web.answer_text import plan_text

    text = plan_text(_june_page(tmp_path))
    assert "Indoors in June" in text and "Feed it" in text
