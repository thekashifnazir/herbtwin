"""Tap the plant you mean, end to end (19 Oct, Kash's walk): a photo of different plants
asks which one, reads the square around the tap, and the whole photo is always an option."""

import io
import json
import re

import httpx
import respx
from fastapi.testclient import TestClient
from PIL import Image

from herbtwin.stages.environment import OPEN_METEO_URL
from tests.fakes import follow
from tests.test_tapping import _photo
from tests.test_web import ADV, OBS, SAMPLE, _client
from tests.test_web_history import _signed_in

MIXED = {
    **OBS,
    "quality_note": "several herbs share the frame",
    "species": [
        {"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.6},
        {"name": "Mentha spicata", "common_name": "spearmint", "confidence": 0.3},
    ],
}
PHOTO = _photo((1600, 1200))


def _upload(c, photo=PHOTO):
    return follow(c, c.post("/analyse", files={"photo": ("m.jpg", photo, "image/jpeg")}))


def _tap_id(page) -> str:
    return re.search(r'action="/taps/([0-9a-f]+)"', page.text).group(1)


@respx.mock
def test_a_photo_of_different_plants_asks_which_one(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED)], [])
    page = _upload(c)
    assert "<h1>Which plant do you mean?</h1>" in page.text
    lead = page.text.split('<p class="lead">', 1)[1].split("</p>", 1)[0]
    # no names: the species list is guesses at one plant, not the plants in the photo
    assert (
        lead
        == "This photo shows more than one plant. Tap the one you want advice for, or use the whole photo."
    )
    assert "spearmint" not in page.text.lower()
    tid = _tap_id(page)
    # the whole photo first, never a gate; the tapped one shows once there is a tap
    form = page.text.split('<div class="actions tap-go">', 1)[1].split("</div>", 1)[0]
    assert form.index("Use the whole photo") < form.index("Use the plant in the box")
    photo = c.get(f"/taps/{tid}/photo")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["cache-control"] == "no-store"
    assert b"GPS" not in photo.content and max(Image.open(io.BytesIO(photo.content)).size) <= 1280


@respx.mock
def test_a_tap_reads_the_square_around_it_and_answers(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    # the crop's own read still says several (it did live): the tap wins
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(MIXED)], [json.dumps(ADV)] * 3)
    tid = _tap_id(_upload(c))
    page = follow(c, c.post(f"/taps/{tid}", data={"fx": "0.25", "fy": "0.5"}))
    assert "Water it." in page.text
    # they chose: said back, never "one of several plants... send a close photo" (live, 19 Oct)
    assert '<p class="note">Answering for the basil you tapped.</p>' in page.text
    assert "one of several plants" not in page.text
    observe = c.app.state.deps.observe_adapter
    assert len(observe.calls) == 2  # the whole photo, then the crop
    # taken once: the same tap again has nothing to read
    again = c.post(f"/taps/{tid}", data={"fx": "0.25", "fy": "0.5"})
    assert again.status_code == 404 and "This photo has expired" in again.text


@respx.mock
def test_the_whole_photo_uses_the_first_read(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED)], [json.dumps(ADV)] * 3)  # one read only
    tid = _tap_id(_upload(c))
    page = follow(c, c.post(f"/taps/{tid}", data={"whole": "1"}))
    assert "Water it." in page.text
    # the next upload of the same photo is asked again, not replayed as "the whole photo"
    c.app.state.deps.observe_adapter.responses.append(json.dumps(MIXED))
    assert "Which plant do you mean?" in _upload(c).text


