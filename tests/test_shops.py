"""Where to get it (shops.py): known UK garden retailers' product pages, found with Tavily,
never a chemical or a plant sold as a cure. A stub stands in for Tavily: no live calls."""

import time

import pytest

from herbtwin import shops
from herbtwin.config import load_settings
from herbtwin.search import Hit, SearchFailed
from herbtwin.shops import ShopFinder, affiliates_from, products_for, shop_page, shops_from

FLEECE_PAGE = (
    "https://www.diy.com/outdoor-garden/lawn-plant-care/plant-support-protection/garden-fleeces.cat"
)


class StubTavily:
    def __init__(self, pages=None, fail=False, slow=0.0):
        self.pages, self.fail, self.slow, self.asked = pages or {}, fail, slow, []

    def search(self, query, domains, n):
        self.asked.append(query)
        time.sleep(self.slow)
        if self.fail:
            raise SearchFailed("HTTP 500")
        assert domains == shops.DOMAINS and n == shops.RESULTS
        # a row is (title, url) or (title, url, the page's text as Tavily gives it)
        return [
            Hit(*r, *[""][len(r) - 2 :])
            for q, rows in self.pages.items()
            if q in query
            for r in rows
        ]


def test_each_action_gets_its_own_things_first_action_first_at_most_three():
    names = [p.name for p in products_for(["shelter", "repot"], outdoor=True)]
    assert names == ["Horticultural fleece", "A pot with drainage holes", "Peat-free compost"]
    assert [p.name for p in products_for(["change_soil", "repot"])][:2] == [
        "Peat-free compost",
        "Horticultural grit",
    ]  # compost once
    assert products_for(["leave_normal", "treat_or_remove", "ask_first", "isolate"]) == []


@pytest.mark.parametrize(
    ("url", "title", "ok"),
    [
        (FLEECE_PAGE, "Garden Fleeces | Plant Fleece Covers", "B&Q"),
        (
            "https://www.harrodhorticultural.com/garden-fleece-30gsm-pid7516.html",
            "Garden Fleece 30gsm",
            "Harrod Horticultural",
        ),
        # a blog or guide on a retailer's own site is not a shop page (probe, 21 Oct)
        (
            "https://www.haxnicks.co.uk/blogs/grow-at-home/garden-fleece",
            "What is Garden Fleece",
            None,
        ),
        (
            "https://www.harrodhorticultural.com/the-ultimate-guide-to-garden-fleece-pgid4059.html",
            "Guide to Garden Fleece",
            None,
        ),
        ("https://www.amazon.co.uk/fleece/dp/B01", "Garden fleece", None),  # not on the list
        ("http://www.diy.com/x/fleece.cat", "Fleece", None),  # https only
        ("https://www.diy.com/x/compost.cat", "Compost", None),  # not about fleece
        ("https://www.diy.com/x/fleece-spray.prd", "Fleece and bug killer spray", None),
        ("https://www.diy.com/x/fleece.prd", "Fleece with fungicide", None),
        ("https://www.diy.com/x/fleece.prd", "Herbal remedy fleece", None),
        ("https://www.thompson-morgan.com/garden-essentials/pest-control/fleece", "Fleece", None),
    ],
)
def test_only_a_known_shops_product_page_about_the_thing_and_never_a_chemical(url, title, ok):
    assert shop_page(url, title, shops.FOR_ACTION["shelter"][0]) == ok


def test_a_slug_pellet_or_weedkiller_page_is_never_linked():
    grit = shops.FOR_ACTION["change_soil"][1]
    assert shop_page("https://www.diy.com/x/grit.prd", "Grit and slug pellets", grit) is None
    assert shop_page("https://www.diy.com/x/grit.prd", "Grit weedkiller", grit) is None


