"""23 Oct, Kash on a phone walk of the live site: "Why is tips for the month on for indoor but
not outdoor?" An indoor answer gets "Indoors in <Month>" (#340); an outdoor one got nothing
like it, even with no place. "Outdoors in <Month>" says what is normal for this plant outdoors
in the UK this month (the season table's own signs) and 2 or 3 care points from our outdoor
table, RHS-sourced, in our own words."""

import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.answer import SAME_JOB, _no_cut_for_growth, _unsafe, tip_job, winter_rest
from herbtwin.config import load_settings
from herbtwin.consequences import consequence_for
from herbtwin.outcomes import load_outcomes
from herbtwin.outdoor_care import OUTDOOR_PATH, load_outdoor, outdoor_care_for, outdoor_now
from herbtwin.pipeline import Deps
from herbtwin.schemas import Advice
from herbtwin.seasonal import PROBLEM_PAPERS, load_norms, normal_for
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.tracing import TraceStore
from herbtwin.web.answer_text import plan_text
from herbtwin.web.app import create_app
from tests.test_answer import ASSESS, DOWNY_PANEL, PANEL, build
from tests.test_web import ADV, OBS, _first

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")

OCT_4 = datetime(2026, 10, 4, 9, tzinfo=UTC)
LONDON = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
PARIS = {"HERBTWIN_HOME_LAT": "48.86", "HERBTWIN_HOME_LON": "2.35"}
OUTDOOR_PLANTS = {n.plant for n in load_norms() if not n.indoor}
# an outcome row that says "not now" for its months: a job tip must never fall in one
NOT_NOW = re.compile(r"^(?:Light picking only|Best avoided|Not now|Little benefit|Skip|Not advised|"
                     r"Not needed|No pruning|Rarely needed|Usually unnecessary)")  # fmt: skip
PARSLEY = [{"name": "Petroselinum crispum", "common_name": "parsley", "confidence": 0.9}]
OUTCOME_ROWS = [r for r in load_outcomes() if r.problem is None]


# --- the table -----------------------------------------------------------------------------


def test_each_plant_and_month_has_at_most_one_row_and_is_an_outdoor_season_plant():
    seen: dict[tuple[str, int], str] = {}
    for row in load_outdoor():
        for plant in row.plants:
            assert plant in OUTDOOR_PLANTS, plant  # the season table's keys, outdoor rows
            for month in row.months:
                assert (plant, month) not in seen, (plant, month)
                seen[(plant, month)] = row.group
    for herb in ("ocimum basilicum", "petroselinum crispum", "salvia rosmarinus", "mentha"):
        assert (herb, 10) in seen, herb


def test_rows_are_short_cited_and_in_our_words():
    for row in load_outdoor():
        where = f"{row.group} {row.months}"
        # 2 or 3 points in a pot and in a bed (pot_tips and bed_tips are one or the other)
        assert 2 <= len(row.tips) + len(row.pot_tips) <= 3, where
        assert 2 <= len(row.tips) + len(row.bed_tips) <= 3, where
        assert row.sources and all(s.startswith("https://www.rhs.org.uk/") for s in row.sources)
        assert row.evidence_tier == "C", where
        for tip in row.tips + row.pot_tips + row.bed_tips:
            assert tip_job(tip) is not None or tip.split(":")[0] in ("Picking", "Sowing"), tip
            assert re.fullmatch(r"[A-Z][a-z ]+: [^\n]+\.", tip), (where, tip)  # "Water: …."
            assert len(tip.split()) <= 18, (where, tip)
        for tip in row.tips + row.bed_tips:  # said in a bed, where there is no pot
            assert not re.search(r"\bpots?\b", tip), (where, tip)
    assert OUTDOOR_PATH.name == "outdoor_care_uk.json"


def test_every_point_passes_the_safety_filter_for_its_plant_and_month():
    # our own fixed words, never the model's: still, no pest product, no home spray, and no
    # cut on a resting herb (answer._unsafe, #379/#386)
    for row in load_outdoor():
        for plant in row.plants:
            for month in row.months:
                rest = winter_rest(plant, month)
                for tip in row.tips + row.pot_tips + row.bed_tips:
                    assert not _unsafe(tip, rest), (plant, month, tip)
                    # and a resting herb is never cut for growth
                    assert not rest or _no_cut_for_growth(tip) == tip, (plant, month, tip)
                now = outdoor_now(plant, month)
                if now is not None and now.normal:
                    assert not _unsafe(now.normal, rest), (plant, month, now.normal)


