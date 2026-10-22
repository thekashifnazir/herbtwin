"""22 Oct, Kash: "why aren't we doing products too as doesn't that help our tavily case?"
A Leave it answer says "Nothing you need to buy for this one." and keeps saying it; under it,
a small "Handy to have" row of 1 to 2 things for what the answer says to watch for (a cold
night: fleece; a pot standing in the wet: pot feet; compost that stays wet: a meter), found
with the same Tavily shop search. Never a spray or pellets; nothing when nothing fits."""

import json
import re

import pytest

from herbtwin.answer import FROST_SIGN, LEAVE_BUT_PROTECT
from herbtwin.schemas import Location, ProblemSeen
from herbtwin.shops import (
    CHECK_METER,
    COPPER_TAPE,
    INSECT_MESH,
    NIGHT_FLEECE,
    POT_FEET,
    SLUG_NEMATODES,
    STICKY_TRAPS,
    WEEVIL_NEMATODES,
    ShopFinder,
    handy_for,
    listed_price,
    plain_title,
    shop_page,
)
from tests.fakes import follow
from tests.test_shops import FLEECE_PAGE, StubTavily
from tests.test_web import ADV, JPEG, OBS, _client
from tests.test_web_answer_page import _card

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")

COLD = f"• {FROST_SIGN.format(day='Saturday')} Seen it? Send a new photo."
# two season signs as the answer writes them (answer.short_sign drops the bracketed notes)
WET = (
    "• Pot standing in water or sodden compost "
    "• Leaves yellow or grey and wilt while compost is wet, stem base dark and soft. "
    "Seen either? Send a new photo."
)
POT_FEET_PAGE = "https://www.crocus.co.uk/product/_/terracotta-pot-feet/classid.2000035519/"
WEEDKILLER_PAGE = "https://www.diy.com/garden/fleece-and-weedkiller-pack/5059340.prd"


def test_a_cold_night_outdoors_is_fleece_and_never_indoors():
    assert handy_for([FROST_SIGN.format(day="Saturday")], outdoor=True, in_pot=False) == [
        NIGHT_FLEECE
    ]
    assert handy_for([FROST_SIGN.format(day="Saturday")], outdoor=False, in_pot=True) == []
    # a cold window indoors is where it sits, not a frost to cover
    sign = "leaves limp, dark or blotched after a cold night by the window or behind curtains"
    assert handy_for([sign], outdoor=False, in_pot=True) == []
    assert handy_for(["pot unwrapped as hard frosts begin"], outdoor=True, in_pot=True) == [
        NIGHT_FLEECE
    ]


def test_a_months_frost_sign_without_the_twins_cold_night_is_no_fleece():
    # normal dieback, or a sign that comes before any cold: nothing to cover (season norms)
    for sign in (
        "top growth yellows and dies back from October, fully after the first hard frost",
        "some green shoots left until the first frost",
        "leaves yellowing between the veins or blackening in a mild spell before any cold night",
    ):
        assert handy_for([sign], outdoor=True, in_pot=True) == []


def test_a_pot_in_the_wet_is_pot_feet_outdoors_and_wet_compost_a_meter():
    wet = "pot standing in water or sodden compost (winter-wet risk)"
    assert handy_for([wet], outdoor=True, in_pot=True) == [POT_FEET, CHECK_METER]
    assert handy_for([wet], outdoor=True, in_pot=False) == [CHECK_METER]  # no pot to lift
    assert handy_for([wet], outdoor=False, in_pot=True) == [CHECK_METER]  # a saucer indoors
    for rot in (
        "drooping while the compost is still wet (root rot, not thirst)",
        "compost staying wet in a pot with no drainage (root rot risk)",
        "pot standing in water or compost waterlogged",
        "leaves yellowing with compost that never dries",
    ):
        assert handy_for([rot], outdoor=False, in_pot=True) == [CHECK_METER], rot


def test_at_most_two_each_once_in_the_watch_order():
    signs = [
        FROST_SIGN.format(day="Saturday"),
        "pot standing in water for weeks",
        "soft, mushy or yellow leaf bases with wet compost (rot from overwatering)",
        "yellowing leaves with wet compost or a pot without drainage (overwatering)",
    ]
    assert handy_for(signs, outdoor=True, in_pot=True) == [NIGHT_FLEECE, POT_FEET]
    assert handy_for(["holes eaten in the leaves by slugs"], outdoor=True, in_pot=True) == []


