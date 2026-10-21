import json
import re
from collections import defaultdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from herbtwin.seasonal import SeasonalNorm, load_norms, normal_for, plants

GARDEN = [
    "salvia officinalis",
    "salvia officinalis 'purpurascens'",
    "artemisia dracunculus",
    "salvia rosmarinus",
    "origanum vulgare",
    "allium tuberosum",
    "petroselinum crispum",
    "mentha spicata",
    "melissa officinalis",
    "rosa",
    "polystichum setiferum",
    "dryopteris filix-mas",
    "acer palmatum",
    "ocimum basilicum",
    "thymus vulgaris",
    "coriandrum sativum",
    "allium schoenoprasum",
    "anethum graveolens",
    "laurus nobilis",
]


def _by_plant() -> dict[str, list[SeasonalNorm]]:
    grouped: dict[str, list[SeasonalNorm]] = defaultdict(list)
    for norm in load_norms():
        grouped[norm.plant].append(norm)
    return grouped


def test_every_plant_has_each_month_exactly_once():
    for plant, norms in _by_plant().items():
        assert sorted(n.month for n in norms) == list(range(1, 13)), plant


def test_the_garden_and_culinary_herbs_are_covered_outdoors():
    grouped = _by_plant()
    for plant in GARDEN:
        assert plant in grouped, plant
        assert not any(n.indoor for n in grouped[plant]), plant


def test_at_least_eight_houseplants_are_covered_indoors():
    indoor = [p for p, norms in _by_plant().items() if all(n.indoor for n in norms)]
    assert len(indoor) >= 8


def test_a_plant_keeps_one_identity_across_months():
    for plant, norms in _by_plant().items():
        assert plant == plant.lower(), plant
        assert len({tuple(n.common_names) for n in norms}) == 1, plant
        assert len({n.indoor for n in norms}) == 1, plant


def test_no_name_points_at_two_plants():
    owner: dict[str, str] = {}
    for plant, norms in _by_plant().items():
        for name in {plant, *norms[0].common_names}:
            assert owner.setdefault(name.casefold(), plant) == plant, name


def test_every_entry_cites_a_source_and_names_signs():
    for n in load_norms():
        assert n.sources and all(s.strip() for s in n.sources), (n.plant, n.month)
        assert n.problem_signs, (n.plant, n.month)
        assert n.next_change.strip(), (n.plant, n.month)


def test_every_source_is_a_link_or_a_repo_doc_so_no_noncommercial_table_is_cited():
    root = Path(__file__).resolve().parents[1]
    for n in load_norms():
        for s in n.sources:
            assert s.startswith("https://") or (root / s).is_file(), (n.plant, n.month, s)
            assert "plantfolio" not in s.casefold(), (n.plant, n.month, s)


def test_mint_in_october_is_normal_dieback_with_spring_regrowth_next():
    norm = normal_for("mint", 10)
    assert norm is not None
    assert "normal_dieback" in norm.status
    assert norm.next_change_month == 3


def test_a_dormant_or_dying_back_perennial_names_the_sign_of_a_dead_plant():
    # The reassurance "it is only dormant" must come with the sign that it is not.
    annuals = {"ocimum basilicum", "coriandrum sativum", "anethum graveolens"}
    dead = re.compile(r"rot|soft|mush|hollow|dead|dying|shrivel", re.IGNORECASE)
    for n in load_norms():
        if n.plant in annuals or not {"normal_dieback", "dormant"} & set(n.status):
            continue
        assert any(dead.search(s) for s in n.problem_signs), (n.plant, n.month)


def test_next_change_is_a_different_month():
    for n in load_norms():
        assert n.next_change_month != n.month, (n.plant, n.month)


def test_a_tier_c_entry_cites_guidance_not_only_encyclopedia_or_local_notes():
    def guidance(src: str) -> bool:
        return src.startswith("http") and "wikipedia.org" not in src and "rhsplants" not in src

    for n in load_norms():
        if n.evidence_tier == "C":
            assert any(guidance(s) for s in n.sources), (n.plant, n.month)


def test_lookup_by_common_name_matches_the_scientific_key_in_any_case():
    assert normal_for("  Spearmint ", 10) == normal_for("Mentha spicata", 10)
    assert normal_for("ROSEMARY", 1) == normal_for("salvia rosmarinus", 1)
    assert normal_for("mint", 10, region=" uk ") == normal_for("mint", 10)


