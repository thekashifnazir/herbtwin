from herbtwin.crops import CALENDAR_PATH, load_calendar


def test_the_committed_calendar_loads_with_the_new_fields():
    crops = {c.id: c for c in load_calendar(CALENDAR_PATH)}
    assert len(crops) == 155
    assert crops["broad_bean"].mild_months == {"sow_outdoors": frozenset({2, 10, 11})}
    assert crops["tomato"].frost_tender and crops["basil"].frost_tender
    assert crops["courgette"].frost_tender and not crops["garlic"].frost_tender  # H2 vs H4
    assert crops["rhubarb"].windows_by_source["garden_organic"]["plant_out"] >= {9, 10}
    assert crops["garlic"].rating == "H4" and crops["garlic"].rating_in_pot() == "H3"


def test_a_missing_calendar_gives_no_crops(tmp_path):
    load_calendar.cache_clear()
    assert load_calendar(tmp_path / "nope.json") == ()
    bad = tmp_path / "bad.json"
    bad.write_text("[{}]")
    assert load_calendar(bad) == ()
    load_calendar.cache_clear()
