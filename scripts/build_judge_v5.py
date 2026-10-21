"""Builds the round-4 sets for the extract-then-decide check (19 Oct; Kash: "keep going,
round 4"): the blind labeller's stricter reading is now in the rules (trusted_check).

DEV (data/eval/sets/trusted_judge_v5_dev.jsonl) is everything round 3 has spent:
- v4 TEST, with the devpost-submission session's blind labels as gold
  (data/eval/labels/2026-10-19-v4-test-blind.jsonl): no longer held out, so it is DEV now;
- v4 DEV, with the author's labels re-read the strict way (STRICT below);
- the v4 red team, as its own split.

The hand-written forms move to the round-4 vocabulary (FORM_FIX; pots and beds become
container conditions). TEST is a fresh set built after the pre-registration
(trusted_judge_v5_test.jsonl), with no sentence shared with v1, v2, v4 or the extractor's
examples.

    uv run python scripts/build_judge_v5.py dev
    uv run python scripts/build_judge_v5.py test [<blind items file to write>]
"""

from __future__ import annotations

import calendar
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from herbtwin.stages.trusted_check import Form, PlantState, decide

ROOT = Path(__file__).parents[1]
SETS = ROOT / "data/eval/sets"
V4 = SETS / "trusted_judge_v4.jsonl"
BLIND_V4 = ROOT / "data/eval/labels/2026-10-19-v4-test-blind.jsonl"
DEV_OUT = SETS / "trusted_judge_v5_dev.jsonl"
TEST_OUT = SETS / "trusted_judge_v5_test.jsonl"
ADVICE_PLAIN = {
    "water": "water it", "dont_water": "hold off watering", "move_light": "move it to better light",
    "shelter": "protect it from the cold", "treat_or_remove": "treat it, or remove the affected parts",
    "prune": "cut it back", "leave_normal": "leave it, as this is normal",
}  # fmt: skip
_POT = re.compile(r"\b(?:pots?|containers?|tubs?|planters?|window ?boxes?)\b", re.I)
_GROUND = re.compile(r"\b(?:beds?|borders?|open ground|in the ground)\b", re.I)

# v4 DEV sentences the strict reading labels no in every state: a strength or a quality of
# the plant the state can't confirm, a near-miss action, a group the plant isn't in, or a
# statement rather than an instruction
STRICT = {
    "Water container herbs morning and evening in very hot weather.",
    "Don't water if heavy rain is forecast.",
    "Thin parsley seedlings to 15cm apart.",
    "Move tender herbs under cover before frost.",  # coriander is not a tender herb
    "Dieback of mint in autumn is normal.",
    "If parsley wilts on a dry day, give it a long drink.",
    "Protect sage pots from freezing winds.",  # no cold in the state
    "Remove diseased leaves promptly.",  # no disease named in the state
}
# the round-4 vocabulary: field changes to the v4 hand-written forms
FORM_FIX: dict[str, dict] = {
    "Thin parsley seedlings to 15cm apart.": {"action": "thin"},
    "Thin coriander seedlings to 5cm apart once they can be handled.": {"action": "thin"},
    "Indoors, water basil less in winter.": {"action": "water_less"},
    "Water rosemary only sparingly.": {"action": "water_less"},
    "Thyme needs little water once established.": {
        "action": "water_less", "add": [("plant_trait", "established")]},
    "Deadhead chives through the summer.": {"action": "deadhead"},
    "When seedlings appear, keep the compost just moist.": {"action": "water_less"},
    "Let sage dry out well between waterings.": {"action": "water_less"},
    "Shelter pots of sage from icy winds.": {
        "add": [("cold_or_frost_forecast", "icy winds")]},
    "Protect sage pots from freezing winds.": {
        "add": [("cold_or_frost_forecast", "freezing winds")]},
    "Remove any shoots killed by disease and bin them.": {
        "add": [("named_problem", "disease")]},
    "Remove diseased leaves promptly.": {"add": [("named_problem", "disease")]},
    "Destroy rosemary beetles and their larvae.": {
        "add": [("named_problem", "rosemary beetles")]},
    "Cut out stems spotted with rust.": {"add": [("named_problem", "rust")]},
    "Shorten leggy mint stems by half.": {"add": [("plant_trait", "leggy")]},
    "Cover young parsley with a cloche when frost threatens.": {
        "add": [("plant_trait", "young")]},
    "It can help to fleece young basil on cold nights.": {"add": [("plant_trait", "young")]},
    "There is no need to fleece established sage.": {"add": [("plant_trait", "established")]},
    "Perhaps move parsley somewhere brighter if it looks pale.": {
        "conditions": [("plant_trait", "looks pale")]},
    "If parsley wilts on a dry day, give it a long drink.": {
        "conditions": [("plant_trait", "wilts"), ("hot_dry_weather", "a dry day")]},
    "Water container herbs morning and evening in very hot weather.": {
        "conditions": [("container", "pot"), ("hot_dry_weather", "very hot weather")]},
    "Don't water if heavy rain is forecast.": {"conditions": [("rain_forecast", "heavy rain")]},
    "When heavy rain is forecast, there is no need to water beds.": {
        "conditions": [("rain_forecast", "heavy rain")]},
    "Move pots of sage against a house wall before a hard frost.": {
        "conditions": [("cold_or_frost_forecast", "hard frost")]},
}  # fmt: skip


