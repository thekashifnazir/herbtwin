import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from risk_gate import run_gate  # noqa: E402

from herbtwin.adapters.mock import MockAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402

GOOD = json.dumps(
    {
        "species": [{"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.9}],
        "condition": "slight droop",
    }
)
BAD = json.dumps(
    {
        "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.6}],
        "condition": "fine",
    }
)


def test_gate_passes_when_four_of_six_correct(tmp_path):
    settings = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.1"})
    photos = {
        h: tmp_path / f"{h}.jpg"
        for h in ["basil", "mint", "parsley", "coriander", "rosemary", "thyme"]
    }
    for p in photos.values():
        p.write_bytes(b"\xff\xd8\xff")
    # zero-shot then few-shot per herb: first four herbs right (8 responses), last two wrong
    script = [GOOD if i < 8 else BAD for i in range(12)]
    adapter = MockAdapter(script)
    # the mock says "basil" for everything; make expected names match for the first four herbs
    expected = {
        "basil": "Ocimum basilicum",
        "mint": "Ocimum basilicum",
        "parsley": "Ocimum basilicum",
        "coriander": "Ocimum basilicum",
        "rosemary": "Rosmarinus officinalis",
        "thyme": "Thymus vulgaris",
    }
    report = run_gate(
        settings,
        photos,
        ["m1"],
        lambda: ["m1", "nvidia/Nemotron-3-Ultra"],
        lambda model: adapter,
        expected=expected,
        out_dir=tmp_path,
    )
    assert report["verdict"] == "pass"
    assert report["nemotron_ids"] == ["nvidia/Nemotron-3-Ultra"]
    assert report["results"]["m1"]["basil"]["zero_shot"]["top1_correct"] is True
    assert list(tmp_path.glob("*.json"))


def test_gate_fails_when_fewer_than_four_correct(tmp_path):
    settings = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.1"})
    photos = {h: tmp_path / f"{h}.jpg" for h in ["basil", "mint", "parsley"]}
    for p in photos.values():
        p.write_bytes(b"\xff\xd8\xff")
    adapter = MockAdapter([BAD] * 6)
    expected = {"basil": "Ocimum basilicum", "mint": "Mentha spicata", "parsley": "x"}
    report = run_gate(
        settings,
        photos,
        ["m1"],
        lambda: ["m1"],
        lambda m: adapter,
        expected=expected,
        out_dir=tmp_path,
    )
    assert report["verdict"] == "fail"
