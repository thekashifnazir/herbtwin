"""25 Oct, Kash on rev 00109: the two folds at the foot of the answer read as one block of
text, "hard to parse if reading quickly". Each group gets a coloured label, each factor
its own row, and a list of things a bullet each; the same words, no new claims."""

import re

from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _render
from tests.test_web_indoor_light_ask import ASKS, _indoor


def _photo_read(rec):
    o = rec.observation
    o.water_stress, o.decline, o.leaf_colour, o.soil_surface = 1, 1, "some_yellow", "dry"
    o.symptoms = ["yellow lower leaves", "leaf spots"]
    return rec


def _why(page: str) -> str:
    return page.split('<details class="why fold', 1)[1].split("</details>", 1)[0]


def _went_on(page: str) -> str:
    # its open body, up to the Ref line (the shut title's " · 3 things" is not the body)
    fold = page.split('<details class="evidence fold">', 1)[1].split("</summary>", 1)[1]
    return fold.split('<p class="record">', 1)[0]


def test_each_how_sure_group_has_a_coloured_label(tmp_path):
    why = _why(_render(_full_plan(tmp_path)))
    # the fixture holds a chip of each net effect
    for effect, said in (("raises", "▲ Helped"), ("lowers", "▼ Lowered it"), ("missing", "? Missing"),
                         ("neutral", "· No effect on how sure we are")):  # fmt: skip
        assert f'<p class="fold-label f-{effect}">{said}</p>' in why, said
    # the 624-question line is still the lead, above the groups
    assert why.index('class="small sure-lead"') < why.index('class="fold-label')


def test_each_factor_is_its_own_row_and_a_list_of_reasons_is_bullets(tmp_path):
    why = _why(_render(_full_plan(tmp_path))).replace("&#39;", "'")
    # one reason: beside the name; the colon is for a screen reader, the row shows it
    assert ('<li class="factor"><strong class="f-name">Season</strong><span class="sr-only">: </span>'
            '<span class="f-why">location unknown</span></li>') in why  # fmt: skip
    # two or more: a bullet each, never "; "-joined
    soil = why.split('<strong class="f-name">Soil</strong>', 1)[1].split("</li></ul></li>", 1)[0]
    assert re.findall(r"<li>([^<]+)", soil) == [
        "soil surface not visible",
        "how the soil feels 2 cm down",
    ]
    assert "; " not in why
    # no reasons: the name alone
    assert (
        '<li class="factor"><strong class="f-name">The lead advisor wasn\'t sure</strong></li>'
        in why
    )


def test_what_we_went_on_labels_each_line_and_bullets_the_photo(tmp_path):
    for indoor in (False, True):
        (tmp_path / str(indoor)).mkdir()
        rec = _photo_read(_full_plan(tmp_path / str(indoor)))
        page = _render(_indoor(rec), asks=ASKS) if indoor else _render(rec)
        went = _went_on(page)
        assert '<p class="fold-label went-photo">From the photo</p>' in went
        photo = went.split("From the photo</p>", 1)[1].split("</ul>", 1)[0]
        assert re.findall(r"<li>([^<]+)</li>", photo) == [
            "a little droopy", "a little tired", "leaves some yellow", "soil surface dry",
            "seen: yellow lower leaves, leaf spots",
        ]  # fmt: skip
        assert '<p class="fold-label went-facts">Care facts</p>' in went
        assert " · " not in went and "From the photo:" not in went and "Care facts:" not in went
        assumed = "What we assumed" if indoor else "What the plant model assumes"
        assert f'<summary class="fold-label went-assumed">{assumed}</summary>' in went


def test_the_labels_use_herbtwin_meaning_colours():
    css = style.CSS
    for cls, bg, fg in (("f-raises", "soft", "primary"), ("f-lowers", "clay-bg", "clay"),
                        ("f-missing", "warn-bg", "warn"), ("f-neutral", "muted", "muted-fg")):  # fmt: skip
        assert (
            f".answer-page .fold-label.{cls} {{ background: var(--{bg}); color: var(--{fg}); }}"
            in css
        )
    assert ".answer-page .fold-label { " in css and "font: 700 16px/1.3 var(--sans);" in css
