"""Builds the round-5 sets (19 Oct; Kash: "keep going", aimed at recall).

DEV (data/eval/sets/trusted_judge_v6_dev.jsonl) is round 4's DEV with the round-5 reading
on the author's labels and hand-written forms: pulling up the whole plant is its own action
(remove_plant), not removing the affected parts. The blind labels on the old v4 test stay
as they were, so where round 5's rules are stricter they cost recall, never a false agree.
The spent v5 test is not used: round 5 chose nothing on it.

TEST (trusted_judge_v6_test.jsonl) is fresh: 200 sentences from a new writer agent, built
after pre-registration part 2, sharing nothing with v1, v2, v4 or v5.

    uv run python scripts/build_judge_v6.py dev
    uv run python scripts/build_judge_v6.py test [<blind items file to write>]
"""

from __future__ import annotations

import sys

import build_judge_v5 as v5

DEV_OUT = v5.SETS / "trusted_judge_v6_dev.jsonl"
TEST_OUT = v5.SETS / "trusted_judge_v6_test.jsonl"
WHOLE_PLANT = {
    "Where downy mildew strikes, pull up and bin the worst plants.",
    "If the leaves are mottled with downy mildew, bin the plant.",
    "Bin basil plants that show downy mildew.",
}


def dev() -> None:
    v5.STRICT.add("Bin basil plants that show downy mildew.")
    for sentence in WHOLE_PLANT:
        v5.FORM_FIX[sentence] = {**v5.FORM_FIX.get(sentence, {}), "action": "remove_plant"}
    v5.DEV_OUT = DEV_OUT
    v5.dev()


def test(items_out: str | None) -> None:
    from v6_test_families import TEST

    v5.test(
        items_out,
        families=TEST,
        out=TEST_OUT,
        earlier=("trusted_judge_v5_dev.jsonl", "trusted_judge_v5_test.jsonl"),
        first_id=2001,
        origin="v6-test",
    )


if __name__ == "__main__":
    if sys.argv[1] == "dev":
        dev()
    else:
        test(sys.argv[2] if len(sys.argv) > 2 else None)
