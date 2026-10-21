import json

import pytest

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.evals.actions import (
    ACTION_CLASSES,
    build_prompt,
    extract,
    label_sources,
    mirage_sources,
    parse_extraction,
    se_sources,
)


def test_parse_extraction_sorts_dedupes_and_adds_the_primary():
    ext = parse_extraction(
        '<think>{x}</think>{"actions": ["prune", "water", "prune"], "primary": "dont_water"}'
    )
    assert ext.actions == ["dont_water", "prune", "water"] and ext.primary == "dont_water"


def test_parse_extraction_rejects_unknown_or_empty():
    with pytest.raises(ValueError):
        parse_extraction('{"actions": ["fertilise"], "primary": "fertilise"}')
    with pytest.raises(ValueError):
        parse_extraction('{"actions": [], "primary": "water"}')


def test_prompt_lists_every_class_and_clips_long_answers():
    p = build_prompt("Why yellow?", "x" * 5000)
    assert all(f"- {c}:" in p for c in ACTION_CLASSES)
    assert "[...]" in p and len(p) < 5000


def test_extract_repairs_once():
    a = MockAdapter(["prose", '{"actions": ["leave_normal"], "primary": "leave_normal"}'])
    assert extract(a, "q", "a", suffix="\n/no_think").primary == "leave_normal"
    assert a.calls[0]["prompt"].endswith("/no_think")


def _q(i, accepted=True, subset=("diagnosis",)):
    return {
        "id": i,
        "url": f"u{i}",
        "title": "T",
        "body": "B",
        "subset": list(subset),
        "answers": [{"id": 1, "accepted": accepted, "body": "Water it less.", "score": 1}],
    }


def test_se_sources_take_accepted_answers_only():
    s = se_sources([_q(1), _q(2, accepted=False)], "s3/x.jsonl")
    assert [x.id for x in s] == ["actions_se/1"] and s[0].tag == "safe-to-train"


def _m(i, category="Plant Care and Gardening Guidance"):
    return {
        "id": f"m{i}",
        "raw_metadata": json.dumps({"category": category, "entity_type": "plant"}),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "text": None},
                    {"type": "text", "text": "Why droopy?"},
                ],
            },
            {"role": "assistant", "content": [{"type": "text", "text": "Water deeply."}]},
        ],
    }


def test_mirage_sources_keep_plant_care_sample_and_are_test_only():
    rows = [_m(i) for i in range(5)] + [_m(9, "Insect and Pest Management")]
    s = mirage_sources(rows, "p.parquet", n=3)
    assert len(s) == 3 and all(x.tag == "test-only" for x in s)
    assert s[0].question == "Why droopy?" and s[0].answer == "Water deeply."
    assert [x.id for x in mirage_sources(rows, "p.parquet", n=3)] == [x.id for x in s]


def test_label_sources_reuses_cache_and_reports_failures():
    sources = se_sources([_q(1), _q(2), _q(3)], "s3/x.jsonl")

    class Mixed(MockAdapter):
        def complete(self, system, user, *, max_tokens=1024):
            self.calls.append(user)
            if len(self.calls) == 1:
                raise AdapterError("down")
            return '{"actions": ["water"], "primary": "water"}'

    cached = {"actions_se/3": {"actions": ["prune"], "primary": "prune", "model": "m"}}
    adapter = Mixed()
    items, failed = label_sources(sources, adapter, model="m", cached=cached)
    assert failed == ["actions_se/1"]
    assert [i.id for i in items] == ["actions_se/2", "actions_se/3"]
    assert items[1].label["primary"] == "prune" and len(adapter.calls) == 2
    assert "Water it less" not in json.dumps([i.model_dump() for i in items])


def test_parallel_labelling_keeps_source_order():
    sources = se_sources([_q(i) for i in range(1, 7)], "s3/x.jsonl")

    class Echo(MockAdapter):
        def complete(self, system, user, *, max_tokens=1024):
            return '{"actions": ["water"], "primary": "water"}'

    items, failed = label_sources(sources, Echo(), model="m", workers=3)
    assert [i.id for i in items] == [s.id for s in sources] and failed == []


def test_make_extractor_reads_the_backend_prefix():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "extract_actions", Path(__file__).parents[1] / "scripts" / "extract_actions.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert type(mod.make_extractor("claude:claude-sonnet-5-5")).__name__ == "ClaudeCLIAdapter"
    ollama = mod.make_extractor("qwen3:14b")
    assert type(ollama).__name__ == "OllamaAdapter" and ollama.model == "qwen3:14b"
    assert mod.make_extractor("ollama:qwen3:14b").model == "qwen3:14b"


def test_extraction_stays_on_the_nine_phase_a_classes():
    from herbtwin.schemas import COARSE_ACTIONS

    assert tuple(ACTION_CLASSES) == COARSE_ACTIONS
    p = build_prompt("q", "a")
    assert "- feed:" not in p and "- check_pests:" not in p
