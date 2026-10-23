"""18 Oct judge ideas 5 and 5b: the plant's face beside its voice, its mood from the
answer, and "I did it" with a thank-you from the plant."""

import re

from herbtwin.schemas import CARE_ACTIONS
from herbtwin.web import style
from herbtwin.web.app import CHOICES, TEMPLATES
from tests.test_web_answer_page import _card, _unsure_record
from tests.test_web_answer_reveal import _rules


def _page(rec, voice=True, signed_in=False, accounts=False) -> str:
    return TEMPLATES.get_template("result.html").render(
        rec=rec, failed={}, asks=["question"], choices=CHOICES, max_question=500,
        chat=[], max_chat=500, check=None, reminder=None, compass_first="", spot_on=False,
        signed_in=signed_in, accounts=accounts, voice=voice,
    )  # fmt: skip


def _with_main(tmp_path, action):
    (tmp_path / action).mkdir(exist_ok=True)
    rec = _unsure_record(tmp_path / action)
    assert rec.answer is not None
    rec.answer.do = [_card(action, "today")]
    return rec


def _mood(page: str, where: str) -> str:
    box = page.split(where, 1)[1]
    return re.search(r'<svg class="face (\w+)"', box).group(1)


def test_the_face_beside_the_voice_wears_the_answers_mood(tmp_path):
    for action, mood in (("leave_normal", "content"), ("shelter", "cold"), ("water", "dry"),
                         ("prune", "trim"), ("treat_or_remove", "poorly"),
                         ("ask_first", "unsure")):  # fmt: skip
        (tmp_path / action).mkdir()
        page = _page(_with_main(tmp_path, action))
        assert _mood(page, 'id="voice"') == mood, action
        voice = page.split('id="voice"', 1)[1].split("</div>", 1)[0]
        # beside the button, never inside it: the voice script rewrites the button's text
        assert voice.index("<svg") < voice.index('<button type="button" class="hear">')
        assert 'aria-hidden="true"' in voice.split("<svg", 1)[1].split(">", 1)[0]


def test_with_the_voice_off_the_face_stays_on_its_own_in_the_answers_mood(tmp_path):
    # 21 Oct: the voice went (Kash: "yeah let's get rid then"); the faces stay
    for action, mood in (("leave_normal", "content"), ("shelter", "cold"), ("water", "dry"),
                         ("prune", "trim"), ("treat_or_remove", "poorly"),
                         ("ask_first", "unsure")):  # fmt: skip
        (tmp_path / action).mkdir()
        page = _page(_with_main(tmp_path, action), voice=False)
        assert 'id="voice"' not in page and 'class="hear"' not in page
        assert _mood(page, '<p class="plant-mood" id="plant-mood">') == mood, action
        face = page.split('<p class="plant-mood" id="plant-mood">', 1)[1].split("</p>", 1)[0]
        assert 'aria-hidden="true"' in face.split(">", 1)[0]  # decoration: the answer says it
        assert "<button" not in face and "<a " not in face  # no new button
        card = page.split('class="card main-action"', 1)[1].split("</section>", 1)[0]
        assert 'id="plant-mood"' in card  # in the main card, where the voice was
        assert len(re.findall(r'class="[^"]*\bprimary\b', card)) <= 1
    assert ".answer-page .voice .face, .answer-page .plant-mood .face { width: 48px;" in style.CSS


def test_i_did_it_gives_a_real_action_an_ending(tmp_path):
    (tmp_path / "shelter").mkdir()
    page = _page(_with_main(tmp_path, "shelter"))
    box = page.split('<div class="i-did" id="i-did" hidden>', 1)[1].split("</script>", 1)[0]
    assert '<button type="button" class="quiet">I did it</button>' in box
    # the thanks is a live status, filled on the tap; the plant is content once it's done
    assert '<p class="thanks" role="status" tabindex="-1">' in box and 'class="face content"' in box
    assert "Thanks for looking after me." in box  # thanks, never a promise of the outcome
    # the tapped button goes, so focus moves to the thanks; the thanks is never display:none
    assert "thanks.focus()" in box
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    thanks = next(b for at, sel, b in rules if not at and sel.endswith(".i-did .thanks"))
    assert "display: flex" in thanks
    # the existing "Did it work?" check-in keeps its own class
    assert page.count('class="i-did"') == 1 and 'class="did-it"' not in box


