import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_scoring", Path(__file__).parents[1] / "scripts" / "check_scoring.py"
)
cs = importlib.util.module_from_spec(_spec)
sys.modules["check_scoring"] = cs
_spec.loader.exec_module(cs)


def test_pairs_file_has_the_probe_c_design():
    pairs = json.loads(cs.PAIRS.read_text())["pairs"]
    posture = [p for p in pairs if p["signal"] == "posture"]
    by_set = {s: [p for p in posture if p["set"] == s] for s in ("change", "same", "parsley")}
    assert [len(by_set[s]) for s in by_set] == [10, 10, 3]
    assert len({p["id"] for p in pairs}) == len(pairs)
    assert all(p["signal"] in ("posture", "tissue", "colour") for p in pairs)
    assert all(p["expect"] in ("less", "more", "same") for p in pairs)
    for p in pairs:
        for side in (p["earlier"], p["later"]):
            assert ("path" in side) != ("crop" in side)
            assert "rascio_wheat" not in side.get("path", "")  # the model reads its angle labels


def test_other_signals_have_enough_pairs_to_be_judged():
    pairs = json.loads(cs.PAIRS.read_text())["pairs"]
    for signal in ("tissue", "colour"):
        mine = [p for p in pairs if p["signal"] == signal]
        if mine:
            assert sum(p["set"] == "change" for p in mine) >= 10
            assert sum(p["set"] == "same" for p in mine) >= 10


def _r(set_, expect, verdict, light_guard=False):
    return {
        "signal": "posture",
        "set": set_,
        "expect": expect,
        "verdict": verdict,
        "light_guard": light_guard,
    }


def _results(change_right=10, same_false=0, parsley=("less", "less", "less"), guards=None):
    change = [_r("change", "less", "less")] * change_right + [_r("change", "less", "cant_tell")] * (
        10 - change_right
    )
    same = [_r("same", "same", "more")] * same_false + [_r("same", "same", "same")] * (
        10 - same_false
    )
    guards = guards or [False, False, False]
    park = [_r("parsley", "less", v, g) for v, g in zip(parsley, guards, strict=True)]
    return change + same + park + [_r("garden", "same", "more")]  # garden is not gated


def test_bar_passes_at_its_edges():
    ok, counts = cs.verdict(_results(change_right=9, same_false=1))
    assert ok and counts == {"change_right": "9/10", "same_false": "1/10", "parsley_ok": "3/3"}


def test_bar_fails_below_it():
    assert not cs.verdict(_results(change_right=8))[0]
    assert not cs.verdict(_results(same_false=2))[0]
    assert not cs.verdict(_results(parsley=("less", "less", "same")))[0]


def test_parsley_cant_tell_counts_only_when_the_light_check_fired():
    assert cs.verdict(_results(parsley=("less", "less", "cant_tell"), guards=[0, 0, 1]))[0]
    assert not cs.verdict(_results(parsley=("less", "less", "cant_tell")))[0]


def _sig(signal, set_, expect, verdict):
    return {
        "signal": signal,
        "set": set_,
        "expect": expect,
        "verdict": verdict,
        "light_guard": False,
    }


def test_other_signals_are_gated_on_their_own_pairs():
    tissue = [_sig("tissue", "change", "more", "more")] * 9 + [
        _sig("tissue", "change", "more", "same")
    ]
    tissue += [_sig("tissue", "same", "same", "same")] * 10
    colour = [_sig("colour", "change", "less", "less")] * 4  # too few pairs to gate
    gates = cs.gates(_results() + tissue + colour)
    assert gates["posture"][0] is True and gates["tissue"][0] is True
    assert gates["tissue"][1] == {"change_right": "9/10", "same_false": "0/10"}
    assert "colour" not in gates  # fewer than 10 change and 10 same pairs: stays untested


def test_a_signal_below_the_bar_fails():
    tissue = [_sig("tissue", "change", "more", "more")] * 10
    tissue += [_sig("tissue", "same", "same", "less")] * 2 + [
        _sig("tissue", "same", "same", "same")
    ] * 10
    assert cs.gates(tissue)["tissue"] == (False, {"change_right": "10/10", "same_false": "2/12"})
