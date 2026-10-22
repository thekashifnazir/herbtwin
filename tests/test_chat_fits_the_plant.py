"""The chat answers for this plant where it grows (22 Oct site walk, healthy curly parsley
outdoors in the ground, London): "Is it safe to eat?" got "Yes … but do not consume if you
have kidney disease, are pregnant, or have oedema (RHS)", a herbal site's medicinal caution
credited to the RHS; "Should I bring it inside for the winter?" got "moving potted parsley"
for a plant in the ground that is hardy outdoors."""

from herbtwin.adapters.mock import MockAdapter
from herbtwin.chat import KITCHEN_RULE, SYSTEM, context, reply
from herbtwin.schemas import SpeciesCandidate, Told
from herbtwin.search import Found, Hit
from tests.test_chat import FakeSearch, _answered, _tool
from tests.test_scenarios import _env, _rec

PARSLEY = SpeciesCandidate(name="Petroselinum crispum", common_name="curly parsley", confidence=0.9)


def _as(rec, species=PARSLEY, **update):
    rec.observation = rec.observation.model_copy(update={"species": [species], **update})
    return rec


def _parsley(tmp_path, **update):
    return _as(_answered(_rec(tmp_path, env=_env())), container="ground", **update)


def _system(rec) -> str:
    m = MockAdapter(["Fine."])
    reply(m, rec, message="ok?", past=[], history=None, search=None)
    return m.calls[0]["messages"][0]["content"]


# --- where it grows, and its winter --------------------------------------------------


def test_the_plant_block_says_where_it_grows_in_plain_words(tmp_path):
    block = context(_parsley(tmp_path), None)
    assert "where: outdoors, in the ground (not in a pot)" in block
    rec = _as(_answered(_rec(tmp_path, env=_env(), setting="indoor")), container="pot")
    assert "where: indoors, in a pot" in context(rec, None)


def test_where_it_grows_follows_what_the_person_told_us(tmp_path):
    # the read said the ground; their note said a pot: the chat goes with them, as the band
    rec = _parsley(tmp_path)
    rec.told = Told(question="It is in a pot on a sunny balcony.")
    assert "where: outdoors, in a pot" in context(rec, None)
    rec.told = Told(setting="indoor")  # "Wrong? Switch"
    assert "where: indoors, in the ground (not in a pot)" in context(rec, None)


def test_the_plant_block_carries_its_winter_from_the_crop_calendar(tmp_path):
    # RHS H6 and "overwinters outdoors: y" for parsley; basil is frost tender
    assert "winter: stays outdoors over a UK winter (RHS H6)" in context(_parsley(tmp_path), None)
    basil = SpeciesCandidate(name="Ocimum basilicum", common_name="basil", confidence=0.9)
    rec = _as(_answered(_rec(tmp_path, env=_env())), basil)
    assert "winter: frost tender, does not survive a UK winter outdoors" in context(rec, None)


def _rosemary(tmp_path, container, setting="outdoor"):
    rec = _answered(_rec(tmp_path, env=_env(), setting=setting))  # RHS H4
    rec.observation = rec.observation.model_copy(update={"container": container})
    return rec


POTTED_H4 = (
    "winter: in a pot outdoors, move it under cover or protect it in hard frosts "
    "(RHS H4; about one step less hardy in a pot)"
)


def test_an_h4_herb_stays_out_in_the_ground_and_needs_cover_in_a_pot(tmp_path):
    # second review: "stays outdoors … (RHS H4, H3 in a pot)" for potted rosemary
    assert "winter: stays outdoors over a UK winter (RHS H4)" in context(
        _rosemary(tmp_path, "ground"), None
    )
    block = context(_rosemary(tmp_path, "pot"), None)
    assert POTTED_H4 in block and "H3" not in block


