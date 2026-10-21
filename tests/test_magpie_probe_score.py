from __future__ import annotations

import json

from scripts.magpie_probe import probe, score


def test_normalise_spells_out_numbers_and_degrees():
    assert score.normalise("Dropping to 3°C, every 2 to 3 weeks!") == (
        "dropping to three degrees celsius every two to three weeks"
    )
    assert score.normalise("It's been 12 days") == "it's been twelve days"
    assert (
        score.normalise("5 cm of balanced fertilizer") == "five centimetres of balanced fertiliser"
    )


def test_number_words():
    assert score.number_words(42) == "forty two"
    assert score.number_words(105) == "one hundred and five"


def test_word_errors_counts_edits():
    assert score.word_errors("a b c", "a b c") == 0
    assert score.word_errors("a b c", "a x c") == 1
    assert score.word_errors("a b c", "a c") == 1
    assert score.word_errors("a b c", "a b c d") == 1


def test_every_line_spoken_form_matches_its_text():
    lines = json.loads(score.LINES.read_text())
    assert len(lines) == 12
    for line in lines:
        words = len(line["text"].split())
        assert 10 <= words <= 35, line["id"]
        # the spoken reference is what a perfect TTS + ASR round trip normalises to
        assert score.normalise(line["text"]) == line["spoken"], line["id"]
        for w in line["watch"]:
            assert f" {w} " in f" {line['spoken']} ", (line["id"], w)


def test_score_rows_wer_and_missed_words():
    lines = json.loads(score.LINES.read_text())
    l06 = next(x for x in lines if x["id"] == "L06")
    rows = [
        {
            "tn": "tn",
            "voice": "Aria",
            "line": "L06",
            "asr": l06["text"],
            "rtf": 0.1,
            "synth_s": 0.5,
            "audio_s": 5.0,
        },
        {
            "tn": "tn",
            "voice": "Leo",
            "line": "L06",
            "asr": l06["text"].replace("Salvia", "Sylvia"),
            "rtf": 0.2,
            "synth_s": 1.0,
            "audio_s": 5.0,
        },
        {"tn": "tn", "voice": "Leo", "line": "L01", "error": "RuntimeError: boom"},
    ]
    out = score.score_rows(rows, lines)
    by_voice = {v["voice"]: v for v in out["voices"]}
    assert by_voice["Aria"]["wer"] == 0
    assert by_voice["Leo"]["wer"] == round(1 / len(l06["spoken"].split()), 4)
    assert out["missed_words"] == [
        {"tn": "tn", "word": "salvia", "missed": 1, "of": 2, "where": ["Leo:L06"]}
    ]
    assert out["failures"] == [
        {"voice": "Leo", "line": "L01", "tn": "tn", "error": "RuntimeError: boom"}
    ]


def test_bare_c_is_not_celsius_and_homophones_apply():
    assert score.normalise("dropping to C this week") == "dropping to c this week"
    assert score.apply_homophones("time is tough", {"time": "thyme"}) == "thyme is tough"
    lines = json.loads(score.LINES.read_text())
    row = {"tn": "raw", "voice": "Aria", "line": "L10", "rtf": 1, "synth_s": 1, "audio_s": 1}
    row["asr"] = (
        "Time is tough, but my woody stems won't regrow if you cut into old wood. Trim only the soft green tips."
    )
    out = score.score_rows([row], lines)
    assert out["voices"][0]["wer"] == 0


def test_changed_lines_keeps_only_lines_the_normaliser_changed():
    lines = json.loads(score.LINES.read_text())
    normalised = {x["id"]: x["text"] for x in lines}
    normalised["L05"] = normalised["L05"].replace("3°C", "three degrees Celsius")
    normalised["L99"] = "a line not in this run"
    assert probe.changed_lines(lines, normalised) == {"L05": normalised["L05"]}
    assert probe.changed_lines(lines[:2], normalised) == {}


def test_as_normalised_swaps_in_normalised_clips_per_voice_and_line():
    def row(tn, voice, line, asr):
        return {
            "tn": tn,
            "voice": voice,
            "line": line,
            "asr": asr,
            "rtf": 1,
            "synth_s": 1,
            "audio_s": 1,
        }

    rows = [
        row("raw", "Aria", "L05", "dropping to C"),
        row("raw", "Aria", "L06", "salvia"),
        row("raw", "Leo", "L05", "to a sea"),
        row("tn", "Aria", "L05", "three degrees celsius"),
    ]
    out = score.as_normalised(rows)
    assert [(r["voice"], r["line"], r["asr"]) for r in out] == [
        ("Aria", "L05", "three degrees celsius"),
        ("Aria", "L06", "salvia"),
        ("Leo", "L05", "to a sea"),  # no normalised clip for Leo: the raw one stays
    ]
    assert {r["tn"] for r in out} == {"as_tn"}
