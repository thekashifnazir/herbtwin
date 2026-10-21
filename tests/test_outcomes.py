import json
import re
from collections import defaultdict

import pytest
from pydantic import ValidationError

from herbtwin.outcomes import ActionOutcome, load_outcomes, outcome_for, problems_for
from herbtwin.seasonal import plants


def _row(**over):
    base = {
        "plant": "mentha spicata",
        "action": "treat_or_remove",
        "problem": "mint rust",
        "problem_aliases": ["rust"],
        "months": [5, 6],
        "if_you_do": "Removing infected shoots slows the spread.",
        "if_you_dont": None,
        "caution": None,
        "evidence_tier": "C",
        "sources": ["https://www.rhs.org.uk/disease/mint-rust"],
    }
    return {**base, **over}


# --- the table ---------------------------------------------------------------------


def test_the_table_loads_and_every_row_validates():
    rows = load_outcomes()
    assert len(rows) > 100
    assert all(isinstance(r, ActionOutcome) for r in rows)


def test_every_plant_key_is_a_seasonal_norms_plant():
    keys = set(plants())
    for r in load_outcomes():
        assert r.plant in keys, r.plant


# Plant and action pairs with no row because no source states the outcome (see
# docs/reference/action-outcomes.md, Gaps). Annuals are sown afresh, not repotted.
KNOWN_GAPS = {
    ("allium tuberosum", "feed"),
    ("aloe vera", "prune"),
    ("anethum graveolens", "feed"),
    ("anethum graveolens", "repot"),
    ("coriandrum sativum", "feed"),
    ("coriandrum sativum", "repot"),
    ("melissa officinalis", "feed"),
    ("ocimum basilicum", "repot"),
    ("petroselinum crispum", "repot"),
    ("rosa", "repot"),
    ("thymus vulgaris", "feed"),
    ("zamioculcas zamiifolia", "repot"),
}


def test_every_plant_has_each_action_except_the_documented_gaps():
    by_plant = defaultdict(set)
    for r in load_outcomes():
        by_plant[r.plant].add(r.action)
    missing = {
        (plant, action)
        for plant in plants()
        for action in ("prune", "feed", "repot", "treat_or_remove")
        if action not in by_plant[plant]
    }
    assert missing == KNOWN_GAPS


def test_every_row_cites_a_url_and_holds_in_real_months():
    for r in load_outcomes():
        assert r.sources and all(s.startswith("https://") for s in r.sources), r
        assert r.months and all(1 <= m <= 12 for m in r.months), r


def test_treat_rows_name_a_problem_and_other_rows_do_not():
    for r in load_outcomes():
        if r.action == "treat_or_remove":
            assert r.problem, r
        else:
            assert r.problem is None and not r.problem_aliases, r


def test_a_lookup_can_never_have_two_answers():
    # Two rows for one plant, action and problem name in the same month would make the
    # answer depend on file order.
    seen: dict[tuple, set[int]] = defaultdict(set)
    for r in load_outcomes():
        names = {r.problem, *r.problem_aliases} if r.problem else {None}
        for name in names:
            key = (r.plant, r.action, name)
            assert not seen[key] & set(r.months), key
            seen[key] |= set(r.months)


def test_an_alias_names_one_problem_per_plant():
    owner: dict[tuple[str, str], str] = {}
    for r in load_outcomes():
        if r.problem:
            for name in {r.problem, *r.problem_aliases}:
                assert owner.setdefault((r.plant, name), r.problem) == r.problem, (r.plant, name)


def test_each_plant_has_at_least_two_named_problems():
    for plant in plants():
        assert len(problems_for(plant)) >= 2, plant


# --- the model rejects what the contract forbids --------------------------------------


def test_a_treat_row_without_a_problem_is_rejected():
    with pytest.raises(ValidationError):
        ActionOutcome.model_validate(_row(problem=None, problem_aliases=[]))


@pytest.mark.parametrize("action", ["prune", "feed", "repot"])
def test_a_prune_feed_or_repot_row_with_a_problem_is_rejected(action):
    with pytest.raises(ValidationError):
        ActionOutcome.model_validate(_row(action=action))


@pytest.mark.parametrize(
    "over",
    [
        {"sources": []},
        {"sources": ["docs/reference/herb-care-packs.md"]},
        {"months": []},
        {"months": [0]},
        {"months": [13]},
        {"months": [5, 5]},
        {"if_you_do": " ".join(["word"] * 31)},
        {"if_you_dont": " ".join(["word"] * 31)},
        {"if_you_do": "  "},
        {"problem": "Mint Rust"},
        {"action": "water"},
        {"evidence_tier": "E"},
    ],
)
def test_a_row_breaking_the_contract_is_rejected(over):
    with pytest.raises(ValidationError):
        ActionOutcome.model_validate(_row(**over))


def test_the_loader_rejects_a_bad_file(tmp_path):
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps([_row(problem=None, problem_aliases=[])]))
    with pytest.raises(ValidationError):
        load_outcomes(path)