def test_a_hardier_herb_in_a_pot_stays_out_and_the_pot_step_is_ours(tmp_path):
    sage = SpeciesCandidate(name="Salvia officinalis", common_name="sage", confidence=0.9)
    rec = _as(_answered(_rec(tmp_path, env=_env())), sage, container="pot")  # RHS H5
    block = context(rec, None)
    assert (
        "winter: stays outdoors over a UK winter (RHS H5; about one step less hardy in a pot)"
        in block
    )
    assert "H4" not in block


def test_an_indoor_herb_is_called_hardy_outdoors(tmp_path):
    rec = _as(_answered(_rec(tmp_path, env=_env(), setting="indoor")), container="ground")
    assert "winter: hardy outdoors in a UK winter (RHS H6)" in context(rec, None)


def test_what_the_person_told_us_changes_the_winter_line(tmp_path):
    rec = _rosemary(tmp_path, "ground")
    rec.told = Told(question="It is in a pot on a sunny balcony.")
    assert POTTED_H4 in context(rec, None)
    rec = _parsley(tmp_path)
    rec.told = Told(setting="indoor")  # "Wrong? Switch"
    assert "winter: hardy outdoors in a UK winter (RHS H6)" in context(rec, None)


def test_the_prompt_says_to_answer_for_where_it_grows_and_never_assume_a_pot():
    assert "never assume a pot" in SYSTEM
    assert "winter" in SYSTEM


# --- safe to eat -----------------------------------------------------------------------


def _named(tmp_path, name, common, confidence=0.9):
    species = SpeciesCandidate(name=name, common_name=common, confidence=confidence)
    return _as(_answered(_rec(tmp_path, env=_env())), species, container="ground")


def test_a_kitchen_herb_is_named_as_one_and_the_prompt_says_how_to_answer(tmp_path):
    system = _system(_parsley(tmp_path))
    assert "kitchen: a common kitchen herb" in system and KITCHEN_RULE in system
    # never "say yes" outright: warnings at kitchen amounts stay
    assert "say yes" not in KITCHEN_RULE
    for kept in ("normal kitchen amounts", "blood thinners", "allergy", "slug pellets"):
        assert kept in KITCHEN_RULE
    assert "look-alike" in KITCHEN_RULE
    assert "do not give large-dose medicinal cautions as reasons not to eat it" in KITCHEN_RULE


def test_a_spearmint_read_is_a_kitchen_herb_through_the_calendars_mint(tmp_path):
    rec = _named(tmp_path, "Mentha spicata", "spearmint")
    assert "kitchen: a common kitchen herb" in context(rec, None)


def test_pennyroyal_is_never_a_kitchen_herb(tmp_path):
    # Opus review: Mentha pulegium matched "Mentha spp." through the genus alone
    rec = _named(tmp_path, "Mentha pulegium", "pennyroyal")
    system = _system(rec)
    assert "kitchen:" not in system and KITCHEN_RULE not in system
    assert "winter:" not in system


def test_an_unsure_name_on_a_good_photo_is_not_a_kitchen_herb(tmp_path):
    rec = _named(tmp_path, "Petroselinum crispum", "curly parsley", confidence=0.3)
    system = _system(rec)
    assert "kitchen:" not in system and KITCHEN_RULE not in system


def test_the_sure_name_bar_is_pinned(tmp_path):
    for confidence, kitchen in ((0.59, False), (0.6, True)):
        rec = _named(tmp_path, "Petroselinum crispum", "curly parsley", confidence=confidence)
        assert ("kitchen:" in context(rec, None)) is kitchen, confidence


def test_a_wrong_latin_name_never_unlocks_the_kitchen_rule_through_the_common_name(tmp_path):
    # second review: fool's parsley named "parsley" matched parsley through the common name
    for name in ("Aethusa cynapium", "Parsley (Aethusa cynapium)"):
        system = _system(_named(tmp_path, name, "parsley"))
        assert "kitchen:" not in system and KITCHEN_RULE not in system, name
        assert "winter:" not in system, name


