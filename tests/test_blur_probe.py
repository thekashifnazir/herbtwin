"""The blur probe's pre-registered rule, on made-up rows (no paid call)."""

from herbtwin.evals.blur_probe import blurred, decide, rates


def _row(set_, level, conf, quality="poor", note="heavily blurred", correct=True):
    return {"set": set_, "level": level, "conf": conf, "quality": quality, "note": note,
            "correct": correct}  # fmt: skip


def test_keeps_0_8_when_it_is_admissible_and_near_the_best():
    rows = (
        [_row("gbif", "sharp", 0.9, quality="good", note="clear")] * 20
        + [_row("gbif", "heavy", 0.5, correct=False)] * 20
        + [_row("gbif", "medium", 0.75)] * 20
        + [_row("sample", "sharp", 0.85, note="soft focus and blurred background")]
    )
    assert rates(rows, 0.8)["fa"] == 0 and rates(rows, 0.8)["catch"] == 1
    assert decide(rows)[0] == 0.8


def test_a_judges_sample_flagged_rules_a_cut_off_out():
    # the sharp rosemary sample read poor at 0.85, "soft focus": 0.9 would flag it
    rows = (
        [_row("gbif", "sharp", 0.9, quality="good")] * 10
        + [_row("gbif", "heavy", 0.85, correct=False)] * 10
        + [_row("sample", "sharp", 0.85, note="soft focus")]
    )
    assert rates(rows, 0.9)["guard"] == 1 and rates(rows, 0.8)["guard"] == 0
    assert decide(rows)[0] == 0.8  # 0.9 would catch more, but flags a sample


def test_moves_when_a_lower_cut_off_stops_false_alarms():
    sharp_poor = [_row("gbif", "sharp", 0.75, note="blurred")] * 2 + [
        _row("gbif", "sharp", 0.95, quality="good")
    ] * 18  # 10% false alarms at 0.8
    rows = sharp_poor + [_row("gbif", "heavy", 0.5)] * 20 + [_row("gbif", "medium", 0.5)] * 20
    t, why = decide(rows)
    assert t == 0.7 and "move" in why


def test_the_blur_is_applied_at_1024_px():
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2048, 1024), "green").save(buf, "JPEG")
    out = Image.open(BytesIO(blurred(buf.getvalue(), 10)))
    assert out.size == (1024, 512)


def test_the_budget_stop_stops_the_spending():
    # #285 review: pool.map queued every read, so after "stopping" all were still paid for
    from herbtwin.evals.blur_probe import paid_rows

    made = []

    def read(job):
        made.append(job)
        return {"id": job, "cost_usd": 0.4}

    rows = list(paid_rows(list(range(20)), read, budget=1.0, spent=0.0, workers=2))
    assert len(made) == len(rows) == 4  # after 2 chunks ($1.60, past $1) no 3rd is sent
    assert list(paid_rows(list(range(5)), read, budget=1.0, spent=2.0, workers=2)) == []


def test_a_rescore_keeps_the_notes_written_by_hand():
    from herbtwin.evals.blur_probe import END_GENERATED, GENERATED, with_block

    page = f"{GENERATED}\nold table\n{END_GENERATED}\n\n**Acted on:** kept.\n"
    out = with_block(page, "new table")
    assert "new table" in out and "old table" not in out and "**Acted on:** kept." in out
    assert with_block("", "first").startswith(GENERATED)