def _job_fits(job: str, plant: str, month: int, held: bool) -> bool:
    """A tip that does the job (held=False) needs no "not now" row of the plant's for that
    job and month, and no off-season flag; one that holds it off ("Pruning: none now")
    needs no row saying to do it then."""
    rows = [r for r in OUTCOME_ROWS if r.plant == plant and r.action == job and month in r.months]
    if held:
        return all(NOT_NOW.search(r.if_you_do) for r in rows)
    c = consequence_for(job, plant_key=plant, month=month, answer="", views={})
    return not c.off_season and not any(NOT_NOW.search(r.if_you_do) for r in rows)


def test_a_job_tip_is_only_given_in_that_plants_own_months_for_the_job():
    # #301's rule for the cards, kept here too: never "Trimming: a light trim now" in a month
    # the outcome table says "Light picking only", nor "Pruning: none now" in one it says to
    # prune. Water and shelter have no months of their own
    for row in load_outdoor():
        for tip in row.tips + row.pot_tips + row.bed_tips:
            job = tip_job(tip)
            if job not in ("prune", "feed", "repot"):
                continue
            held = re.search(r"\bnone\b", tip) is not None
            for plant in row.plants:
                for month in row.months:
                    assert _job_fits(job, plant, month, held), (plant, month, tip)


def test_the_months_check_has_teeth():
    # the review found the first version passed whatever the months: rosemary's April row
    # says light picking only, oregano's winter repot is best avoided, mint's November cut is due
    assert not _job_fits("prune", "salvia rosmarinus", 4, held=False)
    assert not _job_fits("repot", "origanum vulgare", 12, held=False)
    assert not _job_fits("prune", "mentha", 11, held=True)
    assert _job_fits("prune", "salvia rosmarinus", 5, held=False)


# --- the card's content ---------------------------------------------------------------------


def test_october_basil_says_what_is_normal_and_the_months_points():
    now = outdoor_now("ocimum basilicum", 10)
    row = outdoor_care_for("ocimum basilicum", 10)
    assert now is not None and row is not None and now.month == 10
    # the season table's own signs, shortened as Keep an eye on shortens them
    assert now.normal == (
        "Normal now: leaves blackened and limp the morning after a cold night; woody stems "
        "with dry flower spikes."
    )
    assert now.tips == row.tips + row.pot_tips and 2 <= len(now.tips) <= 3
    assert "https://www.rhs.org.uk/herbs/basil/grow-your-own" in now.sources
    # the season's sources, never the disease papers behind its problem signs
    assert not set(now.sources) & PROBLEM_PAPERS
    assert len(now.sources) == len(set(now.sources))


def test_no_season_data_or_no_row_means_no_card():
    assert outdoor_now("not a plant", 10) is None
    assert outdoor_now(None, 10) is None
    assert outdoor_now("acer palmatum", 10) is None  # a season row, but no care row of ours
    assert outdoor_now("ocimum basilicum", 1) is None  # no basil outdoors in January
    assert outdoor_now("spathiphyllum", 10) is None  # a houseplant's season is indoors


def test_a_bed_gets_no_pot_points_and_says_soil():
    # judge walk of a border rosemary: a bed has soil, not compost, and no pot to raise
    row = outdoor_care_for("salvia rosmarinus", 3)
    assert row is not None and row.pot_tips
    pot, bed = outdoor_now("salvia rosmarinus", 3), outdoor_now("salvia rosmarinus", 3, "ground")
    assert pot is not None and bed is not None
    assert pot.tips == row.tips + row.pot_tips
    assert len(bed.tips) == len(row.tips) + len(row.bed_tips)
    assert not any(re.search(r"\bpots?\b|\bcompost\b", t) for t in bed.tips), bed.tips
    assert any("soil" in t for t in bed.tips)
    # nor a season sign about a pot: "a bare pot of compost" is no sign for a bed
    jan = outdoor_now("mentha spicata", 1, "ground")
    assert jan is not None and "pot" not in jan.normal


def test_a_pot_in_summer_is_checked_often_and_a_bed_only_in_long_dry_spells():
    # review: "only in long dry spells" is wrong for a pot; the RHS thyme page says a pot in
    # hot, dry weather needs water
    pot = outdoor_now("thymus vulgaris", 7, "pot")
    bed = outdoor_now("thymus vulgaris", 7, "ground")
    assert pot is not None and bed is not None
    assert any("check every few days" in t for t in pot.tips)
    assert not any("long dry spells" in t for t in pot.tips)
    assert any("long dry spells" in t for t in bed.tips)