def round4_form(sentence: str, form: dict) -> Form:
    f = {**form, "conditions": [dict(c) for c in form["conditions"]]}
    fix = dict(FORM_FIX.get(sentence, {}))
    if "conditions" in fix:
        f["conditions"] = [{"kind": k, "value": v} for k, v in fix.pop("conditions")]
    f["conditions"] += [{"kind": k, "value": v} for k, v in fix.pop("add", [])]
    f.update(fix)
    kinds = {(c["kind"], c["value"]) for c in f["conditions"]}
    for words, place in ((_POT, "pot"), (_GROUND, "ground")):
        if words.search(sentence) and ("container", place) not in kinds:
            f["conditions"].append({"kind": "container", "value": place})
    return Form.model_validate(f)


def rule(form: Form, sentence: str, state: dict) -> bool:
    return decide(form, PlantState(**state), sentence) == "agree"


def dev() -> None:
    blind = {}
    for line in BLIND_V4.read_text().splitlines():
        if line.strip():
            x = json.loads(line)
            blind[x["id"]] = x["label"] == "yes"
    rows = []
    for line in V4.read_text().splitlines():
        r = json.loads(line)
        form = round4_form(r["sentence"], r["form"])
        if r["split"] == "test":
            split, gold, source = "dev", blind[r["id"]], "blind (devpost-submission)"
        else:
            split = r["split"]
            gold = r["gold"] and r["sentence"] not in STRICT
            source = "author, strict"
        rows.append({"id": r["id"], "split": split, "origin": f"v4-{r['split']}",
                     "sentence": r["sentence"], "kind": r["kind"], "state": r["state"],
                     "gold": gold, "gold_source": source,
                     "form_gold": rule(form, r["sentence"], r["state"]),
                     "form": form.model_dump()})  # fmt: skip
    DEV_OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    for split in ("dev", "redteam"):
        rs = [r for r in rows if r["split"] == split]
        neg = sum(not r["gold"] for r in rs)
        print(f"{split}: {len(rs)} items ({len({r['sentence'] for r in rs})} sentences), "
              f"{neg} negatives, {len(rs) - neg} positives")  # fmt: skip
    off = [r for r in rows if r["gold"] != r["form_gold"]]
    print(f"gold vs the rule on the hand-written form: {len(off)} differ")
    for r in off:
        st = {k: v for k, v in r["state"].items() if v not in (None, "unknown", False)}
        print(f"  [{r['origin']} {r['id']}] gold={r['gold']} rule={r['form_gold']} "
              f"{r['sentence']} {st}")  # fmt: skip
    print(Counter((r["split"], r["gold"]) for r in rows))


