import io
import json
from datetime import datetime

from PIL import Image

from herbtwin.adapters.mock import OVERRUN, MockAdapter
from herbtwin.side_by_side import MAX_SIDE, Side, compare_pair, shrink


def _jpeg(w: int, h: int, colour="green", exif: bool = False) -> bytes:
    img = Image.new("RGB", (w, h), colour)
    buf = io.BytesIO()
    if exif:
        e = img.getexif()
        e[0x0132] = "2026:10:02 10:16:56"
        img.save(buf, "JPEG", exif=e)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def _reply(change: str, confidence: str = "high") -> str:
    return json.dumps({"change": change, "confidence": confidence, "reason": "r"})


EARLIER = Side(_jpeg(40, 30), datetime(2026, 10, 2, 10, 16), "direct_sun")
LATER = Side(_jpeg(60, 30, "olive"), datetime(2026, 10, 3, 14, 1), "bright_shade")
AGREE_LESS = [_reply("less"), _reply("more"), _reply("less"), _reply("more")]


def _compare(replies, earlier=EARLIER, later=LATER, **kw):
    m = MockAdapter(replies)
    return m, compare_pair(m, earlier, later, "posture", model="test/vl", **kw)


def test_shrink_caps_the_long_side_and_drops_metadata():
    out = shrink(_jpeg(3000, 1500, exif=True))
    with Image.open(io.BytesIO(out)) as img:
        assert max(img.size) == MAX_SIDE and img.format == "JPEG"
        assert 0x0132 not in img.getexif()


def test_four_agreeing_looks_give_the_change_read_later_against_earlier():
    m, c = _compare(AGREE_LESS)
    assert c.verdict == "less" and c.reason is None
    assert [look.change for look in c.looks] == ["less"] * 4  # later-first replies flipped
    assert [look.order for look in c.looks] == [
        "earlier_first",
        "later_first",
        "earlier_first",
        "later_first",
    ]
    assert c.prompt_version == "c2-v1" and c.model == "test/vl"
    assert all(call["kind"] == "images" for call in m.calls)


def test_photos_go_in_both_orders():
    m, _ = _compare(AGREE_LESS)
    a, b = len(shrink(EARLIER.image)), len(shrink(LATER.image))
    assert a != b
    assert f"[image image/jpeg {a} bytes] [image image/jpeg {b} bytes]" in m.calls[0]["prompt"]
    assert f"[image image/jpeg {b} bytes] [image image/jpeg {a} bytes]" in m.calls[1]["prompt"]


def test_only_the_timed_prompt_carries_time_and_light():
    m, _ = _compare(AGREE_LESS)
    assert "Photo A was taken" not in m.calls[0]["prompt"]
    assert "Photo A was taken at 10:16, in direct sun" in m.calls[2]["prompt"]
    assert "Photo B was taken at 14:01, in bright shade" in m.calls[2]["prompt"]
    # the later-first timed call names the photos the other way round
    assert "Photo A was taken at 14:01, in bright shade" in m.calls[3]["prompt"]


def test_timed_prompt_without_time_or_light():
    m, _ = _compare(AGREE_LESS, earlier=Side(_jpeg(40, 30)), later=Side(_jpeg(60, 30)))
    assert "at an unknown time, light not measured" in m.calls[2]["prompt"]


def test_disagreement_is_cant_tell():
    _, c = _compare([_reply("less"), _reply("same"), _reply("less"), _reply("more")])
    assert c.verdict == "cant_tell" and c.reason == "the four looks did not agree"


def test_low_confidence_is_cant_tell():
    _, c = _compare([_reply("less"), _reply("more"), _reply("less", "low"), _reply("more")])
    assert c.verdict == "cant_tell" and c.reason == "the model was not sure"


def test_unreadable_reply_is_cant_tell():
    _, c = _compare([_reply("less"), "not json", _reply("less"), _reply("more")])
    assert c.verdict == "cant_tell" and c.reason == "a reply could not be read"
    assert c.looks[1].change is None and c.looks[1].raw == "not json"


def test_an_overrun_is_retried_once_at_a_higher_budget():
    m, c = _compare([OVERRUN, *AGREE_LESS])
    assert c.verdict == "less"
    assert [call["max_tokens"] for call in m.calls[:2]] == [4096, 8192]


def test_two_overruns_make_that_look_unreadable():
    _, c = _compare([OVERRUN, OVERRUN, *AGREE_LESS[1:]])
    assert c.verdict == "cant_tell" and c.looks[0].raw == ""


def test_a_failing_model_is_cant_tell_not_a_crash():
    _, c = _compare([])  # the mock is exhausted: every call raises AdapterError
    assert c.verdict == "cant_tell" and len(c.looks) == 4


def test_an_unreadable_photo_is_cant_tell_without_a_call():
    m, c = _compare(AGREE_LESS, earlier=Side(b"not a photo"))
    assert c.verdict == "cant_tell" and c.reason == "a photo could not be read"
    assert m.calls == []


def test_four_workers_still_make_four_calls():
    replies = [_reply("same")] * 4  # identical, so the order calls finish in does not matter
    m, c = _compare(replies, workers=4)
    assert c.verdict == "same" and len(m.calls) == 4
