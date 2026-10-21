import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from simulate_ask_rate import simulate  # noqa: E402


def test_a_small_simulation_asks_only_for_ground_settings():
    got = simulate(points=3, seed=7)
    assert got["reads"] == 3 * 5 * 12
    assert 0 < got["asks"] <= 3 * 2 * 12  # raised bed and open ground only
    assert got["changes_the_list_share"] == 1.0