def blind_item(r: dict) -> dict:
    """What the blind labeller sees: no gold, no form."""
    st = r["state"]

    def yn(v):
        return "unknown" if v is None else ("yes" if v else "no")

    return {"id": r["id"], "sentence": r["sentence"], "plant": st["plant"],
            "our_advice": ADVICE_PLAIN[st["action"]], "month": calendar.month_name[st["month"]],
            "setting": st["setting"], "pot_or_ground": st["container"],
            "soil_feel": st["soil"] or "unknown", "frost_or_cold_night_forecast": yn(st["cold_ahead"]),
            "rain_forecast": yn(st["rain_ahead"]), "hot_or_dry_spell": yn(st["hot_dry"]),
            "named_problem": st["problem"] or "none", "seedlings": "yes" if st["seedlings"] else "no"}  # fmt: skip


def test(
    items_out: str | None,
    families: list[dict] | None = None,
    out: Path = TEST_OUT,
    earlier: tuple[str, ...] = (),
    first_id: int = 1001,
    origin: str = "v5-test",
) -> None:
    import build_judge_v4 as v4

    from herbtwin.stages.trusted_extract import EXAMPLES

    if families is None:
        from v5_test_families import TEST as families
    TEST = families
    seen = set(re.findall(r'"([^"]+[.!?])"', EXAMPLES))
    for name in ("trusted_judge_v1.jsonl", "trusted_judge_v2.jsonl", "trusted_judge_v4.jsonl",
                 *earlier):  # fmt: skip
        for line in (SETS / name).read_text().splitlines():
            if line.strip():
                seen.add(json.loads(line)["sentence"])
    norm = {x.lower().rstrip(".!?") for x in seen}
    names = [f["sentence"] for f in TEST]
    if len(set(names)) != len(names):
        raise SystemExit("a TEST sentence twice")
    reused = [x for x in names if x.lower().rstrip(".!?") in norm]
    if reused:
        raise SystemExit(f"TEST sentences reused: {reused}")
    rows, off = [], []
    for fam in TEST:
        form = round4_form(fam["sentence"], fam["form"].model_dump())
        done = set()
        for st in v4.states(fam):
            if fam.get("near"):
                st = {**st, "action": fam["near"]}
            key = json.dumps(st, sort_keys=True)
            if key in done:
                continue
            done.add(key)
            g = v4.direct_gold(fam, st)
            row = {"id": first_id + len(rows), "split": "test", "origin": origin,
                   "sentence": fam["sentence"], "kind": "near" if fam.get("near") else fam["kind"],
                   "state": st, "gold": g, "gold_source": "author, strict",
                   "form_gold": rule(form, fam["sentence"], st), "form": form.model_dump()}  # fmt: skip
            rows.append(row)
            if row["gold"] != row["form_gold"]:
                off.append(row)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    neg = sum(not r["gold"] for r in rows)
    print(f"test: {len(rows)} items ({len(TEST)} sentences), {neg} negatives, "
          f"{len(rows) - neg} positives")  # fmt: skip
    print(f"gold vs the rule on the hand-written form: {len(off)} differ")
    for r in off:
        st = {k: v for k, v in r["state"].items() if v not in (None, "unknown", False)}
        print(f"  [{r['id']}] gold={r['gold']} rule={r['form_gold']} {r['sentence']} {st}")
    print(Counter((r["kind"], r["gold"]) for r in rows))
    if items_out:
        items = [blind_item(r) for r in rows]
        random.Random(2026).shuffle(items)
        Path(items_out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items))
        print(f"blind items: {items_out}")


if __name__ == "__main__":
    if sys.argv[1] == "dev":
        dev()
    else:
        test(sys.argv[2] if len(sys.argv) > 2 else None)
