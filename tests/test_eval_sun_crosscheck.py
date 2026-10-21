import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_sun_crosscheck import TAPS, agreement, predicted_lit  # noqa: E402


def test_the_trough_is_lit_at_midday_in_june_and_dark_at_dusk_in_december():
    assert predicted_lit(TAPS["trough"], datetime(2026, 6, 15, 13, 0))
    assert not predicted_lit(TAPS["trough"], datetime(2026, 12, 15, 15, 30))


def test_bright_shade_is_never_counted():
    rows = [("trough", True, "direct_sun"), ("pot_row", False, "deep_shade"),
            ("corner_pot", True, "deep_shade"), ("trough", True, "bright_shade")]  # fmt: skip
    got = agreement(rows)
    assert got["decisive"] == 3 and got["agreement"] == 0.667 and not got["pass"]
    assert agreement([])["agreement"] is None