@respx.mock
def test_one_plant_or_one_crop_is_never_asked(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    # one crop is read one_plant (the pea-bed sample, 3 of 3 on 19 Oct)
    peas = {**OBS, "scene": "one_plant",
            "species": [{"name": "Pisum sativum", "common_name": "pea", "confidence": 0.8}]}  # fmt: skip
    c = _client(tmp_path, [json.dumps(peas)], [json.dumps(ADV)] * 3)
    assert "Which plant do you mean?" not in _upload(c).text


@respx.mock
def test_a_tap_outside_the_photo_can_be_tried_again(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    tid = _tap_id(_upload(c))
    for bad in ({"fx": "", "fy": ""}, {"fx": "1.5", "fy": "0.5"}, {"fx": "nan", "fy": "0.5"}):
        r = c.post(f"/taps/{tid}", data=bad)
        assert r.status_code == 400 and "Tap on the plant you mean" in r.text, bad
    assert "Water it." in follow(c, c.post(f"/taps/{tid}", data={"fx": "0.5", "fy": "0.5"})).text


@respx.mock
def test_the_tap_page_is_only_for_the_browser_that_sent_the_photo(tmp_path):
    from tests.test_web_keep import _app

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, deps, *_ = _app(tmp_path)  # accounts on and the claim secret set, as live
    deps.observe_adapter.responses[:] = [json.dumps(MIXED)]
    c = TestClient(app)
    tid = _tap_id(_upload(c))
    other = TestClient(app)  # another browser: no claim cookie
    assert other.get(f"/taps/{tid}").status_code == 404
    assert other.get(f"/taps/{tid}/photo").status_code == 404
    assert other.post(f"/taps/{tid}", data={"whole": "1"}).status_code == 404
    assert c.get(f"/taps/{tid}").status_code == 200  # still there for its own browser


@respx.mock
def test_signed_in_the_crop_is_the_plant_kept_and_chosen(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    page = follow(c, r)
    assert "Which plant do you mean?" in page.text
    store = hist.for_user("u1")
    assert store.list_plants() == []  # nothing kept before the tap
    page = follow(c, c.post(f"/taps/{_tap_id(page)}", data={"fx": "0.25", "fy": "0.5"}))
    assert "Water it." in page.text
    [plant] = store.list_plants()
    assert plant.species == "ocimum basilicum"  # the crop's read, not the mixed one
    [stored] = store.answers_for(plant.id)
    kept = Image.open(io.BytesIO(hist.photos[stored.photo_path]))
    assert kept.size[0] == kept.size[1] == 640  # the square around the tap


@respx.mock
def test_signed_in_the_whole_photo_uses_the_first_read_and_keeps_the_photo(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED)], [json.dumps(ADV)] * 3)  # one read
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    page = follow(c, c.post(f"/taps/{_tap_id(follow(c, r))}", data={"whole": "1"}))
    assert "Water it." in page.text
    store = hist.for_user("u1")
    [plant] = store.list_plants()
    [stored] = store.answers_for(plant.id)
    kept = hist.photos[stored.photo_path]
    assert Image.open(io.BytesIO(kept)).size == (1600, 1200) and b"GPS" not in kept


@respx.mock
def test_a_signed_in_tap_is_not_another_accounts(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, auth = _signed_in(tmp_path, [json.dumps(MIXED)], [])
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    other = TestClient(c.app)
    other.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u2", "b@b.co"), "type": "email"},
        follow_redirects=False,
    )
    assert other.get(f"/taps/{tid}").status_code == 404
    assert other.get(f"/taps/{tid}/photo").status_code == 404
    assert other.post(f"/taps/{tid}", data={"whole": "1"}).status_code == 404
    assert c.get(f"/taps/{tid}").status_code == 200


@respx.mock
def test_a_png_photo_is_shown_and_its_crop_read_as_a_jpeg(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    buf = io.BytesIO()
    Image.new("RGBA", (1600, 1200), (0, 128, 0, 200)).save(buf, "PNG")
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("m.png", buf.getvalue(), "image/png")}))
    tid = _tap_id(page)
    shown = c.get(f"/taps/{tid}/photo")
    assert shown.status_code == 200 and shown.content[:2] == b"\xff\xd8"
    done = follow(c, c.post(f"/taps/{tid}", data={"fx": "0.5", "fy": "0.5"}))
    assert "Water it." in done.text


@respx.mock
def test_a_tap_over_the_daily_limit_is_refused_and_the_photo_kept(tmp_path):
    # integrator's #275 review: the crop is a second paid read, so it counts against the
    # limit; refused, the photo stays for a later tap and nothing is read
    from herbtwin.usage import MemoryUsage
    from tests.test_web_caps import BUSY
    from tests.test_web_caps import _client as capped

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = capped(tmp_path, {"HERBTWIN_DAILY_READS": "1"}, usage=MemoryUsage(), reads=0)
    c.app.state.deps.observe_adapter.responses[:] = [json.dumps(MIXED), json.dumps(OBS)]
    tid = _tap_id(_upload(c))  # the day's one read
    r = c.post(f"/taps/{tid}", data={"fx": "0.5", "fy": "0.5"})
    assert r.status_code == 429 and BUSY in r.text and 'id="next"' not in r.text
    assert c.get(f"/taps/{tid}").status_code == 200  # still there to tap later
    assert len(c.app.state.deps.observe_adapter.calls) == 1  # no second read