def test_a_rough_read_gets_no_kitchen_line(tmp_path):
    # the name may be wrong (a look-alike can be poisonous), as with the starters
    rec = _parsley(tmp_path)
    rec.answer = rec.answer.model_copy(update={"photo_issue": "blurry"})
    system = _system(rec)
    assert "kitchen:" not in system and KITCHEN_RULE not in system


def test_look_alikes_and_houseplants_get_no_kitchen_line(tmp_path):
    for name, common in (
        ("Anthriscus sylvestris", "cow parsley"),
        ("Conium maculatum", "hemlock"),
        ("Aethusa cynapium", "fool's parsley"),
        ("Monstera deliciosa", "Swiss cheese plant"),
    ):
        system = _system(_named(tmp_path, name, common))
        assert "kitchen:" not in system and KITCHEN_RULE not in system, name


SAID = (
    "Yes, curly parsley is safe to eat in normal culinary amounts, but avoid excessive use, "
    "especially as an essential oil, and do not consume if you have kidney disease, are "
    "pregnant, or have oedema (RHS)."
)
PAGES = Found(
    [
        Hit(
            "Petroselinum crispum Parsley PFAF Plant Database",
            "https://pfaf.org/user/Plant.aspx?LatinName=Petroselinum+crispum",
            "Known hazards: should not be used by pregnant women or people with kidney "
            "problems; the oil is toxic in large doses.",
        ),
        Hit(
            "How to grow Parsley | RHS Guide",
            "https://www.rhs.org.uk/herbs/parsley/grow-your-own",
            "Parsley is a popular herb for cooking. Sow little and often.",
        ),
        Hit(
            "Parsley | Kew",
            "https://www.kew.org/plants/parsley",
            "Parsley has long been used as a medicine and a food.",
        ),
    ],
    "tavily",
    None,
)


def _asked(tmp_path, said, message="Is it safe to eat?", pages=PAGES):
    m = MockAdapter([_tool("search_web", query="parsley"), said])
    return reply(
        m, _parsley(tmp_path), message=message, past=[], history=None, search=FakeSearch(pages)
    )


def test_the_walks_caution_loses_the_rhs_its_page_never_gave_and_keeps_its_words(tmp_path):
    r = _asked(tmp_path, SAID)
    assert r.text.startswith(SAID.removesuffix(" (RHS)."))
    assert "(RHS)" not in r.text and "do not consume if you have kidney disease" in r.text


def test_a_warning_the_model_wrote_is_never_rewritten(tmp_path):
    # Opus review: a warfarin warning was replaced by our own line; code never does that
    said = "Yes, in kitchen amounts. Do not eat large amounts if you take warfarin or are pregnant."
    assert _asked(tmp_path, said).text.startswith(said)


def test_a_caution_keeps_a_site_name_only_when_that_site_says_it(tmp_path):
    # the walk's reply credited a herbal site's caution to the RHS
    said = (
        "Large amounts can upset the kidneys (RHS). Large amounts can upset the kidneys "
        "(PFAF). Sow it little and often (RHS)."
    )
    assert _asked(tmp_path, said, "Is there a risk?").text.startswith(
        "Large amounts can upset the kidneys. Large amounts can upset the kidneys (PFAF). "
        "Sow it little and often (RHS)."
    )


def test_a_bracket_of_several_sites_keeps_only_the_one_whose_page_says_it(tmp_path):
    said = "Large amounts can upset the kidneys (RHS, PFAF)."
    assert _asked(tmp_path, said, "Is there a risk?").text.startswith(
        "Large amounts can upset the kidneys (PFAF)."
    )


def test_liverwort_is_not_a_liver_caution(tmp_path):
    said = "Liverwort on the compost does it no harm (RHS)."
    assert _asked(tmp_path, said, "What is the green crust?").text.startswith(said)


