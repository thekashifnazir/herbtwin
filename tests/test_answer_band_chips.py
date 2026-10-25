"""The answer page's green band, clear at a glance (21 Oct, Kash at rev 00049: the band
text was "hard to see" and "a lot of text not clear to the eye"). Where it grows, the date
and the place are a row of chips; "place unknown" is a friendly ask with a town box on the
band; the indoors/outdoors switch says what it does. The notes that carry news still show."""

import re
from datetime import datetime
from pathlib import Path

from herbtwin.schemas import HeadingTap, LightReading, Location, Told
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

STATIC = Path(__file__).parents[1] / "src/herbtwin/web/static"
SITE = (STATIC / "herbtwin.css").read_text()
CSS = (STATIC / "pages/answer.css").read_text()
LONDON = Location(lat=51.5, lon=-0.12, source="home", label="London")
ASK = "We don't know where this is: add a town for weather-checked advice."


def _band(page: str) -> str:
    return page.split('<div class="page-band">', 1)[1].split('<div class="answer-cols', 1)[0]


def _chips(page: str) -> list[str]:
    where = page.split('<p class="where">', 1)[1].split("</p>", 1)[0]
    return re.findall(r'<span class="chip[^"]*">([^<]*)</span>', where)


def _day(rec) -> str:
    return f"{rec.taken_at.day} {rec.taken_at:%b}"


def test_where_and_when_are_chips_in_plain_words(tmp_path):
    rec = _unsure_record(tmp_path)
    obs = rec.observation
    rec.location = LONDON
    obs.setting, obs.container = "outdoor", "pot"
    assert _chips(_render(rec)) == ["Outdoors", "In a container", _day(rec), "London"]
    obs.container = "ground"
    assert _chips(_render(rec)) == ["Outdoors", "In the ground", _day(rec), "London"]
    obs.scene = "bed_or_border"
    assert _chips(_render(rec))[1] == "In a bed or border"
    # indoors there is no ground or border (19 Oct judge walk of #269)
    obs.setting, obs.scene = "indoor", None
    assert _chips(_render(rec)) == ["Indoors", _day(rec), "London"]
    obs.container = "pot"
    assert _chips(_render(rec)) == ["Indoors", "In a container", _day(rec), "London"]
    # told: the person's word wins and says so
    rec.told = Told(setting="indoor")
    assert _chips(_render(rec))[0] == "Indoors (you said)"
    # not known either way: no setting chip, the switch asks instead
    rec.told, obs.setting = None, "unknown"
    assert _chips(_render(rec)) == ["In a container", _day(rec), "London"]