def test_a_plant_can_be_chosen_by_keyboard(tmp_path):
    # integrator's #275 review: nine focusable regions, each marking its centre as a tap would
    from herbtwin.web import style
    from herbtwin.web.app import TEMPLATES

    page = TEMPLATES.get_template("tap_plant.html").render(
        request=None, tap_id="ab", share=0.33, least=0.2, person=None
    )
    assert 'cell.setAttribute("aria-label", `The plant at the ${where} of the photo`);' in page
    assert "choose((i % 3 + 0.5) / 3, (Math.floor(i / 3) + 0.5) / 3)" in page
    rule = style.CSS.split(".tap-page .tap-cell {", 1)[1].split("}", 1)[0]
    assert "pointer-events: none" in rule  # a pointer taps the exact spot underneath


# 21 Oct, Kash's test: the fixed box caught three pots; "maybe we ask them to size box
# themselves". The box now starts at a third of the photo and is moved and sized by hand.


def _tap_page(**over):
    from herbtwin.web.app import TEMPLATES

    ctx = {"request": None, "tap_id": "ab", "share": 0.33, "least": 0.2, "person": None}
    return TEMPLATES.get_template("tap_plant.html").render(**{**ctx, **over})


@respx.mock
def test_the_page_starts_the_box_at_a_third_and_lets_it_go_down_to_a_fifth(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(MIXED)], [])
    page = _upload(c, _photo((4000, 3000)))  # a phone photo: a third is above the minimum
    assert 'data-share="0.3300" data-least="0.2000"' in page.text  # down to a fifth
    page = _upload(c)  # 1600 x 1200: a fifth is 240 px, still above the 200 px floor
    assert 'data-share="0.3300" data-least="0.2000"' in page.text


