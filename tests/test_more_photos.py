"""Up to three photos of the same plant (21 Oct, a gardener tester: "if you want a more
detailed answer, give me more photos"). One read, one model call, all the photos in it."""

import io
import json
from types import SimpleNamespace

import httpx
import pytest
import respx
from PIL import Image

from herbtwin.adapters.base import AdapterError, ModelAdapter
from herbtwin.adapters.mock import OVERRUN, MockAdapter
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.stages.observe import (
    MORE_PHOTOS,
    OBSERVE_MAX_TOKENS,
    OBSERVE_MORE_MAX_TOKENS,
    ObserveError,
    observe,
)
from herbtwin.web import progress
from herbtwin.where import MODEL_LONG_SIDE, exif_gps, for_model, resolve_location
from tests.fakes import follow
from tests.test_observe import GOOD
from tests.test_web import ADV, JPEG, OBS, PNG, SAMPLE, _client
from tests.test_web_accounts import _accounts_client, _sign_in
from tests.test_where import LONDON, _jpeg


class OneImageOnly(MockAdapter):
    """A provider that takes one image per call, like the CLI adapters."""

    complete_with_images = ModelAdapter.complete_with_images


class Recording(MockAdapter):
    """Keeps the images each call was given."""

    def __init__(self, responses):
        super().__init__(responses)
        self.images: list[list[tuple[bytes, str]]] = []

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        self.images.append([(image, mime)])
        return super().complete_with_image(system, user, image, mime, schema, max_tokens=max_tokens)

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        self.images.append(list(images))
        return super().complete_with_images(system, user, images, schema, max_tokens=max_tokens)


# ---------- the read: one call with every photo ----------


def test_more_photos_go_to_the_photo_model_in_one_call():
    adapter = MockAdapter([json.dumps(GOOD)])
    more = [(b"\xff\xd8" + b"l" * 6, "image/jpeg"), (b"\x89PNG" + b"s" * 4, "image/png")]
    obs = observe(adapter, b"\xff\xd8" + b"m" * 8, "image/jpeg", more=more)
    assert obs.species[0].common_name == "basil"
    assert len(adapter.calls) == 1 and adapter.calls[0]["kind"] == "images"
    prompt = adapter.calls[0]["prompt"]
    assert prompt.count("[image ") == 3
    # the main photo first, then the closer looks, in the order they were picked
    assert prompt.index("image/jpeg 10 bytes") < prompt.index("image/jpeg 8 bytes")
    assert prompt.index("image/jpeg 8 bytes") < prompt.index("image/png 8 bytes")
    assert MORE_PHOTOS.format(n=3) in prompt
    assert "looking at one photo" not in prompt and "looking at photos of" in prompt


def test_one_photo_reads_exactly_as_before():
    adapter = MockAdapter([json.dumps(GOOD)])
    observe(adapter, b"\xff\xd8", "image/jpeg")
    assert [c["kind"] for c in adapter.calls] == ["image"]
    assert "photos of the same plant" not in adapter.calls[0]["prompt"]
    assert "looking at one photo of" in adapter.calls[0]["prompt"]