def test_the_chips_never_say_place_unknown(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    page = _render(rec)
    assert "place unknown" not in page.lower() and ASK in page
    # indoors the place changes nothing, so it says nothing about it
    rec.observation.setting = "indoor"
    page = _render(rec)
    assert "place unknown" not in page.lower() and ASK not in page


def test_no_looks_like_line_repeats_the_setting_chip(tmp_path):
    rec = _unsure_record(tmp_path)
    for setting in ("outdoor", "indoor"):
        rec.observation.setting = setting
        band = _band(_render(rec))
        assert "Looks like outdoors" not in band and "Looks like indoors" not in band
        assert "Wrong? Switch" not in band


def test_the_switch_says_what_it_does(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert 'name="setting" value="indoor"' in switch
    # a told setting is not carried as well: the switch posts exactly one (review)
    rec.told = Told(setting="outdoor", soil_feel="wet")
    told = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert told.count('name="setting"') == 1 and 'name="setting" value="indoor"' in told
    rec.told = None
    assert ">Redo for indoors</button>" in switch
    rec.observation.setting = "indoor"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert 'name="setting" value="outdoor"' in switch
    assert ">Redo for outdoors</button>" in switch
    # a small link now (23 Oct answer-page critique, 1): still a button posting the form
    assert 'class="switch as-pill"' in switch and 'class="link"' not in switch


def test_the_place_ask_shows_only_outdoors_with_no_place_and_an_answer(tmp_path):
    rec = _unsure_record(tmp_path)
    for setting in ("outdoor", "unknown"):
        rec.observation.setting = setting
        assert ASK in _band(_render(rec)), setting
    rec.observation.setting = "indoor"
    assert ASK not in _render(rec)
    rec.observation.setting = "outdoor"
    rec.location = LONDON
    assert ASK not in _render(rec)
    rec.location, rec.answer = None, None
    assert ASK not in _render(rec)


def test_the_place_ask_posts_the_town_with_what_was_told(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    rec.told = Told(
        soil_feel="wet", question="Is it ok?", heading=HeadingTap(direction="S"), setting="outdoor"
    )
    page = _render(rec)
    form = page.split('<form class="place-ask"', 1)[1].split("</form>", 1)[0]
    assert f'method="post" action="/answers/{rec.record_id}/refine"' in form
    assert re.search(r'<input id="band-place" type="text" name="place" maxlength="80"', form)
    assert f'<label for="band-place">{ASK}</label>' in form.replace("&#39;", "'")
    for kept in (
        '<input type="hidden" name="soil_feel" value="wet">',
        '<input type="hidden" name="question" value="Is it ok?">',
        '<input type="hidden" name="direction" value="S">',
        # the setting the person gave rides along too, so adding a town never undoes it
        '<input type="hidden" name="setting" value="outdoor">',
    ):
        assert kept in form, kept
    # green on the band since 24 Oct: the card's asks are outlined (Toloka study), so the
    # town is the page's one green press (#364 review: never two); a retake still leads
    assert '<button type="submit" class="button primary">Check the advice</button>' in form
    assert '<a class="button quiet" href="#refine">Make this surer' in page


def test_both_band_forms_say_they_started_and_reset_after_back(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    band = _band(_render(rec))
    script = band.split('<form class="place-ask"', 1)[1].split("</script>", 1)[0]
    assert 'querySelectorAll("form.setting-switch, form.place-ask")' in script
    assert '"Checking the advice…"' in script and 'addEventListener("pageshow"' in script


def test_the_main_card_does_not_ask_for_the_place_again(tmp_path):
    # the ask is said once (Kash disliked repeats): the band's town box, not a second button
    # in the card that jumps to a third box in the fold
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    page = _render(rec, asks=["question"])  # the place was the one quick thing to answer
    assert page.count(ASK.replace("'", "&#39;")) + page.count(ASK) == 1
    assert "Add where it is" not in page
    main = page.split('class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert "Answer the <a" not in main and "Make this surer" not in main
    # the fold stays shut: nothing in it is what the card points at now
    assert '<details class="tell-more">' in page
    # the band's town box is the only place box: the fold does not ask it again (review)
    assert 'placeholder="UK town or postcode"' not in page
    # other quick questions still get their button, counted without the place
    assert "Make this surer: answer 2 quick questions</a>" in _render(rec)


def test_the_fold_asks_no_place_while_the_band_does(tmp_path):
    # review of 903e7b4a: the fold still opened with the place sentence and its "Where is
    # it?" box while the card said "answer 2 quick questions"
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    fold = _render(rec).split('<details class="tell-more"', 1)[1].split("</details>", 1)[0]
    assert 'name="place"' not in fold and "Where is it?" not in fold
    assert rec.answer.tell_me not in fold.replace("&#39;", "'")
    assert 'name="soil_feel"' in fold  # the other questions stay
    # indoors the band asks nothing, so the fold is as before
    rec.observation.setting = "indoor"
    fold = _render(rec).split('<details class="tell-more"', 1)[1].split("</details>", 1)[0]
    assert '<div class="tray warn">' in fold and 'name="place"' in fold


def test_only_the_band_place_ask_does_not_lift_an_empty_fold(tmp_path):
    # review of 903e7b4a: on a phone ask-up lifted "Tell us more" under the card when the
    # place, now asked on the band, was its only quick question
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    assert 'class="answer-cols ask-up"' not in _render(rec, asks=["question"])
    assert 'class="answer-cols ask-up"' in _render(rec)  # soil and watering still to answer
    rec.observation.setting = "indoor"
    assert 'class="answer-cols ask-up"' in _render(rec, asks=["question"])


def test_the_notes_that_carry_news_still_show_on_the_band(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    rec.notes = ["Answering for the mint you tapped."]
    rec.light = LightReading(
        fraction=0.4, now="bright_shade", local_time=datetime(2026, 10, 4, 14, 5), lux=1,
        sky_wm2=1, route="shutter",
    )  # fmt: skip
    band = _band(_render(rec, kept=True))
    assert '<p class="note">Answering for the mint you tapped.</p>' in band
    assert '<p class="note light-read">Light at 14:05: part shade' in band
    assert "<strong>Kept in My plants.</strong>" in band
    assert '<form class="note keep-form"' in _band(_render(rec, keep_as="a@example.com"))
    elsewhere = _band(_render(rec, keep_elsewhere="Kept only in the other browser."))
    assert '<p class="note">Kept only in the other browser.</p>' in elsewhere
    rec.observation.setting = "indoor"
    # indoors is said once, in the card's indoor line, not on the band (25 Oct, Kash)
    assert "indoor-note" not in _band(_render(rec))
    assert 'class="note indoor-light"' in _render(rec)
    (tmp_path / "x").mkdir()
    plan = _full_plan(tmp_path / "x")
    plan.observation.setting, plan.location, plan.environment = "outdoor", LONDON, None
    assert 'class="note no-forecast"' in _band(_render(plan))


def _tokens(scheme: str) -> dict[str, str]:
    """The band's colour tokens, light or dark, as hex."""
    block = (
        SITE.split(":root {", 1)[1]
        if scheme == "light"
        else SITE.split("@media (prefers-color-scheme: dark) {\n  :root {", 1)[1]
    )
    block = block.split("}", 1)[0]
    return dict(re.findall(r"--(band(?:-[a-z]+)?|lime(?:-fg)?):\s*(#[0-9A-Fa-f]{6})", block))


def _lum(rgb: tuple[float, float, float]) -> float:
    c = [x / 255 for x in rgb]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i : i + 2], 16) for i in (1, 3, 5))


def _contrast(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_chips_are_clear_on_the_band_green_in_both_schemes():
    rule = next(
        b for at, s, b in _rules(CSS) if s == ".answer-page .page-band .where .chip" and not at
    )
    assert "color: var(--band-fg)" in rule
    mix = re.search(
        r"background: color-mix\(in srgb, var\(--band-fg\) (\d+)%, var\(--band\)\)", rule
    )
    assert mix, rule
    share = int(mix.group(1)) / 100
    for scheme in ("light", "dark"):
        t = _tokens(scheme)
        fg, band = _rgb(t["band-fg"]), _rgb(t["band"])
        chip = tuple(f * share + b * (1 - share) for f, b in zip(fg, band, strict=True))
        assert _contrast(fg, chip) >= 6, scheme  # "6:1 or better", as the sheet says
        # the switch and the town ask's words are the band's white on its green
        assert _contrast(fg, band) >= 4.5, scheme
        # the band's quiet note lines
        assert _contrast(_rgb(t["band-muted"]), band) >= 4.5, scheme
    where = next(b for at, s, b in _rules(CSS) if s == ".answer-page .page-band .where" and not at)
    assert "flex-wrap: wrap" in where  # a phone wraps the row, never scrolls it


def test_the_band_forms_have_44px_tap_targets():
    rules = {s: b for at, s, b in _rules(CSS) if not at}
    switch = rules[".answer-page .page-band .setting-switch .switch"]
    assert int(re.search(r"min-height: (\d+)px", switch)[1]) >= 44
    row = rules[".answer-page .page-band .place-ask .place-row"]
    assert "flex-wrap: wrap" in row
    assert "min-height: 44px" in rules[".answer-page .page-band .place-ask input"]


def test_the_kept_note_button_reads_on_the_green():
    # "Add my photo" took the paper's dark words onto the band; it is the band's outline now
    rule = next(
        b for at, s, b in _rules(CSS) if s == ".answer-page .page-band .kept button" and not at
    )
    assert "color: var(--band-fg)" in rule and "var(--band-line)" in rule


def test_the_town_ask_and_other_questions_leave_one_green_button(tmp_path):
    # #364 review: no place outdoors and other questions open gave the band's button and the
    # card's "Make this surer" both as primary
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    page = _render(rec)  # _render asks soil_feel and last_watered too
    assert 'class="place-ask"' in page and "Make this surer: answer 2 quick questions" in page
    # one green button above the fold (the fold's own "Check the advice again" is its panel's)
    top = page.split('id="chat"', 1)[0]
    assert len(re.findall(r'class="[^"]*\bprimary\b', top)) == 1


def test_the_town_ask_alone_is_the_one_green_button(tmp_path):
    # #364 review: with the place the only question the card shows no button, and the band's
    # outlined one left the page with no green button at all
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    page = _render(rec, asks=["question"])
    top = page.split('id="chat"', 1)[0]
    assert re.findall(r'class="([^"]*\bprimary\b[^"]*)"', top) == ["button primary"]
    assert '<button type="submit" class="button primary">Check the advice</button>' in _band(page)
