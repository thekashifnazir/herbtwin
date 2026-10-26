"""25 Oct re-walk of rev 00115: after "Should I bring it in at night?" the follow-ups still
offered "What if I move it inside?", the same question in other words. Each suggestion says
what asking covers it, and one already covered is not offered again."""

import json
import re
import shutil
import subprocess

import pytest

from herbtwin.chat import starter_covers
from herbtwin.web.app import TEMPLATES


@pytest.mark.parametrize(
    ("starter", "asked"),
    [
        ("What if I move it inside?", "Should I bring it in at night?"),  # the re-walk's case
        ("What if I move it inside?", "Can it go indoors for the winter?"),
        ("When should I harvest it?", "When can I harvest the leaves?"),
        ("Is it safe to eat?", "Can I eat it?"),
        ("How do I treat rosemary beetle?", "How do I get rid of the beetles?"),
        ("What if I don't water it this week?", "What happens if I stop watering it?"),
        ("What if I don't water it this week?", "Can I skip watering this week?"),
        ("Will it spread to my other plants?", "Could it spread to the mint?"),
    ],
)
def test_a_question_in_other_words_covers_its_suggestion(starter, asked):
    assert re.search(starter_covers(starter), asked, re.IGNORECASE), (starter, asked)


@pytest.mark.parametrize(
    ("starter", "asked"),
    [
        ("What if I move it inside?", "Is it safe to eat?"),
        ("When should I harvest it?", "Should I bring it in at night?"),
        ("Is it safe to eat?", "When should I harvest it?"),
        # how often to water is not the twin's what-if of not watering (review of #554)
        ("What if I don't water it this week?", "How often should I water it?"),
    ],
)
def test_an_unrelated_question_leaves_it_offered(starter, asked):
    assert not re.search(starter_covers(starter), asked, re.IGNORECASE), (starter, asked)


def test_the_page_carries_each_suggestions_cover_and_the_script_uses_it():
    src = TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]
    assert '<button type="button" class="starter" data-covers="{{ starter_covers(q) }}">' in src
    assert "new RegExp(b.dataset.covers" in src


CASES = [
    ("What if I move it inside?", ["should i bring it in at night?"], True),
    ("What if I move it inside?", ["is it safe to eat?"], False),
    ("Is it safe to eat?", ["is it safe to eat?"], True),  # word for word, as before
    ("What if I don't water it this week?", ["how often should i water it?"], False),
    ("When should I harvest it?", [], False),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_pages_own_filter_line_runs_in_node_as_it_does_in_python():
    # the page's own line, run as the browser runs it: JS regex rules are not Python's
    src = TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]
    line = re.search(r"const covered = .*?;\n", src)
    assert line, "the follow-ups' covered() line moved"
    cases = [[q, starter_covers(q), said] for q, said, _ in CASES]
    script = (
        f"const cases = {json.dumps(cases)}; const out = [];"
        "for (const [q, p, said] of cases) {"
        f"{line[0]}"
        '  out.push(covered([q, p ? new RegExp(p, "i") : null])); }'
        "console.log(JSON.stringify(out));"
    )
    run = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [want for _, _, want in CASES]
