import json

import pytest

from herbtwin.adapters.base import TokenOverrun
from herbtwin.adapters.mock import MockAdapter
from herbtwin.schemas import SpotRead
from herbtwin.stages.spot import SPOT_SCHEMA, SYSTEM, SpotReadError, parse_spot, read_spot

BED = {
    "setting": "raised_bed",
    "pot_size": "large",
    "medium": "soil",
    "compost_kind": "unknown",
    "colour": " 10YR 4/3 ",
    "organic_matter": "low_medium",
    "texture_lean": "clayey",
    "texture_lean_conf": 0.4,
    "backed_by_wall": False,
}


def test_a_reply_parses_and_pot_size_is_kept_for_pots_only():
    read = parse_spot("```json\n" + json.dumps(BED) + "\n```")
    assert read.setting == "raised_bed" and read.pot_size == "unknown"
    assert read.colour == "10YR 4/3" and read.container == "ground"
    pot = parse_spot(json.dumps(dict(BED, setting="trough", pot_size="medium")))
    assert pot.pot_size == "medium" and pot.container == "pot"


def test_a_plant_close_up_leaves_the_setting_unknown():
    # seen live: a coriander close-up read as a raised bed (GLM) or open ground (Gemma),
    # and the grow list then trusted a setting no one could see
    read = parse_spot(json.dumps(dict(BED, setting="pot", pot_size="small", plant_close_up=True)))
    assert (read.setting, read.pot_size) == ("unknown", "unknown")
    assert read.medium == "soil"  # what is visible still counts
    assert parse_spot(json.dumps(dict(BED, plant_close_up=False))).setting == "raised_bed"


def test_the_model_is_asked_whether_the_photo_is_a_plant_close_up():
    assert SPOT_SCHEMA["properties"]["plant_close_up"] == {"type": "boolean"}
    assert "plant_close_up" in SPOT_SCHEMA["required"] and "plant_close_up" in SYSTEM


def test_defaults_keep_a_thin_reply_usable():
    read = parse_spot('{"setting": "windowsill"}')
    assert read == SpotRead(setting="windowsill")
    assert read.container == "unknown" and read.backed_by_wall is None


def test_one_call_with_the_context_line_and_4096_tokens():
    m = MockAdapter([json.dumps(BED)])
    read_spot(m, b"jpeg", "image/jpeg", context="UK, October")
    assert len(m.calls) == 1
    assert "Context: UK, October" in m.calls[0]["prompt"] and m.calls[0]["max_tokens"] == 4096


@pytest.mark.parametrize(
    "reply",
    ["I think it is a bed", '{"setting": "lawn"}', "", '{"setting": "pot", "medium": "so'],
)
def test_an_unusable_reply_is_an_error_with_no_second_call(reply):
    m = MockAdapter([reply, json.dumps(BED)])
    with pytest.raises(SpotReadError) as e:
        read_spot(m, b"jpeg", "image/jpeg")
    assert len(m.calls) == 1 and e.value.raw == reply


class Overrun(MockAdapter):
    def complete_with_image(self, *a, **k):
        raise TokenOverrun("cut off at 4096 tokens")


def test_a_reply_cut_off_at_max_tokens_is_an_error():
    with pytest.raises(SpotReadError, match="cut off"):
        read_spot(Overrun(), b"jpeg", "image/jpeg")


def test_a_long_colour_is_trimmed_not_a_failed_read():
    read = parse_spot(
        json.dumps({**BED, "colour": "dark greyish brown, about 10YR 4/2, damp " * 3})
    )
    assert len(read.colour) <= 40 and read.setting == BED["setting"]
