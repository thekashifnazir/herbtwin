import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compass_probe_report import Tap, main, score, tap_of, verdict  # noqa: E402

HEADER = "n,spot,source,alpha,beta,gamma,webkit_heading,webkit_accuracy\n"


def test_rows_become_taps_by_source():
    android = tap_of(
        {"spot": "trough", "source": "absolute", "alpha": "169", "beta": "90", "gamma": "0"}
    )
    assert android == Tap("trough", "absolute", 191.0, 0.0, None)
    ios = {
        "spot": "pot row",
        "source": "ios",
        "alpha": "12",
        "beta": "90",
        "gamma": "0",
        "webkit_heading": "190",
        "webkit_accuracy": "10",
    }
    assert tap_of(ios).heading == 190.0 and tap_of(ios).accuracy == 10.0
    relative = {"source": "relative", "alpha": "10", "beta": "90", "gamma": "0"}
    assert tap_of(relative) is None  # no north
    assert tap_of({"source": "ios", "beta": "90", "gamma": "0", "webkit_heading": ""}) is None


def test_score_and_verdict():
    taps = [Tap("s", "absolute", h, 20.0 + i, None) for i, h in enumerate((185, 195, 200, 170))]
    s = score(taps, 191)
    assert s == {
        "n": 4,
        "median_error": 7.5,
        "worst_error": 21.0,
        "pitch_median": 21.5,
        "pitch_spread": 3.0,
    }
    assert verdict(s).startswith("compass passes")
    assert verdict({"median_error": 31.0, "worst_error": 90.0}).startswith("compass fails")
    assert verdict({"median_error": 12.0, "worst_error": 40.0}).startswith("compass usable")


def test_cli_scores_against_each_truth(tmp_path, capsys):
    f = tmp_path / "taps.csv"
    f.write_text(HEADER + "1,strip bed,absolute,169,90,0,,\n2,strip bed,absolute,171,90,0,,\n")
    assert main([str(f), "--truth", "191", "--truth", "169"]) == 0
    out = capsys.readouterr().out
    assert "truth 191 degrees" in out and "truth 169 degrees" in out


def test_cli_fails_with_no_usable_taps(tmp_path):
    f = tmp_path / "taps.csv"
    f.write_text(HEADER + "1,trough,relative,10,90,0,,\n")
    assert main([str(f), "--truth", "191"]) == 1