def test_the_first_good_page_is_linked_and_kept_for_a_week():
    now = [0.0]
    tav = StubTavily(
        {
            "horticultural fleece": [
                ("What is Garden Fleece", "https://www.haxnicks.co.uk/blogs/g/fleece"),
                ("Garden Fleeces | Plant Fleece Covers | B&Q", FLEECE_PAGE),
            ]
        }
    )
    finder = ShopFinder(tav, clock=lambda: now[0])
    (link,) = finder.links(["shelter"], outdoor=True)
    assert (link.product, link.shop, link.url, link.paid) == (
        "Horticultural fleece", "B&Q", FLEECE_PAGE, False,
    )  # fmt: skip
    assert link.title == "Garden Fleeces | Plant Fleece Covers"  # the shop's name dropped
    assert tav.asked == ["horticultural fleece buy UK"]
    now[0] = 6 * 86400
    finder.links(["shelter"], outdoor=True)
    assert len(tav.asked) == 1  # cached
    now[0] = 8 * 86400
    finder.links(["shelter"], outdoor=True)
    assert len(tav.asked) == 2


def test_a_miss_is_kept_a_day_and_a_failure_five_minutes():
    now = [0.0]
    tav = StubTavily({})
    finder = ShopFinder(tav, clock=lambda: now[0])
    assert finder.links(["water"]) == [] and finder.links(["water"]) == []
    assert len(tav.asked) == 1
    now[0] = 86401
    finder.links(["water"])
    assert len(tav.asked) == 2
    broken = StubTavily(fail=True)
    now[0] = 0.0
    finder = ShopFinder(broken, clock=lambda: now[0])
    assert finder.links(["water"]) == [] and finder.links(["water"]) == []
    assert len(broken.asked) == 1  # an outage: one call per product per 5 minutes
    now[0] = 301
    finder.links(["water"])
    assert len(broken.asked) == 2


def test_the_days_searches_have_a_ceiling_then_nothing_until_tomorrow():
    from datetime import date

    from herbtwin.shops import DailyCap

    day = [date(2026, 10, 21)]
    cap = DailyCap(2, today=lambda: day[0])
    tav = StubTavily({})
    finder = ShopFinder(tav, cap=cap)
    finder.links(["repot"])  # three kinds of thing, two calls left today
    assert len(tav.asked) == 2
    finder.links(["change_soil"])
    assert len(tav.asked) == 2  # none at all now
    day[0] = date(2026, 10, 22)
    finder.links(["change_soil"])
    assert len(tav.asked) == 3


def test_fleece_only_outdoors_and_the_meter_is_for_checking_when_holding_off():
    assert [p.name for p in products_for(["shelter"])] == []
    assert [p.name for p in products_for(["shelter"], outdoor=True)] == ["Horticultural fleece"]
    assert [p.name for p in products_for(["dont_water"])] == [
        "A soil moisture meter, to check before you water"
    ]
    assert len(products_for(["water", "dont_water"])) == 1  # one meter, one search


def test_a_slow_search_is_left_out_not_waited_for(monkeypatch):
    monkeypatch.setattr(shops, "TIMEOUT_S", 0.05)
    finder = ShopFinder(StubTavily({"fleece": [("Fleece", FLEECE_PAGE)]}, slow=0.3))
    start = time.monotonic()
    assert finder.links(["shelter"], outdoor=True) == []
    assert time.monotonic() - start < 0.25


def test_an_affiliate_template_is_used_only_when_set_and_valid():
    got = affiliates_from(
        "diy.com=https://aff.example/t?u={url};crocus.co.uk=http://bad/{url};"
        "amazon.co.uk=https://x/{url};wickes.co.uk=https://no-placeholder"
    )
    assert got == {"diy.com": "https://aff.example/t?u={url}"}
    assert affiliates_from(None) == {} and affiliates_from("") == {}
    finder = ShopFinder(StubTavily({"fleece": [("Fleece", FLEECE_PAGE)]}), got)
    (link,) = finder.links(["shelter"], outdoor=True)
    assert link.paid and link.url.startswith("https://aff.example/t?u=https%3A%2F%2Fwww.diy.com%2F")


def test_the_finder_is_on_only_with_the_switch_and_tavily():
    on = {"HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_TAVILY_ENABLED": "1"}
    assert shops_from(load_settings(on)) is None  # the switch is off by default
    assert shops_from(load_settings({**on, "HERBTWIN_SHOP_LINKS": "1"})) is not None
    no_tavily = {"HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_SHOP_LINKS": "1"}
    assert shops_from(load_settings(no_tavily)) is None


