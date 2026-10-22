"""22 Oct site walk (part B), three answer-page lines said wrong or twice:

1. Also do "Keep it apart" under "Remove it" (the plant is being binned) and under a rosemary
   beetle (it walks from plant to plant): filler. No cure keeps no such card; a pest that
   moves says which plants nearby to check, from our own outcome table.
2. The How sure fold listed a factor twice with opposite effects ("3 of 3 agree" under
   Helped, "needed a second try" under Lowered). One row per factor, its net effect; the
   retry is our workings, never on the page. The levels do not move.
3. "Photo check: rosemary beetle … Signs from rhs.org.uk" linked the RHS sage page. The
   signs link is only ever a page about that problem, or no link.
"""

from dataclasses import replace
from urllib.parse import urlsplit

import pytest

from herbtwin.adapters.mock import MockAdapter
from herbtwin.answer import NEIGHBOURS_CHECK, NEIGHBOURS_FALLBACK, _unsafe, also_eats
from herbtwin.confidence import CHIPS, _chips, assess
from herbtwin.schemas import Advice, Factor, ProblemSeen, about_problem
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.stages.problem import check_problem, signs
from tests.test_answer import BASIL, DOWNY_PANEL, build
from tests.test_confidence import BASE
from tests.test_web_answer_page import _full_plan, _render

SAGE_PAGE = "https://www.rhs.org.uk/herbs/sage/grow-your-own"
BEETLE_PAGE = "https://www.rhs.org.uk/biodiversity/rosemary-beetle"


def _treat(*actions: str) -> Panel:
    adv = Advice(actions=["treat_or_remove", *actions], primary="treat_or_remove", answer="x.")
    run = AdviceRun(adv, 0.0, False)
    return Panel((run,) * 3, (), "treat_or_remove", run, 3, 3)


def _seen(name: str) -> ProblemSeen:
    return ProblemSeen(name=name, looks_like="x", source=SAGE_PAGE)


def _on(plant_key: str, problem: str, actions: tuple[str, ...] = ("isolate",)):
    return build(
        panel=_treat(*actions), problem=_seen(problem), plant_key=plant_key, month=10,
        views=BASIL["views"],
    )  # fmt: skip


# --- 1. Also do ----------------------------------------------------------------------------


def test_no_cure_keeps_no_keep_it_apart_card():
    # r2: "Remove it. There is no cure for this." over "Also do: Keep it apart"
    a = build(panel=DOWNY_PANEL, **BASIL)
    assert a.headline == "Remove it. There is no cure for this."
    assert "isolate" not in [c.action for c in a.do]


def test_a_rosemary_beetle_names_the_herbs_nearby_it_also_eats():
    # r5: "Keep it apart" for a beetle that walks between plants. Our outcome table lists
    # rosemary beetle on sage, purple sage, rosemary and thyme: the rosemary's own name and
    # a kind of sage beside sage are left out
    a = _on("salvia rosmarinus", "rosemary beetle")
    assert [c.action for c in a.do].count("isolate") == 0
    card = next(c for c in a.do[1:] if c.action == "check_pests")
    assert card.because == "check the sage and thyme nearby: rosemary beetle feeds on them too."
    assert card.when == "this_week"
    # on sage, the others are rosemary and thyme
    assert also_eats("rosemary beetle", "salvia officinalis") == ["rosemary", "thyme"]


def test_a_moving_pest_with_no_other_plant_in_our_table_says_check_the_plants_nearby():
    # capsid bugs: our table lists them on sage and purple sage only, the same herb
    assert also_eats("capsid bugs", "salvia officinalis") == []
    a = _on("salvia officinalis", "capsid bugs")
    card = next(c for c in a.do[1:] if c.action == "check_pests")
    assert card.because == NEIGHBOURS_FALLBACK
    assert "isolate" not in [c.action for c in a.do]


def test_a_pest_that_stays_put_keeps_keep_it_apart():
    # aphids on a potted basil: moving the pot away is the RHS's own advice for them
    a = _on("ocimum basilicum", "aphids")
    assert "isolate" in [c.action for c in a.do]
    assert not any(c.action == "check_pests" for c in a.do[1:])


def test_a_moving_pest_with_a_check_card_already_says_it_once():
    a = _on("salvia rosmarinus", "rosemary beetle", ("isolate", "check_pests"))
    checks = [c for c in a.do if c.action == "check_pests"]
    assert len(checks) == 1 and "sage and thyme" in checks[0].because
    assert "isolate" not in [c.action for c in a.do]


@pytest.mark.parametrize("rest", [False, True])
def test_the_new_lines_pass_the_safety_check_for_their_card(rest):
    lines = [NEIGHBOURS_FALLBACK] + [
        NEIGHBOURS_CHECK.format(plants="sage and thyme", pest="x", feeds=f, them=t)
        for f, t in (("feeds", "them"), ("feed", "it"))
    ]
    for line in lines:
        for job in ("check_pests", "treat_or_remove"):
            assert not _unsafe(line, rest, job), (line, job)