def test_editing_a_returned_norm_does_not_change_the_table():
    normal_for("mint", 10).normal_signs.append("scribble")
    assert "scribble" not in normal_for("mint", 10).normal_signs


def test_sage_and_purple_sage_are_distinct_entries():
    assert normal_for("sage", 6).plant == "salvia officinalis"
    assert normal_for("purple sage", 6).plant == "salvia officinalis 'purpurascens'"


def test_unknown_plant_month_or_region_returns_none():
    assert normal_for("triffid", 10) is None
    assert normal_for("mint", 13) is None
    assert normal_for("mint", 0) is None
    assert normal_for("mint", 10, region="US") is None


def test_plants_lists_each_key_once_sorted():
    keys = plants()
    assert keys == sorted(set(keys))
    assert "mentha spicata" in keys


def test_loader_rejects_a_status_outside_the_contract(tmp_path):
    bad = {
        "plant": "mentha spicata",
        "common_names": ["mint"],
        "region": "UK",
        "month": 10,
        "status": ["sulking"],
        "normal_signs": [],
        "problem_signs": ["rust"],
        "next_change": "regrowth in spring",
        "next_change_month": 3,
        "evidence_tier": "C",
        "sources": ["docs/reference/herb-care-packs.md"],
    }
    path = tmp_path / "norms.json"
    path.write_text(json.dumps([bad]))
    with pytest.raises(ValidationError):
        load_norms(path)


def test_an_entry_without_a_source_is_rejected():
    with pytest.raises(ValidationError):
        SeasonalNorm(
            plant="mentha spicata",
            common_names=["mint"],
            region="UK",
            month=10,
            status=["normal_dieback"],
            normal_signs=[],
            problem_signs=[],
            next_change="regrowth in spring",
            next_change_month=3,
            evidence_tier="C",
            sources=[],
        )


# A sign naming a disease or pest must never be listed as normal: phase A answers
# "leave it, this is normal" from these lists, so false reassurance is the costly error.
DISEASE_OR_PEST = re.compile(
    r"\b(rot|rots|rotting|rotten|mould|mouldy|mold|mildew|pustules?|rust|rusty|aphids?|"
    r"weevils?|mealybugs?|mites?|slugs?|snails?|scale insects?|whitefl(y|ies)|caterpillars?)\b",
    re.IGNORECASE,
)


def test_no_normal_sign_names_a_disease_or_pest():
    for n in load_norms():
        for sign in n.normal_signs:
            assert not DISEASE_OR_PEST.search(sign), (n.plant, n.month, sign)


def test_no_sign_is_both_normal_and_a_problem():
    for n in load_norms():
        assert not set(n.normal_signs) & set(n.problem_signs), (n.plant, n.month)


# Cross-check fixes: a normal-looking sign that a common disease of the plant also causes in
# that month must come with the problem sign that tells them apart.


@pytest.mark.parametrize("month", [8, 9, 10, 11])
def test_outdoor_basil_late_season_names_downy_mildew_by_its_own_signs(month):
    # Basil downy mildew yellows, then browns or blackens leaves, outdoors as well as in.
    norm = normal_for("basil", month)
    assert any(
        "downy mildew" in s and "veins" in s and "indoor" not in s for s in norm.problem_signs
    ), month


@pytest.mark.parametrize("month", [8, 9, 10, 11])
def test_blackened_basil_is_only_normal_after_cold(month):
    for sign in normal_for("basil", month).normal_signs:
        if "black" in sign:
            assert re.search(r"cold|frost", sign), (month, sign)


def test_french_tarragon_is_dying_back_by_october():
    assert "normal_dieback" in normal_for("french tarragon", 10).status
    assert normal_for("french tarragon", 9).next_change_month == 10


def test_male_fern_september_allows_autumn_browning_with_moist_compost():
    norm = normal_for("male fern", 9)
    assert any("autumn" in s and "moist" in s for s in norm.normal_signs)
    assert not any("not autumn yet" in s for s in norm.problem_signs)


@pytest.mark.parametrize("plant", ["chives", "garlic chives"])
def test_october_allium_yellowing_comes_with_rust_and_white_rot_signs(plant):
    signs = " ".join(normal_for(plant, 10).problem_signs)
    assert "rust" in signs and "white rot" in signs, plant
