import base64

from herbtwin.redact import COORDS, EMAIL, IMAGE, redact, redact_value

PIXELS = base64.b64encode(bytes(range(256)) * 4).decode()


def test_an_image_data_url_is_omitted():
    out = redact(f'see {{"url": "data:image/jpeg;base64,{PIXELS}"}} ok')
    assert IMAGE in out and PIXELS[:40] not in out and out.endswith(" ok")


def test_a_bare_base64_run_is_omitted():
    assert redact(f"img {PIXELS} end") == f"img {IMAGE} end"


def test_email_addresses_are_omitted():
    assert redact("from kash.n+herbs@example.co.uk, thanks") == f"from {EMAIL}, thanks"


def test_labelled_coordinates_are_omitted():
    out = redact('lat 51.5072, lon=-0.1276 {"latitude": 51.5, "lng": -0.12}')
    assert "51.5" not in out and "0.12" not in out and out.count(COORDS) == 4


def test_a_coordinate_pair_is_omitted():
    assert redact("at 51.507, -0.128 today") == f"at {COORDS} today"
    assert redact("at 51.5° N, 0.12° W") == f"at {COORDS}"


def test_ordinary_text_is_kept():
    text = "Water 2 cm down. Mean max 12.3 °C, 4 dry days; flat in a pot. Confidence 0.9."
    assert redact(text) == text


def test_redact_value_walks_dicts_and_lists():
    got = redact_value({"a": ["me@x.org", 3], "b": {"c": "lat: 51.5"}, "d": None})
    assert got == {"a": [EMAIL, 3], "b": {"c": f"lat: {COORDS}"}, "d": None}