# --- outcome_for ----------------------------------------------------------------------


def test_finds_by_scientific_or_common_name_in_any_case():
    found = outcome_for("Mentha spicata", "treat_or_remove", 6, "mint rust")
    assert found is not None and found.problem == "mint rust"
    assert outcome_for("  SPEARMINT ", "treat_or_remove", 6, "Mint Rust") == found
    assert outcome_for("mint", "treat_or_remove", 6, "rust") == found


def test_rust_means_the_rust_of_that_plant():
    assert outcome_for("mint", "treat_or_remove", 6, "rust").problem == "mint rust"
    assert outcome_for("rose", "treat_or_remove", 5, "rust").problem == "rose rust"
    assert outcome_for("chives", "treat_or_remove", 8, "rust").problem == "leek rust"


def test_problem_must_match_a_whole_name_not_part_of_one():
    assert outcome_for("mint", "treat_or_remove", 6, "mint") is None
    assert outcome_for("mint", "treat_or_remove", 6, "mint rust disease") is None


def test_unknown_problem_returns_none_not_the_closest_row():
    assert outcome_for("mint", "treat_or_remove", 6, "spider mites") is None
    assert outcome_for("mint", "treat_or_remove", 6, "triffid blight") is None


def test_treat_without_a_problem_returns_none():
    assert outcome_for("mint", "treat_or_remove", 6) is None
    assert outcome_for("mint", "treat_or_remove", 6, "  ") is None


def test_a_month_no_row_covers_returns_none():
    # Basil is a summer annual outdoors in the UK: no feed row in January.
    assert outcome_for("basil", "feed", 1) is None
    assert outcome_for("mint", "prune", 13) is None


def test_unknown_plant_or_action_returns_none():
    assert outcome_for("triffid", "prune", 3) is None
    assert outcome_for("mint", "water", 6) is None


# Harvesting is not pruning: a "prune" lookup outside the source's pruning window must not
# read as "cutting is fine now". Those months say light picking only and name the window.
# "any time from late autumn until spring" names a window, so it is allowed.
ANY_TIME = re.compile(r"any time(?! from)|all year|whenever|as needed", re.IGNORECASE)


@pytest.mark.parametrize(
    ("plant", "month"),
    [("bay", 10), ("sage", 10), ("purple sage", 1), ("rosemary", 10), ("thyme", 11)],
)
def test_pruning_a_woody_herb_out_of_season_says_light_picking_only(plant, month):
    row = outcome_for(plant, "prune", month)
    assert row is not None
    assert row.if_you_do.startswith("Light picking only"), row.if_you_do
    assert "spring" in row.if_you_do or "flowers fade" in row.if_you_do


def test_no_prune_row_says_cutting_is_fine_any_time_without_the_light_picking_limit():
    for r in load_outcomes():
        if r.action == "prune" and ANY_TIME.search(r.if_you_do):
            assert r.if_you_do.startswith("Light picking only"), (r.plant, r.months)


def test_winter_spider_mite_rows_name_the_predator_that_survives_winter():
    # RHS: Amblyseius is "more likely to survive winter in glasshouse than Phytoseiulus".
    for r in load_outcomes():
        if r.problem == "spider mites" and set(r.months) & {12, 1}:
            if r.months != list(range(1, 13)):
                assert "Amblyseius" in r.if_you_do, (r.plant, r.months)


def test_problem_is_ignored_for_prune_feed_and_repot():
    assert outcome_for("rosemary", "feed", 5, "aphids") == outcome_for("rosemary", "feed", 5)


def test_spider_mites_match_by_alias_on_a_plant_that_has_them():
    plant = next(r.plant for r in load_outcomes() if r.problem == "spider mites")
    row = next(r for r in load_outcomes() if r.plant == plant and r.problem == "spider mites")
    month = row.months[0]
    assert outcome_for(plant, "treat_or_remove", month, "Red Spider Mite") == row


def test_an_unnamed_mint_has_its_own_rows():
    found = outcome_for("Mentha sp.", "prune", 7)
    assert found is not None and found.plant == "mentha"


def test_editing_a_returned_outcome_does_not_change_the_table():
    outcome_for("mint", "treat_or_remove", 6, "mint rust").sources.append("scribble")
    assert "scribble" not in outcome_for("mint", "treat_or_remove", 6, "mint rust").sources


def test_new_actions_have_sourced_rows():
    by_action: dict[str, set[str]] = {}
    for r in load_outcomes():
        by_action.setdefault(r.action, set()).add(r.plant)
    assert len(by_action.get("mulch", ())) >= 3
    assert len(by_action.get("humidity", ())) >= 2


def test_problems_in_a_month_are_only_the_rows_for_that_month():
    # the wait page's "Problems to watch for in October" (21 Oct)
    from herbtwin.outcomes import problems_in

    assert problems_in("basil", 10) == ["basil downy mildew", "powdery mildew"]
    assert "aphids" in problems_in("Ocimum basilicum", 7)
    assert problems_in("not a plant we know", 7) == []
