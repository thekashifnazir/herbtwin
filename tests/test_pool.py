from herbtwin.pool import EXPORT_KEYS, REFIT_AT, counts, pool_rows, region, scored

PRED = {
    "action": "water",
    "signal": "posture",
    "expected": "less",
    "window_days": [1, 7],
    "less_sure": False,
    "before": 2,
    "source": "t",
}


def _score(user="u-in", plant="p1", earlier="a1", later="a2", result="improved", signal="posture"):
    return {
        "user_id": user,
        "plant_id": plant,
        "earlier_answer_id": earlier,
        "later_answer_id": later,
        "action": "water",
        "prediction": PRED,
        "signal": signal,
        "did_it": "yes",
        "result": result,
    }


PLANTS = {
    "p1": {"id": "p1", "species": "salvia officinalis", "place_lat": 51.5, "place_lon": -0.12},
    "p2": {"id": "p2", "species": "mentha spicata", "place_lat": None, "place_lon": None},
}
ANSWERS = {
    "a1": {
        "id": "a1",
        "taken_at": "2026-10-02T10:00:00+00:00",
        "observation": {"water_stress": 2, "decline": 0, "leaf_colour": "green"},
    },
    "a2": {
        "id": "a2",
        "taken_at": "2026-10-04T10:00:00+00:00",
        "observation": {"water_stress": 1, "decline": 0, "leaf_colour": "green"},
    },
    "a3": {
        "id": "a3",
        "taken_at": "2026-11-01T09:00:00+00:00",
        "observation": {"water_stress": 0, "decline": 1, "leaf_colour": "some_yellow"},
    },
}


def test_a_row_carries_only_the_listed_fields():
    [row] = pool_rows({"u-in"}, [_score()], PLANTS, ANSWERS, new_id=lambda: "pair-1")
    assert tuple(row) == EXPORT_KEYS
    assert row == {
        "pair_id": "pair-1",
        "species": "salvia officinalis",
        "month": 10,
        "region": "52,0",
        "signal": "posture",
        "before": 2,
        "after": 1,
        "action": "water",
        "expected": "less",
        "window_days": [1, 7],
        "less_sure": False,
        "did_it": "yes",
        "result": "improved",
    }
    assert "u-in" not in str(row) and "p1" not in str(row) and "a1" not in str(row)


def test_people_who_did_not_opt_in_are_left_out():
    rows = pool_rows({"u-in"}, [_score(), _score(user="u-out")], PLANTS, ANSWERS)
    assert len(rows) == 1


def test_switching_off_leaves_every_pair_out():
    assert pool_rows(set(), [_score(), _score(later="a3")], PLANTS, ANSWERS) == []


def test_missing_rows_are_skipped_and_no_place_is_no_region():
    scores = [_score(plant="gone"), _score(later="gone"), _score(plant="p2", later="a3")]
    [row] = pool_rows({"u-in"}, scores, PLANTS, ANSWERS)
    assert row["region"] is None and row["species"] == "mentha spicata"


def test_each_signal_reads_its_own_observation_field():
    tissue = pool_rows({"u-in"}, [_score(later="a3", signal="tissue")], PLANTS, ANSWERS)
    colour = pool_rows({"u-in"}, [_score(later="a3", signal="colour")], PLANTS, ANSWERS)
    assert (tissue[0]["before"], tissue[0]["after"]) == (0, 1)
    assert (colour[0]["before"], colour[0]["after"]) == ("green", "some_yellow")


def test_pair_ids_are_fresh_each_export():
    a = pool_rows({"u-in"}, [_score()], PLANTS, ANSWERS)[0]["pair_id"]
    b = pool_rows({"u-in"}, [_score()], PLANTS, ANSWERS)[0]["pair_id"]
    assert a != b and len(a) == 32


def test_region_is_whole_degrees():
    assert region(51.5, -0.12) == "52,0"
    assert region(51.47, -0.45) == "51,0"
    assert region(-33.87, 151.21) == "-34,151"
    assert region(None, -0.12) is None


def test_counts_per_action_and_how_many_are_scored():
    rows = [
        {"action": "water", "result": "improved"},
        {"action": "water", "result": "cant_tell"},
        {"action": "water", "result": "improved"},
        {"action": "leave_normal", "result": "not_scored_yet"},
        {"action": "dont_water", "result": "worse"},
    ]
    assert counts(rows) == {
        "dont_water": {"worse": 1},
        "leave_normal": {"not_scored_yet": 1},
        "water": {"improved": 2, "cant_tell": 1},
    }
    assert scored(rows) == 3 and REFIT_AT == 50
