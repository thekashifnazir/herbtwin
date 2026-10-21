"""Genus-level seasonal norms: the photo reader often names a mint only as "Mentha sp."."""

import pytest

from herbtwin.seasonal import load_norms, normal_for, plants


def _genus_rows():
    return [n for n in load_norms() if n.plant == "mentha"]


@pytest.mark.parametrize("name", ["mentha", "Mint (unknown kind)", " Mentha sp. ", "mentha spp."])
def test_an_unnamed_mint_in_october_is_dying_back_with_spring_regrowth_next(name):
    norm = normal_for(name, 10)
    assert norm is not None and norm.plant == "mentha", name
    assert "normal_dieback" in norm.status
    assert norm.next_change_month == 3


def test_the_genus_covers_every_month_outdoors():
    rows = _genus_rows()
    assert sorted(n.month for n in rows) == list(range(1, 13))
    assert not any(n.indoor for n in rows)
    assert "mentha" in plants()


def test_plain_mint_still_means_spearmint():
    assert normal_for("mint", 10).plant == "mentha spicata"


def test_genus_rows_sit_a_tier_below_the_species_and_cite_the_rhs_mint_guide():
    species = {n.month: n for n in load_norms() if n.plant == "mentha spicata"}
    for n in _genus_rows():
        assert n.evidence_tier == "D", n.month
        assert n.evidence_tier >= species[n.month].evidence_tier, n.month
        assert "https://www.rhs.org.uk/herbs/mint/grow-your-own" in n.sources, n.month