def test_a_page_title_is_made_plain_and_short():
    from herbtwin.shops import plain_title

    assert plain_title("Buy Sylvagrow peat-free compost: Delivery by Crocus", "x") == (
        "Sylvagrow peat-free compost"
    )
    assert plain_title("Garden Fleece - Harrod Horticultural", "x") == "Garden Fleece"
    # live on 22 Oct: a range's B&Q row read "... Covers at B&Q at B&Q"
    assert plain_title("Garden Fleeces and Plant Fleece Covers at B&Q", "x") == (
        "Garden Fleeces and Plant Fleece Covers"
    )
    assert plain_title("Garden Fleeces | Plant Fleece Covers | B&Q", "x") == (
        "Garden Fleeces | Plant Fleece Covers"
    )
    long = plain_title(
        "Digital Soil Meter 4 in 1 PH Meter for Soil Moisture Meter Temperature Sunlight Sensor",
        "x",
    )
    assert long == "Digital Soil Meter 4 in 1 PH Meter for Soil Moisture Meter…"
    assert plain_title("| B&Q", "Horticultural fleece") == "Horticultural fleece"


@pytest.mark.parametrize(
    "title",
    [
        "Bug Clear Ultra Gun fleece",
        "Rose Clear Ultra fleece",
        "Fungus Clear Ultra fleece",
        "Resolva 24H fleece",
        "Roundup Optima+ fleece",
        "SB Plant Invigorator fleece",
        "Doff slug defence fleece",
        "Insect mesh fleece",
        "Provanto fleece",
        "Fleece with vine weevil protection",
        "Westland Plant Protection fleece",
        "Fleece with Bayer protection",
        "Ant bait station fleece",
        "Pest control fleece",
        "Cat repellent fleece",
        "Fleece treatment",
        "Molluscicide fleece",
        "Ant powder fleece",
        "Fleece and ants",
        "Dusting powder fleece",
        "Insect powder fleece",
        "Neem fleece",
    ],
)
def test_a_pest_or_weed_brand_is_never_linked(title):
    fleece = shops.FOR_ACTION["shelter"][0]
    assert shop_page("https://www.diy.com/x/fleece.prd", title, fleece) is None


def test_the_address_counts_and_the_word_must_be_whole():
    pot = shops.FOR_ACTION["repot"][0]
    url = "https://www.diy.com/x/roundup-weedkiller-pot.prd"
    assert shop_page(url, "Optima pot", pot) is None  # the chemical is only in the address
    assert shop_page("https://www.diy.com/x/a.prd", "Sulphate of Potash", pot) is None
    assert shop_page("https://www.diy.com/x/a.prd", "Westland Potting Compost", pot) is None
    assert shop_page("https://www.diy.com/x/a.prd", "Ceramic Plant Pots", pot) == "B&Q"
    healthy = shop_page("https://www.diy.com/x/c.prd", "Healthy Roots compost", shops.COMPOST)
    assert healthy == "B&Q"  # "healthy" is not "heals"


@pytest.mark.parametrize(
    "title", ["Garden Fleece £4.99", "Fleece 2m - 4.99", "Fleece sale", "Fleece 20% off"]
)
def test_a_title_with_a_price_or_an_offer_is_never_linked(title):
    fleece = shops.FOR_ACTION["shelter"][0]
    assert shop_page("https://www.diy.com/x/fleece.prd", title, fleece) is None


def test_searches_not_started_when_the_page_gives_up_never_run(monkeypatch):
    monkeypatch.setattr(shops, "TIMEOUT_S", 0.05)
    tav = StubTavily({}, slow=0.3)
    finder = ShopFinder(tav)
    finder._pool = shops.ThreadPoolExecutor(max_workers=1)  # one at a time: two wait
    assert finder.links(["repot"]) == []
    time.sleep(0.4)
    assert len(tav.asked) == 1  # the two queued ones were cancelled


def test_a_shop_may_file_fleece_under_plant_protection_in_its_address():
    url = "https://www.diy.com/outdoor-garden/lawn-plant-care/plant-support-protection/garden-fleeces.cat"
    assert shop_page(url, "Garden Fleeces", shops.FLEECE) == "B&Q"