@respx.mock
def test_a_sized_box_is_the_square_read(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    big = _photo((4000, 3000))
    r = c.post("/analyse", files={"photo": ("m.jpg", big, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    page = follow(c, c.post(f"/taps/{tid}", data={"fx": "0.2", "fy": "0.5", "fs": "0.25"}))
    assert "Water it." in page.text
    [plant] = hist.for_user("u1").list_plants()
    [stored] = hist.for_user("u1").answers_for(plant.id)
    kept = Image.open(io.BytesIO(hist.photos[stored.photo_path]))
    assert kept.size == (750, 750)  # a quarter of the short side, as the box was drawn


@respx.mock
def test_a_box_round_one_pot_in_a_small_photo_is_read_made_bigger(tmp_path):
    # Kash, 21 Oct: the box must hold ONE pot. A fifth of a 1600 x 1200 photo is 240 px,
    # made 640 across for the read
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    page = follow(c, c.post(f"/taps/{tid}", data={"fx": "0.1", "fy": "0.5", "fs": "0.2"}))
    assert "Water it." in page.text
    [plant] = hist.for_user("u1").list_plants()
    [stored] = hist.for_user("u1").answers_for(plant.id)
    kept = Image.open(io.BytesIO(hist.photos[stored.photo_path]))
    assert kept.size == (640, 640)


@respx.mock
def test_a_box_of_no_size_or_bigger_than_the_photo_is_refused_and_the_photo_kept(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    tid = _tap_id(_upload(c))
    for fs in ("0", "-0.2", "1.01", "nan", "inf", "a third"):
        r = c.post(f"/taps/{tid}", data={"fx": "0.5", "fy": "0.5", "fs": fs})
        assert r.status_code == 400 and "Tap on the plant you mean" in r.text, fs
    assert len(c.app.state.deps.observe_adapter.calls) == 1  # nothing read for them
    done = follow(c, c.post(f"/taps/{tid}", data={"fx": "0.5", "fy": "0.5", "fs": "1"}))
    assert "Water it." in done.text  # the whole short side is a box too


def test_the_box_is_moved_and_sized_by_pointer_and_by_keyboard():
    from herbtwin.web import style

    page = _tap_page()
    # the page sends the box as a rectangle; the square's fields are gone from it
    for name in ("x", "y", "w", "h"):
        assert f'<input type="hidden" name="{name}" id="box-{name}">' in page, name
    assert 'name="fs"' not in page and 'name="fx"' not in page
    mark = page.split('<span class="tap-mark"', 1)[1].split("</div>", 1)[0]
    assert 'tabindex="0"' in mark and 'aria-label="The box we\'ll read"' in mark
    corners = re.findall(r'data-corner="(\w+)"', mark)
    assert corners == ["nw", "ne", "sw", "se"]
    edges = re.findall(r'<span class="tap-edge" data-edge="(\w)" aria-hidden="true">', mark)
    assert edges == ["n", "e", "s", "w"]
    assert (
        "Drag to move, drag an edge or a corner to resize. We'll read the plant in the box." in page
    )
    # Pointer Events, so a finger, a pen and a mouse all drag it; captured, so a fast drag
    # off the box keeps hold
    for event in ("pointerdown", "pointermove", "pointerup", "pointercancel"):
        assert f'"{event}"' in page, event
    assert "setPointerCapture" in page
    assert "ArrowLeft: [-1, 0]" in page and "e.shiftKey" in page
    # Shift sizes: left and right the width, up and down the height. Never Alt: Alt+Left and
    # Alt+Right are the browser's Back and Forward on Windows, so Alt passes to the browser
    assert "const dw = way[0] * STEP * r.width, dh = -way[1] * STEP * r.height;" in page
    assert "if (!way || !at || e.altKey || e.ctrlKey || e.metaKey) return;" in page
    assert "e.altKey ?" not in page and "Alt (Option" not in page
    rule = style.CSS.split(".tap-page .tap-mark {", 1)[1].split("}", 1)[0]
    assert "touch-action: none" in rule  # a drag on the box never scrolls the page
    assert ".tap-page .tap-mark:focus-visible" in style.CSS
    photo = style.CSS.split(".tap-page .tap-photo img {", 1)[1].split("}", 1)[0]
    assert "touch-action" not in photo  # the rest of the photo still scrolls on a phone


def test_the_box_never_animates_and_its_caption_has_room_kept():
    from herbtwin.web.style import STATIC

    sheet = (STATIC / "pages" / "tap.css").read_text(encoding="utf-8")
    rules = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
    assert "transition" not in rules and "animation" not in rules
    said = rules.split(".tap-page .tap-said {", 1)[1].split("}", 1)[0]
    assert "min-height: 2lh" in said  # two lines: the caption arrives without a shift
    under = rules.split(".tap-page .tap-under {", 1)[1].split("}", 1)[0]
    assert "min-height: 48px" in under  # and the row the size buttons arrive in


def test_without_a_script_the_whole_photo_still_works():
    # the box and the buttons for it are hidden until the script places them; the whole
    # photo is a plain submit
    page = _tap_page()
    assert '<button type="submit" name="whole" value="1" id="tap-whole">' in page
    assert 'id="tap-go" hidden>Use the plant in the box</button>' in page
    assert '<span class="tap-mark" id="tap-mark" hidden' in page
    assert '<div class="tap-size" id="tap-size" hidden>' in page


# 22 Oct, for a phone (the owner tests on one): bigger corners, sizing by taps alone, and
# arrow keys a screen reader hands to the page


def test_the_corners_are_big_enough_for_a_finger():
    from herbtwin.web.style import STATIC

    sheet = (STATIC / "pages" / "tap.css").read_text(encoding="utf-8")
    corner = sheet.split(".tap-page .tap-corner {", 1)[1].split("}", 1)[0]
    assert "width: 28px; height: 28px" in corner  # drawn at 28px
    # the hold: the box's own reach, 16px past its 3px border, plus 28px inside = 44px
    hold = sheet.split(".tap-page .tap-mark::before {", 1)[1].split("}", 1)[0]
    assert "inset: -19px" in hold
    page = _tap_page()
    assert "const GRIP_IN = 28;" in page
    # the edge or corner is picked from where the pointer is, and a small box's middle
    # still moves
    assert "handle: handleAt(e, r)" in page
    assert 'if (Math.abs(px - b.w / 2) < mx && Math.abs(py - b.h / 2) < my) return "";' in page
    # the box sits outside the photo's clip, so a corner at the photo's edge is not cut off
    frame = page.split('<div class="tap-frame">', 1)[1].split("</div>", 1)[0]
    assert 'id="tap-shade"' in frame and "tap-mark" not in frame
    clip = sheet.split(".tap-page .tap-frame {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden" in clip and ":has(.tap-mark" not in sheet


def test_the_box_can_be_sized_by_taps_alone():
    # WCAG 2.5.7: a way to size the box with no drag, a tenth at a time, within its limits
    page = _tap_page()
    size = page.split('<div class="tap-size" id="tap-size" hidden>', 1)[1].split("</div>", 1)[0]
    assert (
        '<button type="button" class="quiet" id="tap-smaller" aria-label="Smaller box">−</button>'
        in size
    )
    assert (
        '<button type="button" class="quiet" id="tap-bigger" aria-label="Bigger box">+</button>'
        in size
    )
    assert "const SIZE_STEP = 0.1;" in page
    # both sides at once, the shape kept
    assert 'smaller.addEventListener("click", () => rescale(-1));' in page
    assert 'bigger.addEventListener("click", () => rescale(1));' in page
    # at a limit a button says so but keeps the focus (never `disabled`)
    assert (
        'smaller.setAttribute("aria-disabled", String(same(fit(scaled(f, -1, r), r), f)));' in page
    )
    assert 'bigger.setAttribute("aria-disabled", String(same(fit(scaled(f, 1, r), r), f)));' in page
    assert '<p class="vh" id="tap-size-said" aria-live="polite"></p>' in page
    assert "The box is ${pct(at.w)}% of the photo wide and ${pct(at.h)}% high." in page


def test_a_screen_reader_hands_the_arrow_keys_to_the_box_and_says_how():
    page = _tap_page()
    mark = page.split('<span class="tap-mark"', 1)[1].split(">", 1)[0]
    assert 'role="application"' in mark and 'aria-describedby="tap-box-help"' in mark
    assert 'role="group"' not in page
    help_text = page.split('<p class="vh" id="tap-box-help">', 1)[1].split("</p>", 1)[0]
    assert help_text == (
        "Arrow keys move the box. Shift with Left or Right changes its width, and Shift with "
        "Up or Down changes its height: Right and Up make it bigger, Left and Down smaller. "
        "The Smaller box and Bigger box buttons under the photo resize it too."
    )
    assert page.count('role="application"') == 1  # sparingly: the box alone


# 21 Oct, the owner: "should be able to reduce box size with vertical and horizontal, not
# just corners". The box is a rectangle, sized from its edges as well as its corners.


@respx.mock
def test_a_drawn_rectangle_is_the_crop_read(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    big = _photo((4000, 3000))
    r = c.post("/analyse", files={"photo": ("m.jpg", big, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    box = {"x": "0.1", "y": "0.2", "w": "0.2", "h": "0.5"}  # one tall pot: 800 x 1500 px
    page = follow(c, c.post(f"/taps/{tid}", data=box))
    assert "Water it." in page.text
    [plant] = hist.for_user("u1").list_plants()
    [stored] = hist.for_user("u1").answers_for(plant.id)
    kept = Image.open(io.BytesIO(hist.photos[stored.photo_path]))
    assert kept.size == (800, 1500)


@respx.mock
def test_a_small_rectangle_is_read_made_640_on_its_short_side(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    box = {"x": "0.05", "y": "0.1", "w": "0.15", "h": "0.4"}  # 240 x 480 of 1600 x 1200
    assert "Water it." in follow(c, c.post(f"/taps/{tid}", data=box)).text
    [plant] = hist.for_user("u1").list_plants()
    [stored] = hist.for_user("u1").answers_for(plant.id)
    assert Image.open(io.BytesIO(hist.photos[stored.photo_path])).size == (640, 1280)


@respx.mock
def test_a_rectangle_of_no_size_or_out_of_the_photo_is_refused_and_the_photo_kept(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    tid = _tap_id(_upload(c))
    ok = {"x": "0.2", "y": "0.2", "w": "0.3", "h": "0.4"}
    for bad in (
        {"w": "0"},
        {"h": "-0.2"},
        {"w": "1.01"},
        {"x": "nan"},
        {"h": "inf"},
        {"x": "0.8"},  # its right side past the photo
        {"y": "0.7"},  # its bottom past the photo
        {"w": "a third"},
        {"h": ""},  # half a rectangle is not a square
    ):
        r = c.post(f"/taps/{tid}", data={**ok, **bad})
        assert r.status_code == 400 and "Tap on the plant you mean" in r.text, bad
    assert len(c.app.state.deps.observe_adapter.calls) == 1  # nothing read for them
    assert "Water it." in follow(c, c.post(f"/taps/{tid}", data=ok)).text


@respx.mock
def test_a_page_from_before_the_edges_still_sends_its_square(tmp_path):
    # a tap page loaded before this change posts fx, fy and fs: it is still the square read
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, _ = _signed_in(tmp_path, [json.dumps(MIXED), json.dumps(OBS)], [json.dumps(ADV)] * 3)
    big = _photo((4000, 3000))
    r = c.post("/analyse", files={"photo": ("m.jpg", big, "image/jpeg")}, data={"place": ""})
    tid = _tap_id(follow(c, r))
    old = {"fx": "0.2", "fy": "0.5", "fs": "0.25", "x": "", "y": "", "w": "", "h": ""}
    assert "Water it." in follow(c, c.post(f"/taps/{tid}", data=old)).text
    [plant] = hist.for_user("u1").list_plants()
    [stored] = hist.for_user("u1").answers_for(plant.id)
    assert Image.open(io.BytesIO(hist.photos[stored.photo_path])).size == (750, 750)


def test_the_box_is_kept_within_one_to_three_and_its_edges_have_a_finger_sized_hold():
    from herbtwin.web.style import STATIC

    page = _tap_page()
    assert "const RATIO = 3;" in page
    assert "w = Math.min(w, RATIO * h); h = Math.min(h, RATIO * w);" in page
    # the hold reaches 16px past each edge and 28px into it: 44px across, for an edge too
    sheet = (STATIC / "pages" / "tap.css").read_text(encoding="utf-8")
    hold = sheet.split(".tap-page .tap-mark::before {", 1)[1].split("}", 1)[0]
    assert "inset: -19px" in hold
    edge = sheet.split(".tap-page .tap-edge {", 1)[1].split("}", 1)[0]
    assert "pointer-events: none" in edge  # drawn only: the hold is the box's own
    for e, cursor in (("n", "ns-resize"), ("e", "ew-resize")):
        assert f'{e}: "{cursor}"' in page


@respx.mock
def test_the_wait_says_there_are_several_plants_before_naming_any(tmp_path):
    # 22 Oct phone walk: the wait said "Found geranium (not sure)", then "One question
    # first: Tap your plant". Several plants are said first, and no plant is named (nor its
    # month's normal shown) before the person picks; the same photo of one plant still is
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    where = {"lat": "52.6", "lon": "-1.1"}  # outdoors in the UK: the season card would show
    pages = {}
    for kind, read in (("mixed", MIXED), ("one", OBS)):
        (tmp_path / kind).mkdir()
        c = _client(tmp_path / kind, [json.dumps(read)], [json.dumps(ADV)] * 3)
        files = {"photo": ("m.jpg", PHOTO, "image/jpeg")}
        pages[kind] = c.post("/analyse", files=files, data=where).text
    mixed, one = pages["mixed"], pages["one"]
    assert "<li>Found basil" in one and "Normal for basil" in one  # the control
    assert "<li>We can see more than one plant: you&#x27;ll tap the one you mean next" in mixed
    assert "Found" not in mixed and "Normal for" not in mixed
    # nor its care facts (#491): the card would name the guessed plant before the tap
    assert '<h2 id="fact-care-h">What basil needs</h2>' in one and "fact-care" not in mixed
    assert "basil" not in mixed.split('<div class="ready"', 1)[0].lower()
    assert '<a id="next" href="/taps/' in mixed


@respx.mock
def test_signed_in_the_wait_says_several_plants_too(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, _ = _signed_in(tmp_path, [json.dumps(MIXED)], [])
    r = c.post("/analyse", files={"photo": ("m.jpg", PHOTO, "image/jpeg")}, data={"place": ""})
    assert "<li>We can see more than one plant" in r.text and "Found" not in r.text