# --- 2. How sure: one row per factor -------------------------------------------------------


def test_each_factor_is_one_row_with_its_net_effect():
    got = assess(replace(BASE, agree=3, repaired=True))
    names = [c.name for c in got.chips]
    assert len(names) == len(set(names)), names
    agreement = next(c for c in got.chips if c.name == "Agreement")
    assert (agreement.effect, agreement.why) == ("raises", ["3 of 3 agree"])
    # the second try is our own workings: it still weighs, but is never said on the page
    assert not any("second try" in w for c in got.chips for w in c.why)
    assert any(f.name == "repair" for f in got.factors)


def test_a_reason_the_other_way_is_not_listed_under_another_heading():
    # Season under Lowered and under No effect (r5); Season under Helped and Lowered (mint)
    for changes in ({}, {"action": "water", "soil_surface": "dry"}):
        got = assess(replace(BASE, **changes))
        assert [c.name for c in got.chips if c.name == "Season"] == ["Season"]
    mint = next(c for c in assess(BASE).chips if c.name == "Season")
    # the rule-of-thumb line lowered it: said in the same row, never under its own heading
    assert mint.effect == "raises" and mint.why == [
        "mentha: normal dieback is normal in October, but what is normal this month comes "
        "from a gardeners' rule of thumb"
    ]


def test_missing_says_only_what_is_missing():
    # "care facts verified" under Missing (site walk): the forecast is what is missing
    rows = [
        (Factor(name="plant_model", effect="missing", detail="no 2-week forecast"), 0.0),
        (Factor(name="care_facts", effect="raises", detail="care facts verified"), 0.1),
    ]
    assert [(c.effect, c.why) for c in _chips(rows) if c.name == "Choices compared"] == [
        ("missing", ["no 2-week forecast"])
    ]


def test_every_chip_is_said_once_on_the_page(tmp_path):
    rec = _full_plan(tmp_path)
    got = assess(replace(BASE, agree=3, repaired=True))
    rec.answer.chips, rec.answer.factors = got.chips, got.factors
    fold = _render(rec).split('<details class="why fold')[1].split("</details>")[0]
    for name in CHIPS:
        assert fold.count(f"<strong>{name}</strong>") <= 1, name
    assert "second try" not in fold


# the levels and scores on main before this change (22 Oct): only how the factors are
# listed changes, never how sure we are (the level is used everywhere and by the evals)
LEVELS = {
    "base": ({}, "fairly_sure", -0.089),
    "repaired": ({"repaired": True}, "fairly_sure", -0.082),
    "three_agree_repaired": ({"agree": 3, "repaired": True}, "fairly_sure", -0.008),
    "unsure_split": ({"advisor": "low", "agree": 1}, "not_sure", -0.433),
    "water_dry": ({"action": "water", "soil_surface": "dry"}, "sure", 0.291),
    "no_place": (
        {
            "norm": None,
            "season_missing": "no_location",
            "has_location": False,
            "weather_ok": False,
            "weather_missing": "no_location",
            "view": None,
            "model_missing": "no_weather",
        },
        "not_sure",
        -0.789,
    ),
    "rule_led": ({"advisor": "low", "agree": 0, "rule_led": True}, "not_sure", -0.433),
    "treat_three": (
        {"action": "treat_or_remove", "symptoms": ["grey fuzzy mould"], "agree": 3},
        "sure",
        0.615,
    ),
    "poor_photo": (
        {"photo_quality": "poor", "quality_note": "blurred", "species_conf": 0.3},
        "not_sure",
        -0.789,
    ),
}


@pytest.mark.parametrize("case", LEVELS)
def test_the_levels_do_not_move(case):
    changes, level, score = LEVELS[case]
    got = assess(replace(BASE, **changes))
    assert (got.level, got.score) == (level, score)


# --- 3. The signs link ---------------------------------------------------------------------


def test_a_page_about_another_plant_is_not_the_problems_page():
    assert not about_problem(SAGE_PAGE, "rosemary beetle")
    assert about_problem(BEETLE_PAGE, "rosemary beetle")
    assert about_problem("https://www.rhs.org.uk/disease/powdery-mildews", "powdery mildew")
    assert about_problem(
        "https://hort.extension.wisc.edu/articles/basil-downy-mildew-2/", "basil downy mildew"
    )
    # the host is not the page: "rhs" names no problem, and a bare site is no page about it
    assert not about_problem("https://www.rhs.org.uk", "rust")


def test_a_stored_wrong_page_is_dropped_and_the_page_shows_no_link(tmp_path):
    # r5 as stored: the sage page under a rosemary beetle
    seen = ProblemSeen(name="rosemary beetle", looks_like="beetles", source=SAGE_PAGE)
    assert seen.page == ""
    # decided when shown, not stored: a saved case keeps its source as it was
    again = ProblemSeen.model_validate_json(seen.model_dump_json())
    assert again.source == SAGE_PAGE and again.page == ""
    rec = _full_plan(tmp_path)
    rec.problem = seen
    page = _render(rec)
    assert SAGE_PAGE not in page
    assert "Photo check: rosemary beetle." in page and "Signs from" not in page


