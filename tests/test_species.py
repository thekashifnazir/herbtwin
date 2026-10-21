import pytest

from herbtwin.species import PlantMatch, display_name, match_plant, match_species


@pytest.mark.parametrize(
    ("name", "key", "how"),
    [
        ("Mentha spicata", "mentha spicata", "exact"),
        ("Rosemary (Salvia rosmarinus)", "salvia rosmarinus", "exact"),
        ("Salvia rosmarinus (rosemary)", "salvia rosmarinus", "exact"),
        ("Rosmarinus officinalis", "salvia rosmarinus", "exact"),
        ("ocimum basilicum L.", "ocimum basilicum", "binomial"),
        ("Mentha sp.", "mentha", "exact"),
        ("Mentha x piperita", "mentha", "genus"),
        ("Mentha suaveolens", "mentha", "genus"),
        ("rosa x", "rosa", "exact"),
        ("Rosa canina", "rosa", "genus"),
        ("Mint", "mentha spicata", "exact"),
        ("Salvia officinalis 'Purpurascens'", "salvia officinalis 'purpurascens'", "exact"),
    ],
)
def test_names_resolve_to_norm_keys(name, key, how):
    assert match_plant(name) == PlantMatch(key, how)


@pytest.mark.parametrize("name", ["Salvia nemorosa", "Lamiaceae", "", "a plant", "Monarda didyma"])
def test_no_near_miss_and_no_species_borrowing(name):
    # a genus resolves only to a genus-level entry: there is no "salvia" key
    assert match_plant(name) == PlantMatch(None, "none")


def test_match_species_falls_back_to_the_common_name():
    assert match_species("Unknownia weirdii", "basil").key == "ocimum basilicum"
    assert match_species("Ocimum basilicum", "mint").key == "ocimum basilicum"


@pytest.mark.parametrize(
    ("name", "common", "shown"),
    [
        ("Mentha spicata (mint)", "mint", "Mint (Mentha spicata)"),
        ("Sage (Salvia officinalis)", "Common sage", "Common sage (Salvia officinalis)"),
        (
            "Petroselinum crispum (curly parsley)",
            "Curly parsley",
            "Curly parsley (Petroselinum crispum)",
        ),
        ("Marjoram (Origanum majorana)", "Sweet marjoram", "Sweet marjoram (Origanum majorana)"),
        ("Coriandrum sativum", "Coriander/cilantro", "Coriander/cilantro (Coriandrum sativum)"),
        ("Salvia rosmarinus", "", "Salvia rosmarinus"),
        ("Basil", "basil", "Basil"),
        ("", "mint", "Mint"),
        ("Mentha (spearmint (garden))", "mint", "Mint (Mentha spearmint garden)"),
        ("(mint", "mint", "Mint"),
        ("Mint (Mentha sp.)", "Garden mint", "Garden mint (Mentha sp.)"),
    ],
)
def test_the_shown_name_is_common_then_latin_without_doubling(name, common, shown):
    assert display_name(name, common) == shown