def _leave_it(tmp_path, pages, watch=COLD, setting="outdoor", container="pot"):
    tmp_path.mkdir(exist_ok=True)
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    c.app.state.shops = ShopFinder(StubTavily(pages))
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r"/answers/([0-9a-f]{32})", str(page.url))[1]
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.observation.setting, rec.observation.container = setting, container
    rec.answer.do = [_card("leave_normal", "today")]
    rec.answer.headline, rec.answer.watch = "Leave it for now and keep an eye on it.", watch
    return c, rid


def test_a_leave_it_answer_with_a_cold_night_shows_fleece_as_handy(tmp_path):
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    got = c.get(f"/answers/{rid}/extras")
    assert got.status_code == 200
    text = got.text
    # the answer still needs nothing, and says so first
    assert '<p class="extras-none muted">Nothing you need to buy for this one.</p>' in text
    assert "<h3>Handy to have</h3>" in text
    assert "Horticultural fleece, for a cold night" in text and f'href="{FLEECE_PAGE}"' in text
    assert "at B&amp;Q" in text
    assert text.index("Nothing you need to buy") < text.index("<h3>Handy to have</h3>")
    # the same credit line as the shops: Tavily found it, no prices, never sprays
    assert "Found with Tavily on UK garden retailers" in text and "sprays or pellets" in text
    assert "Shops we found for this" not in text and "Or order online" not in text
    assert c.app.state.shops._tavily.asked == ["horticultural fleece buy UK"]  # one search


def test_handy_is_never_offered_beside_things_the_job_needs(tmp_path):
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    c.app.state.answers.get_for(rid, None).latest.answer.do = [_card("shelter", "today")]
    text = c.get(f"/answers/{rid}/extras").text
    assert "<h3>Shops we found for this</h3>" in text and "Handy to have" not in text
    assert "Nothing you need to buy" not in text  # it does need something


def test_two_handy_things_for_a_wet_pot_outdoors(tmp_path):
    c, rid = _leave_it(
        tmp_path,
        {
            "pot feet": [("Terracotta Pot Feet", POT_FEET_PAGE)],
            "soil moisture meter": [
                ("Soil Moisture Meter", "https://www.dobbies.com/soil-moisture-meter/5638482639.p")
            ],
        },
        watch=WET,
    )
    text = c.get(f"/answers/{rid}/extras").text
    assert text.index("Pot feet, to lift it out of the wet") < text.index(
        "A soil moisture meter, to check before you water"
    )


