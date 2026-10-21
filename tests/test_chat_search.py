"""The chat-search measurement's rubric and summary: offline, no network."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from herbtwin.chat import LESS_SURE, NO_ANSWER, context
from herbtwin.evals import chat_search as C

Q = {q.id: q for q in C.QUESTIONS}


def test_thirty_questions_each_with_a_source_and_a_compiling_rubric():
    assert len(C.QUESTIONS) == 30
    assert len(Q) == 30
    for q in C.QUESTIONS:
        assert q.herb in C.HERBS
        assert q.source.startswith("data/")
        for p in (*q.must, *q.wrong):
            re.compile(p)


@pytest.mark.parametrize("q", C.QUESTIONS, ids=lambda q: q.id)
def test_the_key_fact_passes_its_own_rubric(q):
    assert C.correct(q, q.fact)


@pytest.mark.parametrize(
    ("qid", "text", "ok"),
    [
        ("basil_hardy", "No, basil is frost tender and needs bringing indoors.", True),
        ("basil_hardy", "Yes, basil is hardy and will be fine outside.", False),
        ("rosemary_hardy", "Rosemary is hardy in most of the UK.", True),
        ("rosemary_hardy", "Rosemary is not fully hardy, so bring it in.", False),
        ("parsley_life", "Parsley is an annual, so sow it again.", False),
        ("parsley_life", "It is a biennial: it flowers in its second year.", True),
        ("parsley_sow_out", "Sow outdoors from April.", False),  # half the window
        ("parsley_sow_out", "Sow outdoors from April to August.", True),
        ("rosemary_foam", "That is cuckoo spit; it is harmless, no need to spray.", True),
        ("rosemary_foam", "That is cuckoo spit; spray it with soapy water.", False),
        ("mint_after_flower", "Cut the whole plant back to about 5 cm.", True),
        ("mint_after_flower", "Leave it be.", False),
    ],
)
def test_correct_checks_the_key_fact(qid, text, ok):
    assert C.correct(Q[qid], text) is ok


def test_correct_ignores_the_citations_and_the_less_sure_line():
    q = Q["thyme_mulch"]
    # the fact only inside an address does not count
    assert not C.correct(q, "Use a mulch [https://www.rhs.org.uk/advice/gravel-gardens].")
    assert C.correct(q, f"Spread grit around it.\n\n{LESS_SURE}")


def test_cited_finds_urls_and_bracketed_addresses_once():
    text = (
        "Pinch out flowers [https://www.rhs.org.uk/herbs/basil/grow-your-own]. "
        "See also [rhs.org.uk/herbs/basil/grow-your-own/] and https://kew.org/x."
    )
    assert C.cited(text) == ["rhs.org.uk/herbs/basil/grow-your-own", "kew.org/x"]
    assert C.cited("No sources here, and [this] is not one.") == []


def _tools(*hits):
    return [{"name": "search_web", "arguments": {}, "result": {"results": list(hits)}}]


BASIL_HIT = {
    "title": "Basil / RHS",
    "url": "https://www.rhs.org.uk/herbs/basil/grow-your-own",
    "snippet": "Sow basil indoors",
}
PEONY_HIT = {"title": "Peony problems", "url": "https://www.rhs.org.uk/peony", "snippet": ""}


def test_on_plant_needs_every_cited_source_to_be_a_hit_naming_the_herb():
    basil = C.HERBS["basil"]
    hits = C.hits_of(_tools(BASIL_HIT, PEONY_HIT))
    assert C.on_plant([], hits, basil) is None
    assert C.on_plant(["rhs.org.uk/herbs/basil/grow-your-own"], hits, basil) is True
    assert C.on_plant(["rhs.org.uk/herbs/basil"], hits, basil) is True  # a cut-short address
    assert C.on_plant(["rhs.org.uk/peony"], hits, basil) is False  # a hit, another plant
    # not among the hits: from memory or invented
    assert (
        C.on_plant(["rhs.org.uk/herbs/basil/x", "gardenersworld.com/basil"], hits, basil) is False
    )


def test_unsure_reads_the_model_not_the_app_line():
    assert C.unsure("I'm not sure, sorry.")
    assert C.unsure(NO_ANSWER)
    assert not C.unsure(f"Sow it in April.\n\n{LESS_SURE}")


def test_score_on_a_cited_reply():
    q = Q["basil_plant_out"]
    s = C.score(
        q,
        "Plant it out in June [https://www.rhs.org.uk/herbs/basil/grow-your-own].",
        _tools(BASIL_HIT),
    )
    assert s == {
        "correct": True,
        "cites": True,
        "on_plant": True,
        "unsure": False,
        "less_sure": False,
        "correct_v2": True,
    }


def _row(qid, arm, correct, cites=False):
    score = {
        "correct": correct,
        "cites": cites,
        "on_plant": None,
        "unsure": False,
        "less_sure": False,
    }
    return {"id": qid, "arm": arm, "status": "ok", "score": score}


def test_summarise_pairs_by_question_and_bootstraps_the_difference():
    rows = [
        _row("a", "off", False), _row("a", "on", True),
        _row("b", "off", True), _row("b", "on", True),
        _row("c", "off", False), _row("c", "on", False),
        _row("d", "off", True), _row("d", "on", False),
        {"id": "e", "arm": "on", "status": "error"},
    ]  # fmt: skip
    s = C.summarise(rows, n=200)
    assert s["paired_questions"] == 4
    assert s["arms"]["on"]["correct"]["value"] == 0.5
    assert s["arms"]["off"]["correct"]["value"] == 0.5
    d = s["diff"]["correct"]
    assert d["value"] == 0.0 and d["lo"] < 0 < d["hi"]
    assert "on_plant" not in s["diff"]  # never cited: nothing to pair
    assert s["flips"] == {"on_only": ["a"], "off_only": ["d"]}
    assert C.decision(d) == "no measurable change in correctness"
    assert C.decision({"value": 0.3, "lo": 0.1, "hi": 0.5, "n": 30}).endswith("more correct")


def test_each_herb_gets_one_answer_record_the_chat_can_read():
    for herb in C.HERBS.values():
        rec = C.record_for(herb)
        assert rec.pack is not None  # run_scenario works, as live
        assert f"plant: {herb.common} ({herb.latin})" in context(rec, None)


def test_summarise_does_not_depend_on_the_order_rows_finished_in():
    rows = [
        _row(q, arm, (i + (arm == "on")) % 3 == 0)
        for i, q in enumerate("abcdefgh")
        for arm in C.ARMS
    ]
    assert C.summarise(rows, n=300) == C.summarise(list(reversed(rows)), n=300)


# ---- rubric v2 (post-hoc) ----


def test_rubric_v2_only_names_real_questions_and_keeps_the_facts():
    assert set(C.RUBRIC_V2) <= set(Q)
    for q in C.QUESTIONS:
        assert C.correct_v2(q, q.fact), q.id


@pytest.mark.parametrize(
    ("qid", "text", "v1", "v2"),
    [
        # a bare "won't" is not the fact
        ("coriander_after_flower", "It won't matter much; enjoy the flowers.", True, False),
        ("coriander_after_flower", "No, it will stop producing new leaves.", True, True),
        # "best" alone is not "wait for spring"
        ("thyme_repot_october", "Yes, October is a good time; spring is best too.", True, False),
        ("thyme_repot_october", "Better to wait until spring.", True, True),
        # "hardy" with a "not" in front
        ("rosemary_hardy", "No, rosemary is not reliably hardy here.", False, False),
        ("rosemary_hardy", "Rosemary is hardy, if a little tender in pots.", False, False),
        ("rosemary_hardy", "Rosemary is generally hardy outdoors.", True, True),
        # "may" the verb is not the month
        ("sage_prune", "You may prune it whenever you like.", True, False),
        ("sage_prune", "Prune it in May.", True, True),
        # the data saying nothing is not "no cure"
        ("basil_dm_cure", "I'm not sure; there's no treatment mentioned.", True, False),
        ("basil_dm_cure", "There is no known cure: bin infected plants.", True, True),
        # cutting the flower stems is not cutting the clump
        ("chives_after_flower", "Cut the flower stems back to the base.", True, False),
        ("chives_after_flower", "Cut the whole clump down to about 5 cm.", True, True),
        ("mint_after_flower", "Cut it back to just above soil level.", True, True),
        ("mint_after_flower", "Trim to just above the soil.", False, True),
        ("basil_eat_flowering", "No, the leaves are not safe to eat now.", True, False),
        ("basil_eat_flowering", "The flowers are edible, so do try them.", True, False),
    ],
)
def test_rubric_v2_is_tighter_where_v1_was_loose(qid, text, v1, v2):
    assert C.correct(Q[qid], text) is v1
    assert C.correct_v2(Q[qid], text) is v2


def test_rubric_v2_reads_non_breaking_hyphens():
    text = "These are allium leaf‑miner flies."
    assert not C.correct(Q["chives_white_dots"], text)
    assert C.correct_v2(Q["chives_white_dots"], text)
    assert C.correct_v2(Q["sage_speckles"], "Leaf‐hopper damage; the leaves are safe to eat.")


def _script():
    path = Path(__file__).parents[1] / "scripts" / "measure_chat_search.py"
    spec = importlib.util.spec_from_file_location("measure_chat_search", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["measure_chat_search"] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


def test_scrubbed_rows_keep_the_reply_and_scores_but_no_snippets_or_regions():
    s = _script()
    text = "Seen in parts of England [https://extension.illinois.edu/basil]."
    tools = [
        {
            "name": "search_web",
            "arguments": {"query": "basil"},
            "result": {"results": [dict(BASIL_HIT, title="Basil in Illinois")]},
        }
    ]
    row = {
        "id": "basil_pot", "herb": "basil", "arm": "on", "question": "q", "status": "ok",
        "key": "basil_pot|on|model|hash", "text": text, "tools": tools, "grounded": True,
        "score": {"correct": False}, "calls": 2, "in_tok": 10, "out_tok": 5, "cost_usd": 1e-5,
    }  # fmt: skip
    (out,) = s.scrubbed([row, {"id": "x", "arm": "on", "status": "error"}])
    assert out["reply"] == "Seen in parts of [place] [https://extension.illinois.edu/basil]."
    assert out["cited"] == ["extension.illinois.edu/basil"]  # from the full text
    assert out["hits"] == [
        {"title": "Basil in [place]", "url": BASIL_HIT["url"], "names_herb": True}
    ]
    assert out["searches"] == ["basil"]
    flat = json.dumps(out)
    assert "snippet" not in flat and "Sow basil indoors" not in flat and "key" not in out


def test_summarise_reports_v2_beside_m1_and_the_hand_agreement():
    rows = [_row("a", "off", False), _row("a", "on", True)]
    for r in rows:
        r["score"]["correct_v2"] = True
    s = C.summarise(rows, n=50)
    assert s["diff"]["correct"]["value"] == 1.0
    assert s["diff"]["correct_v2"]["value"] == 0.0
    hand = {"a|off": {"correct": True}, "a|on": {"correct": True}, "z|on": {"correct": False}}
    assert C.hand_agreement(rows, hand) == {"n": 2, "correct": 1, "correct_v2": 2}