def test_more_photos_keep_the_repair_and_the_schema():
    adapter = MockAdapter(["Looks like basil.", json.dumps(GOOD)])
    obs = observe(adapter, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert obs.water_stress == 2
    assert [c["kind"] for c in adapter.calls] == ["images", "images"]
    assert "Looks like basil." in adapter.calls[1]["prompt"]


def test_a_cut_off_reply_with_more_photos_is_repaired_not_a_dead_end():
    adapter = MockAdapter([OVERRUN, json.dumps(GOOD)])
    obs = observe(adapter, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert obs.species[0].name == "Ocimum basilicum" and len(adapter.calls) == 2


def test_more_photos_get_more_room_to_answer():
    adapter = MockAdapter([json.dumps(GOOD)])
    observe(adapter, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert adapter.calls[0]["max_tokens"] == OBSERVE_MORE_MAX_TOKENS > OBSERVE_MAX_TOKENS
    one = MockAdapter([json.dumps(GOOD)])
    observe(one, b"\xff\xd8", "image/jpeg")
    assert one.calls[0]["max_tokens"] == OBSERVE_MAX_TOKENS  # one photo: as before


def test_a_read_of_several_cut_off_twice_falls_back_to_the_main_photo():
    adapter = MockAdapter([OVERRUN, OVERRUN, json.dumps(GOOD)])
    obs = observe(adapter, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert obs.species[0].common_name == "basil"
    assert [c["kind"] for c in adapter.calls] == ["images", "images", "image"]


def test_a_refused_call_with_several_photos_falls_back_to_the_main_photo():
    class RefusesSeveral(MockAdapter):
        def complete_with_images(self, *a, **kw):
            raise AdapterError("413 request too large")

    adapter = RefusesSeveral([json.dumps(GOOD)])
    obs = observe(adapter, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert obs.is_plant and [c["kind"] for c in adapter.calls] == ["image"]


def test_a_backup_model_reads_all_the_photos_before_the_main_one_alone():
    first = MockAdapter([OVERRUN, OVERRUN])
    backup = MockAdapter([json.dumps(GOOD)])
    first.backup_for_unusable = lambda: backup
    observe(first, b"\xff\xd8", "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert [c["kind"] for c in backup.calls] == ["images"]


def test_a_single_photo_unusable_twice_still_fails_loudly():
    adapter = MockAdapter(["prose", "more prose"])
    with pytest.raises(ObserveError) as e:
        observe(adapter, b"\xff\xd8", "image/jpeg")
    assert e.value.unusable and len(adapter.calls) == 2


def test_a_provider_with_one_image_per_call_reads_the_main_photo():
    adapter = OneImageOnly([json.dumps(GOOD)])
    observe(adapter, b"\xff\xd8" + b"m" * 8, "image/jpeg", more=[(b"\xff\xd8x", "image/jpeg")])
    assert [c["kind"] for c in adapter.calls] == ["image"]
    assert "image/jpeg 10 bytes" in adapter.calls[0]["prompt"]


def test_token_factory_gets_all_three_photos_in_one_request(monkeypatch):
    sent: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            sent.append(kwargs)
            msg = SimpleNamespace(content=json.dumps(GOOD))
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)
    a = TokenFactoryAdapter(model="test/vl", api_key="k", base_url="https://x/v1/")
    more = [(b"\xff\xd8B", "image/jpeg"), (b"\x89PNGC", "image/png")]
    observe(a, b"\xff\xd8A", "image/jpeg", more=more)
    assert len(sent) == 1
    parts = sent[0]["messages"][1]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url", "image_url", "image_url"]
    assert sent[0]["response_format"]["type"] == "json_schema"


# ---------- location: the first photo that has one ----------


def test_location_comes_from_the_first_photo_that_has_one():
    plain, gps = _jpeg(), _jpeg(LONDON)
    loc, _ = resolve_location(plain, device=None, place=None, home=None, more=[plain, gps])
    assert loc is not None and loc.source == "photo"
    assert (loc.lat, loc.lon) == pytest.approx(exif_gps(gps), abs=0.01)  # rounded to ~1 km
    # the main photo's own location wins over a later one
    main = _jpeg({1: "N", 2: (53.0, 0.0, 0.0), 3: "W", 4: (1.0, 0.0, 0.0)})
    loc, _ = resolve_location(main, device=None, place=None, home=None, more=[gps])
    assert loc.lat == pytest.approx(53.0, abs=0.01)


def test_a_sample_photo_stays_in_london_whatever_the_extra_photos_say(monkeypatch):
    monkeypatch.setattr("herbtwin.where.is_sample", lambda image: image == b"sample")
    loc, _ = resolve_location(b"sample", device=None, place=None, home=None, more=[_jpeg(LONDON)])
    assert loc is not None and loc.source == "sample"


# ---------- what the model is sent: at most 1600 px ----------


def _big(w=4000, h=3000, fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "green").save(buf, fmt)
    return buf.getvalue()


def test_a_big_photo_is_shrunk_for_the_model_and_a_small_one_sent_as_is():
    data, mime = for_model(_big(), "image/jpeg")
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (1600, 1200) and img.format == "JPEG" and mime == "image/jpeg"
    small = _big(1600, 1200)
    assert for_model(small, "image/jpeg") == (small, "image/jpeg")  # byte for byte
    data, mime = for_model(_big(3000, 4000, "PNG"), "image/png")  # portrait stays portrait
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (1200, 1600) and mime == "image/jpeg"


@respx.mock
def test_every_photo_reaches_the_model_at_most_1600_px(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [], [json.dumps(ADV)] * 3)
    rec = Recording([json.dumps(OBS)])
    c.app.state.deps.observe_adapter = rec
    big = _big()
    files = [("photo", ("a.jpg", big, "image/jpeg")), *_more(big, PNG)]
    assert c.post("/api/analyse", files=files).status_code == 200
    sizes = []
    for image, _ in rec.images[0]:
        with Image.open(io.BytesIO(image)) as img:
            sizes.append(max(img.size))
    assert sizes[:2] == [MODEL_LONG_SIDE, MODEL_LONG_SIDE] and sizes[2] == 8  # the PNG fits


@respx.mock
def test_a_cut_off_read_of_three_photos_still_gives_an_answer_page(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [OVERRUN, OVERRUN, json.dumps(OBS)], [json.dumps(ADV)] * 3)
    files = [("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(JPEG, PNG)]
    r = follow(c, c.post("/analyse", files=files))
    assert r.status_code == 200 and "Water it." in r.text
    assert "Could not read the photo" not in r.text


# ---------- the upload boundary ----------


def _more(*photos):
    return [("more", (f"m{i}.jpg", p, "image/jpeg")) for i, p in enumerate(photos)]


@respx.mock
def test_analyse_reads_up_to_three_photos_in_one_call(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    adapter = c.app.state.deps.observe_adapter
    files = [("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(JPEG, PNG)]
    r = follow(c, c.post("/analyse", files=files))
    assert r.status_code == 200 and "Water it." in r.text
    reads = [call for call in adapter.calls if call["stage"] == "observe"]
    assert [call["kind"] for call in reads] == ["images"]
    assert reads[0]["prompt"].count("[image ") == 3


@respx.mock
def test_the_extra_photos_reach_the_model_without_their_metadata(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [], [json.dumps(ADV)] * 3)
    rec = Recording([json.dumps(OBS)])
    c.app.state.deps.observe_adapter = rec
    files = [("photo", ("a.jpg", _jpeg(), "image/jpeg")), *_more(_jpeg(LONDON))]
    r = c.post("/api/analyse", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["location"]["source"] == "photo"  # read from the second photo
    assert len(rec.images) == 1 and len(rec.images[0]) == 2
    assert all(exif_gps(image) is None for image, _ in rec.images[0])


@respx.mock
def test_an_empty_extra_photo_field_is_the_single_photo_flow(tmp_path):
    # a form sent without script and nothing picked in "Add another photo"
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    files = [
        ("photo", ("a.jpg", JPEG, "image/jpeg")),
        ("more", ("", b"", "application/octet-stream")),
    ]
    r = follow(c, c.post("/analyse", files=files))
    assert r.status_code == 200 and "Water it." in r.text
    adapter = c.app.state.deps.observe_adapter
    assert [call["kind"] for call in adapter.calls if call["stage"] == "observe"] == ["image"]


@respx.mock
def test_a_signed_in_upload_reads_all_its_photos_in_one_call(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, auth = _accounts_client(tmp_path, [], [json.dumps(ADV)] * 3)
    rec = Recording([json.dumps(OBS)])
    c.app.state.deps.observe_adapter = rec
    _sign_in(c, auth)
    files = [("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(JPEG, PNG)]
    r = follow(c, c.post("/analyse", files=files))
    assert r.status_code == 200 and "Water it." in r.text
    assert [len(images) for images in rec.images] == [3]


def test_more_than_three_photos_are_refused_before_any_read(tmp_path):
    c = _client(tmp_path, [], [])
    files = [("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(JPEG, JPEG, JPEG)]
    r = c.post("/analyse", files=files)
    assert r.status_code == 400 and "at most 3 photos" in r.text and '{"detail"' not in r.text
    assert c.app.state.deps.observe_adapter.calls == []
    api = c.post("/api/analyse", files=files)
    assert api.status_code == 400 and "at most 3 photos" in api.json()["detail"]


def test_an_oversized_extra_photo_is_refused(tmp_path):
    c = _client(tmp_path, [], [])
    big = JPEG + b"\x00" * (12 * 1024 * 1024)
    r = c.post("/analyse", files=[("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(big)])
    assert r.status_code == 400 and "12 MB" in r.text


def test_photos_too_big_together_get_our_page_not_the_hosts_413(tmp_path):
    # each under 12 MB, 30 MB together: Cloud Run would refuse over 32 MiB with a bare 413
    c = _client(tmp_path, [], [])
    nine = JPEG + b"\x00" * (9 * 1024 * 1024)
    big = JPEG + b"\x00" * (12 * 1024 * 1024 - len(JPEG) - 1)
    files = [("photo", ("a.jpg", big, "image/jpeg")), *_more(nine, nine)]
    r = c.post("/analyse", files=files)
    assert r.status_code == 400 and "too big together" in r.text and '{"detail"' not in r.text
    assert 'href="/"' in r.text
    assert c.app.state.deps.observe_adapter.calls == []
    api = c.post("/api/analyse", files=files)
    assert api.status_code == 400 and "too big together" in api.json()["detail"]


def test_the_home_page_shrinks_only_the_extra_photos_and_checks_the_total(tmp_path):
    page = _client(tmp_path, [], []).get("/").text
    script = page.split("more photos of the same plant", 1)[1].split("})();", 1)[0]
    assert "LONG = 2400" in script and '"image/jpeg", 0.85' in script
    assert "TOTAL = 28 * 1024 * 1024" in script and "too big together" in script
    assert "take.map(shrink)" in script  # the extras; the main photo is never redrawn


def test_an_extra_file_that_is_not_a_photo_is_refused(tmp_path):
    c = _client(tmp_path, [], [])
    evil = b"MZ\x90\x00" + b"\x00" * 32
    r = c.post("/analyse", files=[("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(evil)])
    assert r.status_code == 400 and "JPEG or PNG" in r.text


@respx.mock
def test_the_same_main_photo_with_new_extra_photos_is_read_again(tmp_path):
    # the repeat-photo shortcut (replays.py) must never hand a three-photo answer to one photo
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)] * 2, [json.dumps(ADV)] * 6)
    c.post("/api/analyse", files=[("photo", ("a.jpg", JPEG, "image/jpeg")), *_more(PNG)])
    c.post("/api/analyse", files={"photo": ("a.jpg", JPEG, "image/jpeg")})
    adapter = c.app.state.deps.observe_adapter
    kinds = [call["kind"] for call in adapter.calls if call["stage"] == "observe"]
    assert kinds == ["images", "image"]


# ---------- the pages ----------


def test_the_home_form_offers_two_more_photos_of_the_same_plant(tmp_path):
    page = _client(tmp_path, [], []).get("/").text
    box = page.split('<div class="home-more"', 1)[1].split("</div>", 1)[0]
    assert "Add another photo of the same plant" in box and "(optional)" in box
    more = box.split('<input type="file" name="more"', 1)[1].split(">", 1)[0]
    assert 'accept="image/jpeg,image/png"' in more and "multiple" in more
    assert 'aria-describedby="more-hint"' in more
    assert 'id="more-said" role="status" aria-live="polite"' in box
    script = page.split("more photos of the same plant", 1)[1].split("})();", 1)[0]
    assert "MAX_MORE = 2" in script and "DataTransfer" in script
    assert "Remove photo" in script
    assert "kept.concat(" in script  # a new pick adds to the photos, never replaces them
    assert "add.hidden = full" in script  # no more to add once there are three
    assert "kept = []" in script  # a sample tile clears photos of another plant


def test_the_spot_button_never_sends_the_extra_photos(tmp_path):
    # the bed answer reads one photo: the extras are for one plant's answer
    page = _client(tmp_path, [], []).get("/").text
    script = page.split("more photos of the same plant", 1)[1].split("})();", 1)[0]
    assert 'getAttribute("formaction")' in script


def test_the_wait_page_shows_the_extra_photos():
    assert 'id="wait-more"' in progress.WAIT_PHOTO and "p.more" in progress.WAIT_PHOTO


@respx.mock
def test_the_answer_page_has_room_for_the_extra_photos(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert 'class="your-more" id="your-more"' in r.text and "herbtwin-photo-more:" in r.text