def test_the_points_fit_the_plants_stage():
    # review: "dying after seeding" over "snip off flower stems"; a second-year parsley is
    # flowering and dying in summer, so no flower snipping for it either
    for key, month in (("coriandrum sativum", 9), ("petroselinum crispum", 7)):
        now = outdoor_now(key, month)
        assert now is not None and not any(t.startswith("Flowers:") for t in now.tips), key
    assert outdoor_now("anethum graveolens", 9) is None  # dill is done by September
    # nor "pick often" for a die-back herb in September, when it starts to rest
    sept = outdoor_now("mentha spicata", 9)
    assert sept is not None and not any("pick often" in t for t in sept.tips)
    # cold nights harm basil; the card no longer claims a number of its own
    oct_ = outdoor_now("ocimum basilicum", 10)
    assert oct_ is not None and not any("10 C" in t for t in oct_.tips)


def test_a_copy_each_time():
    now = outdoor_now("petroselinum crispum", 10)
    assert now is not None
    now.tips.append("x")
    assert "x" not in outdoor_now("petroselinum crispum", 10).tips  # type: ignore[union-attr]


# --- build_answer: which answers carry it ----------------------------------------------------

PARSLEY_OCT = outdoor_now("petroselinum crispum", 10)


def test_an_outdoor_answer_carries_the_card_and_others_do_not():
    assert PARSLEY_OCT is not None
    a = build(panel=PANEL, setting="outdoor", outdoor=PARSLEY_OCT)
    assert a.outdoor == PARSLEY_OCT
    # the read could not tell: "Outdoors in October" would claim what we don't know, and a
    # windowsill herb would be told about cloches and pot feet
    for setting in ("indoor", "unknown"):
        assert build(panel=PANEL, setting=setting, outdoor=PARSLEY_OCT).outdoor is None


def _panel(primary: str, answer: str):
    adv = Advice(actions=[primary], primary=primary, answer=answer, confidence="high")
    run = AdviceRun(adv, 0.0, False)
    return Panel((run,) * 3, (), primary, run, 3, 3)


def _outdoors(key: str, month: int, primary: str, answer: str, container: str = "pot", **kw):
    return build(panel=_panel(primary, answer), plant_key=key, month=month,
                 norm=normal_for(key, month), setting="outdoor", container=container,
                 outdoor=outdoor_now(key, month, container), **kw)  # fmt: skip


@pytest.mark.parametrize(
    ("key", "month", "primary", "answer", "container", "gone"),
    [
        # review of this PR: "Give it a light tidy." over "Pruning: none now"
        ("salvia rosmarinus", 10, "prune", "Trim off the dead brown tips.", "pot", "Pruning:"),
        ("laurus nobilis", 11, "prune", "Cut out the frost-browned shoots.", "pot", "Pruning:"),
        ("salvia rosmarinus", 3, "prune", "Cut out the winter-killed tips.", "ground", "Pruning:"),
        # "Water it." over "Water: only in long dry spells"
        ("thymus vulgaris", 7, "water", "The compost is bone dry. Water it.", "pot", "Water:"),
        ("mentha", 11, "prune", "Cut the dead stems down.", "pot", "Old stems:"),
    ],
)
def test_a_point_never_argues_with_the_answers_own_cards(
    key, month, primary, answer, container, gone
):
    a = _outdoors(key, month, primary, answer, container)
    jobs = {c.action for c in a.do} | ({a.dont.action} if a.dont else set())
    if a.outdoor is not None:
        assert not any(t.startswith(gone) for t in a.outdoor.tips), a.outdoor.tips
        for t in a.outdoor.tips:
            job = tip_job(t)
            assert job is None or job not in {SAME_JOB.get(j, j) for j in jobs}, (t, jobs)
    # the card's other points stay, when there are any
    full = outdoor_now(key, month, container)
    assert full is not None and any(t.startswith(gone) for t in full.tips)


def test_with_every_point_taken_there_is_no_card():
    # a bed rosemary in March told to cut it back and not to water: both its points are
    # decided above, and a card of signs alone says nothing to do
    a = _outdoors("salvia rosmarinus", 3, "prune", "Cut out the winter-killed tips.", "ground")
    assert a.dont is not None and a.outdoor is None


def test_no_card_under_a_cold_protection_lead():
    # review: "Bring it indoors to a bright windowsill." over "pick what you want now"
    for container in ("pot", "ground"):
        a = _outdoors("ocimum basilicum", 10, "shelter", "Cold nights are coming. Bring it in.",
                      container, tender=True)  # fmt: skip
        assert a.do[0].action == "shelter" and a.outdoor is None, container


