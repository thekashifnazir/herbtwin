"""25 Oct re-walk of rev 00115: after "Should I bring it in at night?" the follow-ups still
offered "What if I move it inside?", the same question in other words. Each suggestion says
what asking covers it, and one already covered is not offered again."""

import re

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
        ("What if I don't water it this week?", "How often should I water it?"),
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
    ],
)
def test_an_unrelated_question_leaves_it_offered(starter, asked):
    assert not re.search(starter_covers(starter), asked, re.IGNORECASE), (starter, asked)


def test_the_page_carries_each_suggestions_cover_and_the_script_uses_it():
    src = TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]
    assert '<button type="button" class="starter" data-covers="{{ starter_covers(q) }}">' in src
    assert "new RegExp(b.dataset.covers" in src
