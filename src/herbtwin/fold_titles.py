"""The answer's shut folds say what each one found, not what kind of thing is inside (22 Oct,
Kash chose "B2", after Perplexity Finance, where each section's title is its headline
finding, and Turo, where a shut row shows its key value).

Each title is built from the answer's own data, never a model call. With nothing true to say,
`found` is False and the page keeps the old category title: never an invented number. Pure:
the template draws the summary from these words.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from herbtwin.answer import NO_CURE_HEADLINE, TENDER_HEADLINE, shown_call
from herbtwin.confidence import RULE_LED
from herbtwin.plant_model import TIP, is_tender
from herbtwin.schemas import AnalysisRecord, Answer, CompareRow
from herbtwin.twin_chart import _windows, plain_why


@dataclass(frozen=True)
class FoldTitle:
    kind: str  # the small label above the finding, so the fold is still findable
    title: str  # the finding, or the old category title when `found` is False
    peek: str = ""  # a quiet line under the title; "" for none
    found: bool = True
    # the evidence fold only: the lines it lists, in order, and its weather line's words. The
    # page draws exactly these lines and its label counts them: one list for both
    holds: tuple[str, ...] = ()
    weather: str = ""


EVIDENCE = "What we went on"
EVIDENCE_PEEK = "What the photo showed, the season and where the care facts came from"

# each choice as the subject of a sentence: "Protecting it beats leaving it" (the card labels
# are orders: "Protect it (shelter or bring in)")
DOING = {
    "water": "watering",
    "dont_water": "holding off watering",
    "move_light": "moving it to better light",
    "shelter": "protecting it",
    "treat_or_remove": "treating it",
    "prune": "cutting it back",
    "leave_normal": "leaving it",
    "ask_first": "checking first",
    "feed": "feeding",
    "repot": "repotting",
    "change_soil": "refreshing the soil",
    "check_pests": "checking for pests",
    "isolate": "keeping it apart",
    "mulch": "mulching",
    "humidity": "raising humidity",
    "rotate": "turning the pot",
}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _span(n: int) -> str:
    return "2 weeks" if n == 14 else f"{n} days"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _weather_finding(rec: AnalysisRecord) -> tuple[str, str] | None:
    """(title, the fold's weather line). Cold spells if left out, counted as the twin chart
    marks them: one per run of cold nights, its snowflakes (site walk 2, 22 Oct: "11 cold
    nights" over a chart with 3 marks). With no twin, the rain due; None with no day ahead."""
    state, pack, env = rec.state, rec.pack, rec.environment
    base = next((s for s in state.strips if s.action == "do_nothing"), None) if state else None
    if base and base.days and pack:
        nights = [i for i, d in enumerate(base.days) if d.frost >= TIP]
        n = len(_windows(nights))
        when = f"in {_span(len(base.days))}"
        # a tender plant's risk is chill, not frost (plant_model._cold)
        spell, none = (
            ("cold spell", "No cold nights") if is_tender(pack) else ("frosty spell", "No frost")
        )
        said = f"{_plural(n, spell)} {when}" if n else f"{none} {when}"
        # the nights too, inside, so one long spell never reads as a short one (r5: 13 in a row)
        more = f" ({len(nights)} nights in all)" if len(nights) > n else ""
        return said, f"{said} if left out{more}"
    ahead = [d for d in env.days if d.is_forecast] if env else []
    if not ahead:
        return None
    mm = round(sum(d.rain_mm for d in ahead))
    when = f"in {_span(len(ahead))}"
    said = f"{mm} mm of rain due {when}" if mm else f"No rain due {when}"
    return said, said


def _holds(rec: AnalysisRecord, indoor: bool, weather: bool) -> tuple[str, ...]:
    """The lines the evidence fold lists, in its order (result.html draws these and no others)."""
    a, pack = rec.answer, rec.pack
    held = {
        "photo": rec.observation is not None,
        "weather": weather,
        "season": rec.season is not None and not indoor,
        "facts": pack is not None and bool(pack.sources),
        "check": rec.problem is not None,
        "assumes": a is not None and bool(a.assumptions),
    }
    return tuple(k for k, on in held.items() if on)


def weather_title(rec: AnalysisRecord, weather_failed: bool = False) -> FoldTitle:
    """The evidence fold: what we went on, led by what the weather holds for the plant, and
    how many things the fold lists (site walk 2, 22 Oct: "Weather · 3 sources" held no
    weather, and counted sources, not its lines). Indoors there is no weather to look at."""
    obs = rec.observation
    indoor = obs is not None and obs.setting == "indoor"
    no_forecast = weather_failed or rec.environment is None
    said = None if indoor or no_forecast else _weather_finding(rec)
    holds = _holds(rec, indoor, said is not None)
    kind = f"{EVIDENCE} · {_plural(len(holds), 'thing')}" if holds else EVIDENCE
    if indoor:
        return FoldTitle(kind, "Indoors: no weather needed", holds=holds)
    if no_forecast:
        return FoldTitle(kind, "No forecast this time", holds=holds)
    if said is None:  # weather, but no day ahead of the photo to count
        return FoldTitle("", EVIDENCE, EVIDENCE_PEEK, found=False, holds=holds)
    # a line in the fold, after a colon like its others: "Weather: no frost in 2 weeks if left out"
    return FoldTitle(kind, said[0], holds=holds, weather=said[1][:1].lower() + said[1][1:])


def why_title(rec: AnalysisRecord, label: Mapping[str, str]) -> FoldTitle:
    """The why fold: how many advisors said the plan at the top, or that our rules chose it.
    Falls back to the old title when neither is true."""
    a = rec.answer
    best = a is not None and a.level == "sure"
    kind = "Why it's our best read" if best else "Why we're not sure"
    if a is None or not a.do or not a.runs:
        return FoldTitle(kind, kind, found=False)
    calls = [shown_call(a, r.primary, label, advisor=True) for r in a.runs]
    main = shown_call(a, a.do[0].action, label)
    said, n = calls.count(main), len(calls)
    plan = main.split(" (")[0].lower()  # "Protect it (shelter or bring in)": "protect it"
    if not plan:
        return FoldTitle(kind, kind, found=False)
    ruled = a.headline == NO_CURE_HEADLINE or any(
        f.name == "advisor" and f.detail == RULE_LED for f in a.factors
    )
    if not said:  # no advisor said the plan at the top
        if ruled:
            return FoldTitle(kind, f"Our rules chose: {plan}")
        return FoldTitle(kind, kind, found=False)
    if n == 1:
        return FoldTitle(kind, f"The advisor said: {plan}")
    if said == n:
        return FoldTitle(kind, f"{n} advisors agreed: {plan}")
    return FoldTitle(kind, f"{said} of {n} advisors said: {plan}")


def _join(xs: list[str]) -> str:
    return " and ".join(xs[:2])


# the twin models moving it to better light as a little faster drying (stages/twin.py), never
# the light itself: under "Bring it indoors to a bright windowsill." its "Moving it to better
# light does nothing extra" read as against the advice (23 Oct judge walk, a flowering basil)
NO_LIGHT = "the twin can't model light, so moving it shows no change here"


def light_unmodelled(a: Answer) -> bool:
    """The advice sends it to the light (our bright windowsill, or a Move it to better light
    card) and the twin rates moving it the same as leaving it. Only then: other answers read
    as before (the rosemary beetle sample is in a rater study, 23 Oct)."""
    to_light = a.headline == TENDER_HEADLINE or any(c.action == "move_light" for c in a.do)
    same = any(r.action == "move_light" and r.vs_leaving_it == "same" for r in a.compare)
    return to_light and same


def row_why(r: CompareRow, a: Answer) -> str:
    """A Compare row's reason as a plain sentence; moving it to better light says the twin
    can't model light where light_unmodelled."""
    if r.action == "move_light" and light_unmodelled(a):
        return _cap(NO_LIGHT) + "."
    return plain_why(r.why)


def twin_off_job(a: Answer) -> bool:
    """The card's main job is one the twin does not compare (pick off the beetles): the twin
    only weighs water and frost around it."""
    main = a.do[0].action if a.do else None
    return main is not None and main not in {"leave_normal", "dont_water"} | {
        r.action for r in a.compare
    }


# under "Pick the beetles off by hand", "Nothing beats leaving it" read as "leave it alone":
# 3 of 11 Toloka workers gave a watering instruction as the answer (site study, 23 Oct)
NOTHING_ELSE = "Nothing else is needed for water or frost"


def compare_title(a: Answer, no_cure: bool) -> FoldTitle:
    """The Compare fold: which choice beat leaving it on the twin, then what did nothing extra
    or made it worse. Falls back to the old title with no verdict to report."""
    kind = "Compare all choices · next 2 weeks"
    if not a.compare:
        if no_cure:
            return FoldTitle("Compare all choices", "No cure, so the choices don't apply")
        return FoldTitle(kind, "Compare all choices (next 2 weeks)", found=False)
    by: dict[str, list[str]] = {"better": [], "same": [], "worse": []}
    no_light = light_unmodelled(a)
    for r in a.compare:
        if no_light and r.action == "move_light":
            continue  # said as NO_LIGHT, in place of "does nothing extra"
        if r.action != "leave_normal" and r.action in DOING and r.vs_leaving_it in by:
            by[r.vs_leaving_it].append(DOING[r.action])
    better, same, worse = by["better"], by["same"], by["worse"]
    if not (better or same or worse or no_light):
        return FoldTitle(kind, "Compare all choices (next 2 weeks)", found=False)
    # the main job is not one the twin compares (pick off the beetles): a better choice is an
    # extra, never the title's lead (site walk 2, r3: "Watering beats leaving it")
    off_job = twin_off_job(a)
    extra = bool(better) and off_job
    if extra:
        title = f"{_cap(_join(better))} {'helps' if len(better) == 1 else 'help'} too"
    elif better:
        title = f"{_cap(better[0])} beats leaving it"
    else:
        title = NOTHING_ELSE if off_job else "Nothing beats leaving it"
    more = []
    if len(better) > 1 and not extra:
        more.append(f"{_join(better[1:])} {'helps' if len(better) == 2 else 'help'} too")
    if same:
        more.append(f"{_join(same)} {'does' if len(same) == 1 else 'do'} nothing extra")
    if no_light:
        more.append(NO_LIGHT)
    if worse:
        more.append(f"{_join(worse)} {'makes' if len(worse) == 1 else 'make'} it worse")
    return FoldTitle(kind, title, _cap("; ".join(more)))


def fold_titles(
    rec: AnalysisRecord, label: Mapping[str, str], weather_failed: bool = False
) -> dict[str, FoldTitle]:
    """Every fold's title for one answer: "weather" (the evidence fold), "why" and, with an
    answer, "compare". `label` is the page's card labels (result.html)."""
    a = rec.answer
    out = {"weather": weather_title(rec, weather_failed), "why": why_title(rec, label)}
    if a is not None:
        out["compare"] = compare_title(a, a.headline == NO_CURE_HEADLINE)
    return out