def test_no_card_for_seedlings():
    # seedlings are never cut ("pinch out shoot tips"), and the season's signs are for a
    # grown plant
    for key, month in (("ocimum basilicum", 7), ("thymus vulgaris", 4), ("salvia officinalis", 5)):
        a = _outdoors(key, month, "water", "The compost is dry. Water it.", seedlings=True)
        assert a.no_cut_growth and a.outdoor is None, key
        grown = _outdoors(key, month, "leave_normal", "It looks fine. Leave it.")
        assert grown.outdoor is not None, key


def test_no_card_on_a_no_cure_answer_or_a_rough_read():
    # the plant is bagged and binned: next month's care is no use to it
    a = build(panel=DOWNY_PANEL, plant_key="ocimum basilicum", setting="outdoor",
              outdoor=outdoor_now("ocimum basilicum", 10))  # fmt: skip
    assert a.headline == "Remove it. There is no cure for this." and a.outdoor is None
    # a blurred photo names the plant only as a guess: no care for that guess
    rough = replace(ASSESS, photo_issue="blurry")
    a = build(panel=PANEL, assessment=rough, setting="outdoor", outdoor=PARSLEY_OCT)
    assert a.outdoor is None


# --- the page ----------------------------------------------------------------------------------


def _page(tmp_path, setting="outdoor", place=LONDON, obs=None, actions=("leave_normal",)):
    # leave it: no card of the answer's own takes one of the month's points
    adv = {**ADV, "actions": list(actions), "primary": actions[0],
           "answer": "It looks fine for the time of year. Leave it."}  # fmt: skip
    # parsley: an October basil outdoors is led by "Bring it indoors", which takes no card
    obs = obs or {**OBS, "setting": setting, "container": "pot", "species": PARSLEY}
    tmp_path.mkdir(parents=True, exist_ok=True)
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(obs)]),
        advise_adapter=MockAdapter([json.dumps(adv)] * 9),
        settings=load_settings(place),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    c = TestClient(create_app(deps, clock=lambda: OCT_4))
    return c.get(f"/answers/{_first(c)}").text


def _section(page: str) -> str:
    return page.split('<section class="outdoor-now"', 1)[1].split("</section>", 1)[0]


def test_an_outdoor_parsley_in_october_gets_outdoors_in_october(tmp_path):
    page = _page(tmp_path)
    now = outdoor_now("petroselinum crispum", 10, "pot")
    assert now is not None
    section = _section(page)
    assert '<h2 id="outdoor-now">Outdoors in October</h2>' in section
    assert now.normal in section
    assert section.count("<li>") == len(now.tips)
    for tip in now.tips:
        assert tip in section, tip
    # who says so, linked, as the indoor card does
    assert '<p class="note">From <a href="https://www.rhs.org.uk/' in section
    assert '<section class="indoor-now"' not in page
    # after the plan's own cards, before What next
    assert page.index('class="outdoor-now"') < page.index('class="next-step')


def test_no_place_still_gets_the_card_and_abroad_does_not(tmp_path):
    assert "Outdoors in October" in _page(tmp_path / "none", place={})
    page = _page(tmp_path / "paris", place=PARIS)
    assert '<section class="outdoor-now"' not in page and "Outdoors in October" not in page


def test_an_indoor_answer_keeps_its_indoor_card_and_gets_no_outdoor_one(tmp_path):
    page = _page(tmp_path, setting="indoor")
    assert "Indoors in October" in page
    assert '<section class="outdoor-now"' not in page and "Outdoors in October" not in page


def test_an_unknown_setting_gets_neither_card(tmp_path):
    page = _page(tmp_path, setting="unknown")
    assert "Outdoors in October" not in page and "Indoors in October" not in page


def test_a_plant_with_no_season_data_gets_no_card(tmp_path):
    fern = {**OBS, "setting": "outdoor", "container": "ground", "symptoms": [],
            "species": [{"name": "Acer palmatum", "common_name": "Japanese maple",
                         "confidence": 0.9}]}  # fmt: skip
    page = _page(tmp_path, obs=fern)
    assert '<section class="outdoor-now"' not in page


def test_the_rater_text_carries_the_outdoor_card(tmp_path):
    # advice, so rated, as the indoor card is (#340)
    text = plan_text(_page(tmp_path))
    now = outdoor_now("petroselinum crispum", 10, "pot")
    assert now is not None
    assert "Outdoors in October" in text and now.normal in text
    for tip in now.tips:
        assert tip in text, tip


def test_the_card_wears_the_indoor_cards_style():
    # one card style for the month, indoors or out: the same rules, never a copy of them
    css = (Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer.css").read_text()
    for part in ("", " h2", " ul", " li + li", " > :last-child"):
        assert f".answer-page :is(.indoor-now, .outdoor-now){part} {{" in css, part
    assert ".answer-page .indoor-now" not in css