def test_nothing_to_have_done_no_i_did_it(tmp_path):
    for action in ("leave_normal", "dont_water", "ask_first", "check_pests", "other"):
        (tmp_path / action).mkdir()
        assert 'id="i-did"' not in _page(_with_main(tmp_path, action)), action


def test_the_face_and_leaves_only_move_when_motion_is_welcome():
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    ours = [r for r in rules if any(k in r[1] for k in (".face", ".i-did", ".voice"))]
    moving = [r for r in ours if "animation" in r[2]]
    assert {"face-talk", "leaf-out"} <= {w for _, _, b in moving for w in re.findall(r"[\w-]+", b)}
    for at, sel, _ in moving:
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
    # with motion off there are no leaves at all, only the thanks and the still face
    burst = [b for at, sel, b in ours if not at and sel.endswith(".i-did .burst")]
    assert burst and "display: none" in burst[0]


def test_sure_shows_the_green_badge(tmp_path):
    # #232 review nit: the top of the scale (a word badge since 21 Oct, not 2 steps)
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None
    rec.answer.level = "sure"
    page = _page(rec)
    assert '<span class="badge best">Our best read' in page and "badge check" not in page


def test_the_face_wobbles_only_while_the_voice_plays(tmp_path):
    page = _page(_unsure_record(tmp_path))
    voice = page.split('id="voice"', 1)[1].split("</section>", 1)[0]
    hook = voice.split("<script>")[-1].split("</script>", 1)[0]
    assert 'box.classList.toggle("speaking", on)' in hook
    assert 'audio.addEventListener("play", talk(true))' in hook
    assert '["pause", "ended", "error"]' in hook


def test_a_no_cure_answer_wears_the_poorly_face_and_says_why_compare_is_empty(tmp_path):
    # #230: "Remove it. There is no cure for this." empties Compare on purpose
    from herbtwin.answer import NO_CURE_HEADLINE

    (tmp_path / "treat_or_remove").mkdir()
    rec = _with_main(tmp_path, "treat_or_remove")
    assert rec.answer is not None
    rec.answer.headline, rec.answer.compare = NO_CURE_HEADLINE, []
    page = _page(rec)
    assert _mood(page, 'id="voice"') == "poorly"
    compare = page.split('<details class="compare fold', 1)[1].split("</details>")[0]
    assert "Not compared: there is no cure, so the choices don't apply." in compare
    assert "No 2-week forecast" not in compare


def test_a_split_panel_led_by_protect_it_wears_the_cold_face(tmp_path):
    # #233: a split leave-it panel can follow the twin to "Protect it" before a cold day
    (tmp_path / "shelter").mkdir()
    rec = _with_main(tmp_path, "shelter")
    assert rec.answer is not None
    rec.answer.level, rec.answer.in_ten = "fairly_sure", 5
    assert _mood(_page(rec), 'id="voice"') == "cold"


# 21 Oct, Kash: "why is the plant face cross?" Every action but four fell through to the
# unsure face, whose level dot eyes and flat mouth read as cross. Each action now names its
# mood, and no face is ever cross.
MOODS = {
    "leave_normal": "content", "dont_water": "content", "shelter": "cold", "water": "dry",
    "prune": "trim", "treat_or_remove": "poorly", "isolate": "poorly",
    "ask_first": "unsure", "check_pests": "unsure", "other": "unsure",
    "feed": "content", "mulch": "content", "repot": "content", "change_soil": "content",
    "rotate": "content", "humidity": "content", "move_light": "content",
}  # fmt: skip


def _face(mood: str) -> str:
    src = "{% from '_plant_face.html' import plant_face %}{{ plant_face(m) }}"
    return TEMPLATES.env.from_string(src).render(m=mood)


def test_every_action_names_its_mood(tmp_path):
    assert set(MOODS) == set(CARE_ACTIONS)
    # named in the template, so none reaches the fallback by accident
    html = (style.STATIC.parent / "templates" / "result.html").read_text(encoding="utf-8")
    moods = re.search(r"set moods = \{(.*?)\}", html, re.S).group(1)
    assert set(re.findall(r'"(\w+)": "\w+"', moods)) == set(CARE_ACTIONS)
    for action, mood in MOODS.items():
        assert _mood(_page(_with_main(tmp_path, action)), 'id="voice"') == mood, action


def test_the_unsure_face_looks_puzzled_never_cross():
    face = _face("unsure")
    assert 'd="M15 28 h10"' not in face  # no flat, cross mouth
    # one raised brow over a higher eye, and a small "?" beside the head
    assert '<path class="line brow"' in face and '<path class="mark"' in face
    eyes = re.findall(r'<circle class="eye" cx="[\d.]+" cy="([\d.]+)"', face)
    assert len(eyes) == 2 and eyes[0] != eyes[1]