def test_the_daily_ceiling_is_set_from_the_environment():
    import pytest as _pytest

    assert load_settings({}).shop_daily_searches == 200
    assert load_settings({"HERBTWIN_SHOP_DAILY_SEARCHES": "50"}).shop_daily_searches == 50
    with _pytest.raises(ValueError, match="whole number"):
        load_settings({"HERBTWIN_SHOP_DAILY_SEARCHES": "lots"})


def test_ant_and_powder_are_whole_words_only():
    # "plant" holds "ant"; a word match never refuses a plant pot
    pot = shops.FOR_ACTION["repot"][0]
    assert shop_page("https://www.diy.com/x/a.prd", "Ceramic Plant Pots", pot) == "B&Q"
    assert shop_page("https://www.diy.com/x/a.prd", "Planter pot", pot) == "B&Q"


def test_a_powder_is_refused_only_as_a_pest_product():
    # #344 review: "powders?" refused bone meal and powder-coated trellis
    compost = shops.COMPOST
    url = "https://www.diy.com/x/a.prd"
    assert shop_page(url, "Compost with bone meal powder", compost) == "B&Q"
    assert shop_page(url, "Powder coated compost bin", compost) == "B&Q"
    assert shop_page(url, "Compost and ant powder", compost) is None
    assert shop_page(url, "Compost with dusting powder", compost) is None


@pytest.mark.parametrize(
    "title",
    [
        "Derris powder compost",
        "Rotenone compost",
        "Pyrethrum compost",
        "Pyrethrins compost",
        "Bifenthrin compost",
        "Deltamethrin compost",
        "Lambda-cyhalothrin compost",
        "Acetamiprid compost",
        "Metaldehyde compost",
        "Ferric phosphate compost",
        "Bordeaux mixture compost",
        "Copper sulphate compost",
        "Sulphur dust compost",
        "Nicotine compost",
        "Glyphosate compost",
        "Fungus fighter compost",
        "Mildew spray compost",
    ],
)
def test_a_pesticide_active_without_cide_in_its_name_is_refused(title):
    # #345 review: narrowing "powder" let "Derris powder" through
    assert shop_page("https://www.diy.com/x/a.prd", title, shops.COMPOST) is None


@pytest.mark.parametrize(
    "title",
    ["Compost with bone meal powder", "Rooting powder and compost", "Powder coated compost bin"],
)
def test_a_garden_powder_that_is_not_a_pesticide_passes(title):
    assert shop_page("https://www.diy.com/x/a.prd", title, shops.COMPOST) == "B&Q"


def test_pruning_light_and_pest_checks_get_their_tools_never_a_spray():
    # 21 Oct, Kash's live look: a "light tidy" (prune) answer showed no shops
    assert [p.name for p in products_for(["prune"])] == ["Secateurs", "Herb snips"]
    assert [p.name for p in products_for(["move_light"])] == ["A plant grow light"]
    assert products_for(["move_light"], outdoor=True) == []  # outdoors: move it, buy nothing
    assert [p.name for p in products_for(["check_pests"])] == [
        "A hand lens, to look under the leaves"
    ]
    url = "https://www.diy.com/x/a.prd"
    snips = shops.FOR_ACTION["prune"][1]
    assert shop_page(url, "Herb snips and bug spray", snips) is None
    lens = shops.FOR_ACTION["check_pests"][0]
    assert shop_page(url, "30X Jewellers Loupe Magnifier Pocket Magnifying Eye", lens) == "B&Q"
    assert shop_page(url, "Insect magnifier trap", lens) is None


@pytest.mark.parametrize(
    "title", ["Secateurs and wound sealant", "Secateurs with pruning paint", "Tree paint secateurs"]
)
def test_a_wound_paint_or_sealant_is_never_linked(title):
    # #352 review: the RHS advises against wound paints after pruning
    secateurs = shops.FOR_ACTION["prune"][0]
    assert shop_page("https://www.diy.com/x/a.prd", title, secateurs) is None
    assert shop_page("https://www.diy.com/x/a.prd", "Garden Secateurs", secateurs) == "B&Q"