def test_the_right_page_still_links(tmp_path):
    rec = _full_plan(tmp_path)
    rec.problem = ProblemSeen(name="rosemary beetle", looks_like="beetles", source=BEETLE_PAGE)
    page = _render(rec)
    assert f'Signs from <a href="{BEETLE_PAGE}" rel="noopener noreferrer">rhs.org.uk</a>' in page


def test_the_photo_check_links_the_rosemary_beetle_page_not_the_sage_one():
    reply = '{"problem": "rosemary beetle", "seen": "striped beetles"}'
    got = check_problem(MockAdapter([reply]), b"x", "image/jpeg", "salvia rosmarinus", "rosemary")
    assert got is not None and got.source == BEETLE_PAGE


def test_every_problem_we_can_name_from_a_photo_links_its_own_page_or_none():
    for name, entry in signs().items():
        src = entry["source"]
        if entry["photo"] and about_problem(src, name):
            continue
        # a problem with no page of its own among its sources keeps none (whitefly), and
        # one never offered from a photo (root rot) is never shown
        assert not entry["photo"] or name == "whitefly", (name, src)
        assert urlsplit(src).scheme == "https"


# --- review of the branch: never hide a reason that lowered it ------------------------------


def test_a_minority_call_still_says_how_few_agree():
    # W2: advisor sure, 1 of 3 agree nets to Helped; "1 of 3 agree" is the doubt that matters
    got = assess(replace(BASE, advisor="high", agree=1))
    agreement = next(c for c in got.chips if c.name == "Agreement")
    assert agreement.effect == "raises"
    assert agreement.why == ["the advisor was sure, but only 1 of 3 agree"]


def _lowered(got) -> list[str]:
    """Every reason that did lower it (a negative weight), as the fold must say it."""
    from herbtwin.confidence import UNSAID, load_weights

    w = load_weights()["factors"]
    low = [
        f for f in got.factors if f.effect == "lowers" and w.get(f.name, {}).get("lowers", 0.0) < 0
    ]
    count = any(f.name == "agreement" and f.effect == "lowers" for f in low)
    # beside a count that lowered it, "the advisor was not sure" goes (_once, as before)
    return [
        f.detail
        for f in low
        if f.name not in UNSAID and not (count and f.detail.startswith("the advisor was"))
    ]


@pytest.mark.parametrize("case", LEVELS)
def test_every_reason_that_lowered_it_is_said_in_the_fold(case):
    got = assess(replace(BASE, **LEVELS[case][0]))
    fold = " ".join(w for c in got.chips for w in c.why)
    for detail in _lowered(got):
        assert detail in fold, (case, detail)


@pytest.mark.parametrize("case", LEVELS)
def test_mostly_names_only_a_reason_the_fold_says(case, tmp_path):
    # W1: on the mint fixture "Mostly: what is normal this month comes from a gardeners' rule
    # of thumb" while the fold showed Season under Helped without it
    from herbtwin.answer import doubt_reason

    got = assess(replace(BASE, **LEVELS[case][0]))
    rec = _full_plan(tmp_path)
    rec.answer.chips, rec.answer.factors = got.chips, got.factors
    fold = _render(rec).split('<details class="why fold')[1].split("</details>")[0]
    f = doubt_reason(got.factors)
    if f is not None:
        assert f.detail in fold.replace("&#39;", "'"), (case, f.detail)
    assert doubt_reason(assess(BASE).factors) is not None  # the case the review found


def test_the_wait_pages_more_on_link_is_only_the_problems_own_page():
    # N3: the wait page's chip read the signs file's source as it was
    from herbtwin.web import progress

    beetle = progress._problem_chip("Rosemary beetle")
    assert f'<a href="{BEETLE_PAGE}"' in beetle and "More on rhs.org.uk" in beetle
    # no page of its own among its sources (whitefly), or only another plant's (root rot)
    for name in ("Whitefly", "Root rot"):
        chip = progress._problem_chip(name)
        assert "Looks like:" in chip and "More on" not in chip, name


def test_the_neighbours_line_reads_right_for_a_plural_pest_and_never_says_unknown_kind():
    from herbtwin.answer import neighbours_check

    # N4: "capsid bugs feeds"; and "mint (unknown kind)" as a plant to check
    assert neighbours_check("capsid bugs", "salvia rosmarinus") == (
        "check the sage nearby: capsid bugs feed on it too."
    )
    assert neighbours_check("rosemary beetle", "salvia rosmarinus").endswith(
        "rosemary beetle feeds on them too."
    )
    # mint and "mint (unknown kind)" are one herb: named by its plain name
    assert also_eats("blue mint beetle", "origanum vulgare") == ["mint"]
    assert neighbours_check("blue mint beetle", "origanum vulgare") == (
        "check the mint nearby: blue mint beetle feeds on it too."
    )
