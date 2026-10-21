import json

from herbtwin.evals.pairs import MAX_CHARS, Pair, build_pairs, choose_pair, pair_texts


def _a(i, score, accepted=False, body="text"):
    return {"id": i, "score": score, "accepted": accepted, "body": body}


def test_accepted_answer_wins_when_its_score_is_at_least_the_others():
    pref, other = choose_pair([_a(1, 5, True), _a(2, 5), _a(3, 1)])
    assert pref["id"] == 1 and other["id"] == 3


def test_accepted_but_outvoted_falls_back_to_the_score_gap_rule():
    pref, other = choose_pair([_a(1, 2, True), _a(2, 9), _a(3, 1)])
    assert pref["id"] == 2 and other["id"] == 3
    assert choose_pair([_a(1, 2, True), _a(2, 3)]) is None  # gap 1: skipped


def test_unaccepted_pairs_need_a_gap_of_three():
    assert choose_pair([_a(1, 4), _a(2, 2)]) is None
    pref, other = choose_pair([_a(1, 5), _a(2, 2)])
    assert (pref["id"], other["id"]) == (1, 2)


def test_single_answer_questions_give_no_pair():
    assert choose_pair([_a(1, 9, True)]) is None


def test_build_pairs_is_one_per_question_and_tracks_ids_only(tmp_path):
    rows = [
        {
            "id": 10,
            "url": "u10",
            "title": "t",
            "body": "b",
            "subset": ["herb", "diagnosis"],
            "answers": [_a(1, 3, True), _a(2, 0), _a(3, 1)],
        },
        {
            "id": 11,
            "url": "u11",
            "title": "t",
            "body": "b",
            "subset": ["herb"],
            "answers": [_a(4, 1)],
        },
    ]
    (tmp_path / "s3").mkdir()
    (tmp_path / "s3" / "se_diagnosis_herb.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    items = build_pairs(tmp_path)
    assert [i.id for i in items] == ["pairs_se/10"]
    label = items[0].label
    assert label == {
        "question_id": 10,
        "preferred_id": 1,
        "other_id": 2,
        "gap": 3,
        "accepted": True,
        "subsets": ["diagnosis", "herb"],
    }
    assert "text" not in json.dumps(label)


def test_pair_texts_clip_long_answers():
    q = {"title": "T", "body": "B", "answers": [_a(1, 1, body="x" * (MAX_CHARS + 50)), _a(2, 0)]}
    pair = Pair(question_id=1, preferred_id=1, other_id=2, gap=1, accepted=True, subsets=[])
    question, pref, other = pair_texts(q, pair)
    assert question.startswith("T\n\nB") and pref.endswith("[...]") and other == "text"