def test_the_poorly_face_is_worried_not_cross():
    face = _face("poorly")
    brows = re.search(
        r'<path class="line brow" d="M([\d.]+) ([\d.]+) L([\d.]+) ([\d.]+) '
        r'M([\d.]+) ([\d.]+) L([\d.]+) ([\d.]+)"',
        face,
    )
    lx1, ly1, lx2, ly2, rx1, ry1, rx2, ry2 = map(float, brows.groups())
    # worried brows rise toward the middle; cross ones would fall toward it
    assert lx2 > lx1 and ly2 < ly1 and rx1 < rx2 and ry1 < ry2


def test_the_trim_face_holds_its_scissors():
    face = _face("trim")
    assert '<g class="snip">' in face
    assert face.split('<g class="snip">', 1)[1].split("</g>", 1)[0].count("<circle") == 2


def test_new_face_marks_use_theme_colours_and_keep_drawn_in_forced_colours():
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    plain = {s: b for at, s, b in rules if not at}
    assert "var(--" in plain[".answer-page .face .mark"]
    assert "var(--" in plain[".answer-page .face .snip"]
    forced = " ".join(
        s + b for at, s, b in rules if any("forced-colors" in a for a in at) and ".face" in s
    )
    assert ".mark" in forced and ".snip" in forced


def test_forced_colours_keep_the_face_drawn():
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    forced = " ".join(
        b for at, sel, b in rules if any("forced-colors" in a for a in at) and ".face" in sel
    )
    assert "CanvasText" in forced and "Canvas;" in forced


def test_the_face_is_big_enough_to_notice():
    # 19 Oct final look: the drawing read as about 20 px beside the voice button
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))

    def size(sel: str) -> int:
        body = next(b for at, s, b in rules if not at and s == sel)
        return int(re.search(r"width: (\d+)px", body).group(1))

    assert 40 <= size(".answer-page .voice .face, .answer-page .plant-mood .face") <= 48
    assert size(".answer-page .i-did .face") >= 36


KEEP = (
    '<p class="keep"><a href="/auth/sign-in">Sign in, then send this photo again, to keep '
    "this plant; you can then ask for an email when it's time to check again</a></p>"
)


def test_signed_out_i_did_it_says_how_to_keep_the_plant(tmp_path):
    # 19 Oct home pass: the one place a signed-out visitor sees what signing in is for.
    # Signing in does not carry this answer over, so it says to send the photo again
    page = _page(_with_main(tmp_path, "shelter"), accounts=True)
    # one plain line under What next's stops since 23 Oct, still only beside "I did it"
    box = page.split('<section class="next-step"', 1)[1].split("</section>", 1)[0]
    assert KEEP.replace("'", "&#39;") in box or KEEP in box
    # nothing is promised that does not happen: the email is asked for, never automatic
    assert "and get an email" not in page


def test_signed_in_or_without_accounts_nothing_new_shows(tmp_path):
    rec = _with_main(tmp_path, "shelter")
    assert 'class="keep"' not in _page(rec, signed_in=True, accounts=True)
    assert 'class="keep"' not in _page(rec, accounts=False)  # no sign-in to offer


def test_no_i_did_it_no_sign_in_line(tmp_path):
    page = _page(_with_main(tmp_path, "leave_normal"), accounts=True)
    assert 'id="i-did"' not in page and 'class="keep"' not in page


def test_the_sign_in_line_is_16px_in_the_themes_colours():
    css = (style.STATIC / "pages" / "answer.css").read_text()
    rule = re.search(r"\.answer-page \.i-did \.keep \{([^}]*)\}", css).group(1)
    assert (
        ".answer-page .next-step > p.keep { margin: 0; font-size: 16px; color: var(--muted-fg); }"
        in style.CSS
    )
    assert "font-size: 16px" in rule and "var(--muted-fg)" in rule


def test_the_dry_face_is_thirsty_not_grumpy(tmp_path):
    # flat-line eyes over a frown read as cross too (21 Oct): round eyes and a small "oh"
    face = _page(_with_main(tmp_path, "water")).split('class="face dry"', 1)[1].split("</svg>")[0]
    assert face.count('class="eye"') == 2 and "<ellipse" in face and 'class="drop"' in face
    assert " h5" not in face  # no flat eyes