def test_a_caution_spelt_another_way_on_the_page_keeps_its_citation(tmp_path):
    pfaf = Found(
        [
            Hit(
                "Petroselinum crispum Parsley PFAF Plant Database",
                "https://pfaf.org/user/Plant.aspx?LatinName=Petroselinum+crispum",
                "Large doses may cause edema; avoid them when breastfeeding.",
            )
        ],
        "tavily",
        None,
    )
    said = "Large doses may worsen oedema (PFAF). Avoid them when breast-feeding (PFAF)."
    assert _asked(tmp_path, said, "Is there a risk?", pfaf).text.startswith(said)


def test_used_medicinally_is_not_a_caution_and_keeps_its_citation(tmp_path):
    said = "It has been used medicinally since Roman times (Kew)."
    assert _asked(tmp_path, said, "What is it used for?").text.startswith(said)


def test_the_prompt_asks_for_a_site_only_for_what_its_own_page_says(tmp_path):
    m = MockAdapter(["Fine."])
    reply(m, _parsley(tmp_path), message="ok", past=[], history=None, search=FakeSearch(PAGES))
    assert "only for a fact that site's own result says" in m.calls[0]["messages"][0]["content"]


# --- annuals and bolting (site walk 2, 22 Oct, r7) --------------------------------------

CORIANDER = SpeciesCandidate(name="Coriandrum sativum", common_name="coriander", confidence=0.9)


def _coriander(tmp_path, notes=""):
    return _as(_answered(_rec(tmp_path, env=_env())), CORIANDER, container="pot", notes=notes)


def test_an_annual_is_named_as_one_with_its_one_season(tmp_path):
    block = context(_coriander(tmp_path), None)
    assert "life: an annual: it grows, flowers, sets seed and dies in one season" in block
    # parsley lives two years; a perennial gets no life line
    assert "life: a biennial" in context(_parsley(tmp_path), None)
    rosemary = SpeciesCandidate(name="Salvia rosmarinus", common_name="rosemary", confidence=0.9)
    assert "life:" not in context(_as(_answered(_rec(tmp_path, env=_env())), rosemary), None)


def test_a_bolted_annual_is_finishing_and_never_told_it_lasts_the_winter(tmp_path):
    # r7: "Leave it outdoors; it can survive a UK winter with protection (RHS H5)." for a
    # coriander the read said had bolted and was flowering: an annual that has flowered dies
    rec = _coriander(tmp_path, notes="The coriander has bolted and is flowering, dying back.")
    block = context(rec, None)
    assert "bolted: it is flowering, so this plant is finishing" in block
    assert "winter: finishing after flowering, so it will not last the winter" in block
    assert "survives a UK winter" not in block and "H5" not in block
    # the same coriander not yet bolted keeps the calendar's winter line
    young = context(_coriander(tmp_path), None)
    assert "(RHS H5" in young and "finishing" not in young
    assert "bolted:" not in young


def test_the_prompt_says_a_finishing_plant_is_never_kept_for_winter_and_no_h_codes():
    assert "If PLANT says it is finishing" in SYSTEM
    assert "sow again" in SYSTEM
    assert "never write a hardiness code such as H5" in SYSTEM


def test_a_bolted_dill_is_finishing_too_and_a_flowering_perennial_is_not(tmp_path):
    dill = SpeciesCandidate(name="Anethum graveolens", common_name="dill", confidence=0.9)
    rec = _as(_answered(_rec(tmp_path, env=_env())), dill, notes="The dill has bolted.")
    assert "bolted: it is flowering, so this plant is finishing" in context(rec, None)
    # a perennial in flower is no end of life: mint flowers every summer and comes back
    mint = SpeciesCandidate(name="Mentha spicata", common_name="spearmint", confidence=0.9)
    rec = _as(_answered(_rec(tmp_path, env=_env())), mint, notes="The mint is flowering.")
    block = context(rec, None)
    assert "finishing" not in block and "life:" not in block


def test_the_prompt_keeps_the_hardiness_codes_out_of_the_reply():
    # review: PLANT still carries "(RHS H6)"; the prompt says the codes are for the model
    assert "RHS codes in PLANT (H4, H5, H6) are for you" in SYSTEM
