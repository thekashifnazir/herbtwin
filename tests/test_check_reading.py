import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_reading", Path(__file__).parents[1] / "scripts" / "check_reading.py"
)
check_reading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_reading)


def test_verdict_needs_three_of_four_rhs_plants_verified():
    rows = [{"species": s, "verified": True} for s, _ in check_reading.PLANTS[:3]]
    rows.append({"species": check_reading.PLANTS[3][0], "verified": False})
    assert check_reading.verdict(rows) is True
    rows[0]["verified"] = False
    assert check_reading.verdict(rows) is False


def test_run_without_a_lookup_source_gives_default_rows(tmp_path):
    from herbtwin.stages.research import Lookup

    rows = check_reading.run(Lookup(), tmp_path)
    assert len(rows) == len(check_reading.PLANTS) and not any(r["verified"] for r in rows)