def test_nothing_handy_found_or_nothing_to_watch_shows_nothing(tmp_path):
    c, rid = _leave_it(tmp_path, {})  # the search finds no shop page
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    c, rid = _leave_it(tmp_path / "b", {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    c.app.state.answers.get_for(rid, None).latest.answer.watch = "Send a new photo if it changes."
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    assert c.app.state.shops._tavily.asked == []  # nothing to watch: no search at all


def test_handy_never_links_a_spray_or_pellets(tmp_path):
    c, rid = _leave_it(
        tmp_path, {"horticultural fleece": [("Fleece and Weedkiller Pack", WEEDKILLER_PAGE)]}
    )
    assert c.get(f"/answers/{rid}/extras").status_code == 204


def test_handy_stays_uk_only(tmp_path):
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    c.app.state.answers.get_for(rid, None).latest.location = Location(
        lat=48.85, lon=2.35, source="typed", label="Paris, FR"
    )
    assert c.get(f"/answers/{rid}/extras").status_code == 204


def test_the_cold_night_in_the_headline_counts_when_the_watch_has_other_signs(tmp_path):
    # answer.LEAVE_BUT_PROTECT: the twin's cold night is in the headline, the watch keeps
    # the month's signs
    c, rid = _leave_it(
        tmp_path,
        {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]},
        watch="• Holes eaten in the leaves. Seen it? Send a new photo.",
    )
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.answer.headline = LEAVE_BUT_PROTECT.format(day="Saturday")
    assert "Horticultural fleece, for a cold night" in c.get(f"/answers/{rid}/extras").text


def test_the_nothing_to_buy_line_is_the_slots_own(tmp_path):
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    page = c.get(f"/answers/{rid}").text
    line = re.search(r'said\.textContent = "([^"]+)";', page)[1]
    assert f">{line}</p>" in c.get(f"/answers/{rid}/extras").text


def test_a_rough_read_gets_nothing_handy(tmp_path):
    # the plant is a guess, so what it should watch for is too (22 Oct walk, the blurred mint)
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.answer.photo_issue = "blurry"
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    assert c.app.state.shops._tavily.asked == []


# round 2 (22 Oct, Kash on #429: "we should have a range right? That's only one... also any
# other info we should include?"): up to 3 shops for each, a price only as the page listed it
HARROD = "https://www.harrodhorticultural.com/garden-fleece-30gsm-pid7516.html"
DOBBIES = "https://www.dobbies.com/grow-it-frostgard-fleece/5637292297.p"
DOBBIES_2 = "https://www.dobbies.com/growing-frost-fleece/5637306838.p"
CROCUS = "https://www.crocus.co.uk/product/_/winter-fleece-plant-covers/classid.2000008848"
HAXNICKS = "https://www.haxnicks.co.uk/products/easy-fleece-jackets"


def test_a_range_of_up_to_three_each_at_a_different_shop_and_no_price(tmp_path):
    rows = [
        ("Garden Fleece - Harrod Horticultural", HARROD, "Garden Fleece 30gsm £12.95 In stock"),
        ("Grow it Frostgard Fleece - Dobbies Garden Centres", DOBBIES, "Frostgard fleece."),
        ("Grow it Heavy Duty Fleece - Dobbies", DOBBIES_2, "£9.99"),  # Dobbies again: skipped
        (
            "Buy Winter fleece plant covers: Delivery by Crocus",
            CROCUS,
            "Free delivery over £75 on plants. Winter fleece covers £8.99, £5.99 or £10.99",
        ),
        ("Easy Fleece Jackets | Haxnicks", HAXNICKS, "£4.99"),  # a fourth shop: past the range
    ]
    c, rid = _leave_it(tmp_path, {"horticultural fleece": rows})
    text = c.get(f"/answers/{rid}/extras").text
    item = text.split('<ul class="shop-options">', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r"<span class=\"shop-name\">at ([^<]+)</span>", item) == [
        "Harrod Horticultural",
        "Dobbies",
        "Crocus",
    ]
    assert "Haxnicks" not in text and DOBBIES_2 not in text
    # no price shows, even Harrod's one clear figure (hotfix, 22 Oct: see the B&Q carousel)
    assert "shop-price" not in text and "when we looked" not in text and "£" not in text
    assert "We don't check prices or stock" in text
    assert text.count("Horticultural fleece, for a cold night") == 1  # the why, once
    assert c.app.state.shops._tavily.asked == ["horticultural fleece buy UK"]  # one search


def test_no_price_said_when_no_page_listed_one(tmp_path):
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    text = c.get(f"/answers/{rid}/extras").text
    assert "shop-price" not in text and "when we looked" not in text
    assert "We don't check prices or stock" in text


@pytest.mark.parametrize(
    ("url", "content", "price"),
    [
        (HARROD, "Garden Fleece 30gsm £12.95. In stock.", "£12.95"),
        (HARROD, "Moisture & Light Meter £16.99. Delivery is free for orders over £50", "£16.99"),
        (HARROD, "Dryzone Moisture Meter Product code: 278297 £24 Excluding delivery", "£24"),
        (HARROD, "Was £12 now £9.50", "£9.50"),
        (HARROD, "£8.99 £8.99 add to basket", "£8.99"),  # the same figure twice is one
        (HARROD, "Winter fleece £8.99, £5.99 or £10.99", None),  # which one: never a guess
        (HARROD, "Free delivery over £75 on plants", None),
        (HARROD, "By price + Under £20 + Under £50 + Under £100", None),
        (HARROD, "Save £5 on fleece this week", None),
        (HARROD, "£5 off fleece", None),
        (HARROD, "No price here", None),
        # instalments, packs and "from" prices are not this page's one price (review of #429)
        (HARROD, "Fleece £24.99 or Klarna 3 payments of £8.33", "£24.99"),
        (HARROD, "Klarna 3 payments of £8.33", None),
        (HARROD, "Pay in 3 instalments £8.33", None),
        (HARROD, "from £5 Fleece £8.99", None),
        (HARROD, "Fleece 2 x £4.50", None),
        (HARROD, "Fleece £2 per metre", None),
        (HARROD, "Fleece £2/m", None),
        # the text cut inside a figure: "£12.95" read as "£12."
        (HARROD, "x" * 596 + "£12.", None),
        # a range page lists many things: its one figure is not this thing's price
        (FLEECE_PAGE, "Garden fleeces from 8 brands £14.99", None),
    ],
)
def test_a_price_is_one_clear_figure_on_a_product_page(url, content, price):
    assert listed_price(url, content) == price


def test_the_meter_must_be_for_soil_not_a_wall_or_wood():
    # 22 Oct probe: a meter search also found a damp meter for walls and a wood meter
    wickes = "https://www.wickes.co.uk/Dryzone-Moisture-Meter---Plastic/p/278297"
    stanley = "https://www.wickes.co.uk/Stanley-0-77-030-Moisture-Meter/p/267316"
    soil = "https://www.homebase.co.uk/en-uk/soil-moisture-tester---green/p/8393735"
    assert shop_page(wickes, "Dryzone Moisture Meter - Plastic", CHECK_METER) is None
    assert shop_page(stanley, "Stanley Moisture Meter with 2 Detection Pins", CHECK_METER) is None
    assert shop_page(soil, "Soil Moisture Tester - Green", CHECK_METER) == "Homebase"


def test_a_title_keeps_an_at_that_names_no_shop():
    assert plain_title("Frost Protection at Home Fleece - Dobbies", "x") == (
        "Frost Protection at Home Fleece"
    )


def test_the_jobs_shop_link_stays_the_first_while_handy_shows_the_range(tmp_path):
    rows = [
        ("Garden Fleece - Harrod Horticultural", HARROD),
        ("Grow it Frostgard Fleece - Dobbies Garden Centres", DOBBIES),
    ]
    finder = ShopFinder(StubTavily({"horticultural fleece": rows}))
    assert [x.shop for x in finder.links(["shelter"], outdoor=True)] == ["Harrod Horticultural"]
    handy = finder.handy([FROST_SIGN.format(day="Saturday")], outdoor=True)
    assert [o.shop for o in handy[0].options] == ["Harrod Horticultural", "Dobbies"]
    assert finder._tavily.asked == ["horticultural fleece buy UK"]  # one search for both


# round 3 (22 Oct, Kash: yes to non-chemical pest controls): a barrier, a trap or a
# biological control for the pest the photo showed, never a spray, pellets or any chemical
NEMASLUG = "https://www.harrodhorticultural.com/nemaslug-slug-killer-pid7623.html"
COPPER = "https://www.homebase.co.uk/en-uk/copper-slug-tape/p/8496747"


@pytest.mark.parametrize(
    ("pest", "outdoor", "in_pot", "want"),
    [
        ("slugs and snails", True, True, [SLUG_NEMATODES, COPPER_TAPE]),
        ("slugs and snails", True, False, [SLUG_NEMATODES]),  # copper tape goes round a pot
        ("slugs and snails", False, True, [COPPER_TAPE]),  # nematodes are watered into a bed
        ("vine weevil", False, True, [WEEVIL_NEMATODES]),
        ("aphids", True, False, [INSECT_MESH]),
        ("aphids", False, True, []),  # indoors: squash them, no mesh
        ("carrot fly", True, False, [INSECT_MESH]),
        ("allium leaf miner", True, False, [INSECT_MESH]),
        ("whitefly", False, True, [STICKY_TRAPS]),
        ("fungus gnats", False, True, [STICKY_TRAPS]),
        ("thrips", True, True, [STICKY_TRAPS]),
        ("rosemary beetle", True, True, []),  # picked off by hand: nothing to buy
        ("basil downy mildew", True, True, []),  # a disease: no control here
        (None, True, True, []),
    ],
)
def test_each_pest_gets_its_own_non_chemical_control(pest, outdoor, in_pot, want):
    assert handy_for([], outdoor, in_pot, pest) == want


def test_the_pests_control_comes_before_what_to_watch_for_and_two_at_most():
    cold = [FROST_SIGN.format(day="Saturday")]
    assert handy_for(cold, True, True, "slugs and snails") == [SLUG_NEMATODES, COPPER_TAPE]
    assert handy_for(cold, True, True, "vine weevil") == [WEEVIL_NEMATODES, NIGHT_FLEECE]


@pytest.mark.parametrize(
    ("product", "title", "url"),
    [
        # live titles, 22 Oct probe
        (SLUG_NEMATODES, "Nemaslug Slug Killer Pest Control - Harrod Horticultural", NEMASLUG),
        (COPPER_TAPE, "Copper Slug Tape", COPPER),
        (
            COPPER_TAPE,
            "Verve Copper Slug & snail Barrier tape",
            "https://www.diy.com/x/1880137_BQ.prd",
        ),
        (
            WEEVIL_NEMATODES,
            "Nemasys Vine Weevil Killer Nematodes",
            "https://www.thompson-morgan.com/p/nemasys-vine-weevil-killer-nematodes/404188503",
        ),
        (
            INSECT_MESH,
            "Ultra Fine Insect Mesh Netting - Harrod Horticultural",
            "https://www.harrodhorticultural.com/ultra-fine-insect-mesh-netting-pid7805.html",
        ),
        (
            STICKY_TRAPS,
            "Yellow Sticky Traps for Whitefly",
            "https://www.harrodhorticultural.com/yellow-sticky-traps-pid1234.html",
        ),
    ],
)
def test_a_real_control_page_is_linked(product, title, url):
    assert shop_page(url, title, product) is not None


@pytest.mark.parametrize(
    ("product", "title", "url"),
    [
        # sprays, pellets and "organic" pesticides never show, whatever the control
        (
            SLUG_NEMATODES,
            "Slug Repellent and Snail & Slug Killer",
            "https://www.diy.com/x/slug-killer.prd",
        ),
        (
            SLUG_NEMATODES,
            "Nematode and Ferric Phosphate Slug Pellets",
            "https://www.diy.com/x/1.prd",
        ),
        (COPPER_TAPE, "Copper Tape Slug Repellent 10m", "https://www.diy.com/x/2.prd"),
        (COPPER_TAPE, "Organic Copper Slug Barrier Pellets", "https://www.diy.com/x/3.prd"),
        (COPPER_TAPE, "Copper Tapes | Decorating tools", "https://www.diy.com/x/4.prd"),  # no slug
        # a gel or liquid slug killer sold with the tape (integrator review of #429)
        (COPPER_TAPE, "Copper Slug Tape with Slug Gel", "https://www.diy.com/x/11.prd"),
        (COPPER_TAPE, "Copper Slug Tape and Slug Liquid", "https://www.diy.com/x/12.prd"),
        (COPPER_TAPE, "Copper Slug Tape plus Concentrate", "https://www.diy.com/x/13.prd"),
        (INSECT_MESH, "Insect Mesh and Plant Oil Spray Kit", "https://www.diy.com/x/5.prd"),
        (INSECT_MESH, "Insect Mesh with Insecticidal Soap", "https://www.diy.com/x/6.prd"),
        (INSECT_MESH, "Netting and Bug Clear Ultra", "https://www.diy.com/x/7.prd"),
        (
            WEEVIL_NEMATODES,
            "Vine weevil killer",
            "https://www.crocus.co.uk/product/_/vine-weevil-killer/classid.2000051593",
        ),
        (
            WEEVIL_NEMATODES,
            "Provado Vine Weevil Killer 2 with nematodes acetamiprid",
            "https://www.diy.com/x/8.prd",
        ),
        (
            STICKY_TRAPS,
            "Critterkill Insect and Spider Sticky Traps",
            "https://www.diy.com/x/9.prd",
        ),  # no yellow
        (STICKY_TRAPS, "Yellow Sticky Traps and Pyrethrum Spray", "https://www.diy.com/x/10.prd"),
        # a slug killer with no chemical word, or a bundle that joins one to nematodes
        # (review of round 3)
        *[
            (SLUG_NEMATODES, t, f"https://www.diy.com/x/{i}.prd")
            for i, t in enumerate(
                [
                    "Growing Success Advanced Slug Killer nematode",
                    "Nemaslug and Slug Gone",
                    "Nematode Slug Kill Granules",
                    "Nematode Deterrent Granules",
                    "Nematode Sluggo Plus",
                    "Nematode Slug Control Nemaslug Spinosad",
                    "Nematode Slug Nix",
                    "Nematode and Slug Clear",
                    "Nemaslug Bundle with Slug Bait",
                ],
                start=20,
            )
        ],
    ],
)
def test_a_chemical_or_off_topic_page_never_shows_as_a_control(product, title, url):
    assert shop_page(url, title, product) is None


def test_a_slug_answer_shows_nematodes_and_copper_tape_never_pellets(tmp_path):
    c, rid = _leave_it(
        tmp_path,
        {
            "slug nematodes": [
                (
                    "Organic Slug Pellets - Harrod Horticultural",
                    "https://www.harrodhorticultural.com/organic-slug-pellets-pid1.html",
                ),
                ("Nemaslug Slug Killer Pest Control - Harrod Horticultural", NEMASLUG),
            ],
            "copper slug tape": [("Copper Slug Tape", COPPER)],
        },
        watch="Send a new photo if it changes.",
    )
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.answer.do = [_card("treat_or_remove", "today")]
    rec.problem = ProblemSeen(
        name="slugs and snails", looks_like="holes", source="https://www.rhs.org.uk/x"
    )
    text = c.get(f"/answers/{rid}/extras").text
    assert "Slug nematodes, a biological control" in text and NEMASLUG in text
    assert "Copper tape, a barrier round a pot" in text and COPPER in text
    assert "pellets" not in text.lower().replace("sprays or pellets", "")
    # the pick-off needs nothing; the controls are for if they keep coming back (Kash, 22 Oct)
    assert (
        '<p class="extras-none muted">Nothing you must buy. If they keep coming back:</p>' in text
    )
    assert "Nothing you need to buy for this one." not in text


def test_a_could_be_pest_gets_no_control(tmp_path):
    c, rid = _leave_it(
        tmp_path,
        {"copper slug tape": [("Copper Slug Tape", COPPER)]},
        watch="Send a new photo if it changes.",
    )
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.answer.do = [_card("treat_or_remove", "today")]
    rec.problem = ProblemSeen(
        name="slugs and snails", looks_like="holes", source="https://www.rhs.org.uk/x", sure=False
    )
    assert c.get(f"/answers/{rid}/extras").status_code == 204


# 22 Oct price probe (scratchpad nano/, pre-registered): on B&Q product pages the search
# snippet holds ANOTHER product's carousel, so its one clear £ figure is the wrong price
# (true £255.99 and £10.99). Kept as fixtures for a future pre-registered test of a stricter
# rule (a price tied to the page's own title); until one passes, no price shows
BQ_CAROUSEL = [
    (
        "Fargro Home and Garden Heavy-Duty Horticultural Fleece",
        "https://www.diy.com/departments/fargro-home-and-garden-heavy-duty-horticultural-fleece"
        "-6m-x-250m-18gsm-large-area-plant-protection/5060542961004_BQ.prd",
        "Plant Fleece Covers with Zip 4 pcs 70 gm 2.36x2 m. Great low price. Plant Fleece "
        "Covers with Zip 4 pcs 70 gm 2.36x2 m. £96.65Free home delivery. Add to basket.",
        "255.99",
    ),
    (
        "Horticultural Fleece with Drawstring for Winter Plant Cover",
        "https://www.diy.com/departments/2-pack-garden-fleece-plant-frost-protection-"
        "horticultural-fleece-with-drawstring-for-winter-plant-cover/5061076309515_BQ.prd",
        "vers with Drawstring 4 pcs 70 gm 0.8x1.2 m. Great low price. Plant Fleece Covers with "
        "Drawstring 4 pcs 70 gm 0.8x1.2 m. £23.65Free home delivery.",
        "10.99",
    ),
]


@pytest.mark.parametrize(("title", "url", "snippet", "true_price"), BQ_CAROUSEL)
def test_a_carousel_price_fools_the_snippet_rule_so_no_price_shows(
    tmp_path, title, url, snippet, true_price
):
    wrong = listed_price(url, snippet)
    assert wrong is not None and wrong != f"£{true_price}"  # why prices are off
    c, rid = _leave_it(tmp_path, {"horticultural fleece": [(title, url, snippet)]})
    text = c.get(f"/answers/{rid}/extras").text
    assert title.split()[0] in text  # the shop link still shows
    assert "when we looked" not in text and wrong not in text and "Prices as listed" not in text


def test_nothing_handy_for_a_plant_to_be_binned(tmp_path):
    # site walk 2 (22 Oct), r5: "Remove it… bag and bin" still offered "Horticultural fleece,
    # for a cold night": nothing is handy for a plant that is going
    from herbtwin.answer import NO_CURE_HEADLINE

    c, rid = _leave_it(tmp_path, {"horticultural fleece": [("Garden Fleeces", FLEECE_PAGE)]})
    a = c.app.state.answers.get_for(rid, None).latest.answer
    a.do = [_card("treat_or_remove", "today")]
    a.headline = NO_CURE_HEADLINE
    got = c.get(f"/answers/{rid}/extras")
    assert "Handy to have" not in got.text and "fleece" not in got.text.lower()
    assert c.app.state.shops._tavily.asked == []  # no search for it either
