"""Which questions to show under an answer: only those that would change it (spec
section 4). The answer never waits on them; a refine re-runs the advisor with the replies."""

from __future__ import annotations

from typing import Literal

from herbtwin.schemas import Answer, Observation

Question = Literal[
    "soil_feel", "last_watered", "changed", "question", "aspect", "soil_texture", "window"
]
WATERING = frozenset({"water", "dont_water"})
# Sudden decline: decline rose by 1 or more since a visit in the last 30 days, or, with no
# such visit, decline is this high (spec section 4).
SUDDEN_DECLINE = 2


def questions_for(
    answer: Answer, obs: Observation, last_decline: int | None = None, *, spot: bool = False
) -> list[Question]:
    out: list[Question] = []
    watering = any(c.action in WATERING for c in answer.do)
    if watering or answer.tell_me_key == "soil_feel":
        out += ["soil_feel", "last_watered"]
    rose = last_decline is not None and obs.decline - last_decline >= 1
    if rose or (last_decline is None and obs.decline >= SUDDEN_DECLINE):
        out.append("changed")
    if spot and answer.tell_me_key in ("aspect", "soil_texture"):
        out.append(answer.tell_me_key)  # the spot answer's questions (spot spec D73)
    if obs.setting == "indoor":
        from herbtwin.answer import NO_CURE_HEADLINE  # the answer module imports widely

        # which window and how close, in place of the compass: which way it faces is for a
        # plant outside (22 Oct, a gardener: "how do you tell light levels indoors?"); not
        # beside a retake or a no-cure answer, where the window can't help (review)
        out = [q for q in out if q != "aspect"]
        if not answer.photo_issue and answer.headline != NO_CURE_HEADLINE:
            out.append("window")
    out.append("question")
    return out
