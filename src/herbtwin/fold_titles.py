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

from herbtwin.answer import NO_CURE_HEADLINE, shown_call
from herbtwin.confidence import RULE_LED
from herbtwin.plant_model import TIP, is_tender
from herbtwin.schemas import AnalysisRecord, Answer
from herbtwin.seasonal import season_sources


@dataclass(frozen=True)
class FoldTitle:
    kind: str  # the small label above the finding, so the fold is still findable: "Weather"
    title: str  # the finding, or the old category title when `found` is False
    peek: str = ""  # a quiet line under the title; "" for none
    found: bool = True


OLD_WEATHER_PEEK = "What the photo showed, the season and where the care facts came from"

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


def _sources(rec: AnalysisRecord, names: Mapping[str, str], indoor: bool) -> int:
    """The sources the fold names, counted as the page names them (said_by in result.html):
    one per site or set of notes, so two RHS pages are one source."""
    found: list[str] = []
    if rec.season and not indoor:
        found += season_sources(rec.season)
    if rec.pack:
        found += rec.pack.sources
    if rec.problem and rec.problem.page:
        found.append(rec.problem.page)
    shown: set[str] = set()
    for x in found:
        if x.startswith(("https://", "http://")):
            host = x.split("/")[2].removeprefix("www.")
            shown.add(names.get(host, host))
        elif x.startswith("docs/"):
            shown.add("our care notes")
        elif x.startswith("openplantbook:"):
            shown.add("Open Plantbook")
        elif x.startswith("openplantdb"):
            shown.add("OpenPlantDB")
        elif x:
            shown.add(x)
    return len(shown)


def _weather_finding(rec: AnalysisRecord) -> str | None:
    """Cold nights if left out, as the twin counts them (the chart's blue bands); with no twin,
    the rain due; None with no weather at all."""
    state, pack, env = rec.state, rec.pack, rec.environment
    base = next((s for s in state.strips if s.action == "do_nothing"), None) if state else None
    if base and base.days and pack:
        n = sum(1 for d in base.days if d.frost >= TIP)
        when = f"in {_span(len(base.days))}"
        # a tender plant's risk is chill, not frost (plant_model._cold)
        night, none = (
            ("cold night", "No cold nights") if is_tender(pack) else ("frosty night", "No frost")
        )
        return f"{n} {night}{'s' if n != 1 else ''} {when}" if n else f"{none} {when}"
    ahead = [d for d in env.days if d.is_forecast] if env else []
    if not ahead:
        return None
    mm = round(sum(d.rain_mm for d in ahead))
    when = f"in {_span(len(ahead))}"
    return f"{mm} mm of rain due {when}" if mm else f"No rain due {when}"


def weather_title(
    rec: AnalysisRecord, names: Mapping[str, str], weather_failed: bool = False
) -> FoldTitle:
    """The sources fold: what the weather holds for the plant, and how many sources the fold
    names. Indoors there is no weather to look at, so it says so instead."""
    obs = rec.observation
    indoor = obs is not None and obs.setting == "indoor"
    n = _sources(rec, names, indoor)
    count = f" · {n} source{'s' if n != 1 else ''}" if n else ""
    if indoor:
        return FoldTitle(f"Photo and sources{count}", "Indoors: no weather needed")
    if weather_failed or rec.environment is None:
        return FoldTitle(f"Weather{count}", "No forecast this time")
    said = _weather_finding(rec)
    if said is None:  # weather, but no day ahead of the photo to count
        return FoldTitle("", "Weather, forecast and sources", OLD_WEATHER_PEEK, found=False)
    return FoldTitle(f"Weather{count}", said)


def why_title(rec: AnalysisRecord, label: Mapping[str, str]) -> FoldTitle:
    """The why fold: how many advisors said the plan at the top, or that our rules chose it.
    Falls back to the old title when neither is true."""
    a = rec.answer
    best = a is not None and a.level == "sure"
    kind = "Why it's our best read" if best else "Why we're not sure"
    if a is None or not a.do or not a.runs:
        return FoldTitle(kind, kind, found=False)
    calls = [shown_call(a, r.primary, label) for r in a.runs]
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


def compare_title(a: Answer, no_cure: bool) -> FoldTitle:
    """The Compare fold: which choice beat leaving it on the twin, then what did nothing extra
    or made it worse. Falls back to the old title with no verdict to report."""
    kind = "Compare all choices · next 2 weeks"
    if not a.compare:
        if no_cure:
            return FoldTitle("Compare all choices", "No cure, so the choices don't apply")
        return FoldTitle(kind, "Compare all choices (next 2 weeks)", found=False)
    by: dict[str, list[str]] = {"better": [], "same": [], "worse": []}
    for r in a.compare:
        if r.action != "leave_normal" and r.action in DOING and r.vs_leaving_it in by:
            by[r.vs_leaving_it].append(DOING[r.action])
    better, same, worse = by["better"], by["same"], by["worse"]
    if not (better or same or worse):
        return FoldTitle(kind, "Compare all choices (next 2 weeks)", found=False)
    title = f"{_cap(better[0])} beats leaving it" if better else "Nothing beats leaving it"
    more = []
    if len(better) > 1:
        more.append(f"{_join(better[1:])} {'helps' if len(better) == 2 else 'help'} too")
    if same:
        more.append(f"{_join(same)} {'does' if len(same) == 1 else 'do'} nothing extra")
    if worse:
        more.append(f"{_join(worse)} {'makes' if len(worse) == 1 else 'make'} it worse")
    return FoldTitle(kind, title, _cap("; ".join(more)))


def fold_titles(
    rec: AnalysisRecord,
    label: Mapping[str, str],
    names: Mapping[str, str],
    weather_failed: bool = False,
) -> dict[str, FoldTitle]:
    """Every fold's title for one answer: "weather", "why" and, with an answer, "compare".
    `label` is the page's card labels, `names` its source names (result.html)."""
    a = rec.answer
    out = {"weather": weather_title(rec, names, weather_failed), "why": why_title(rec, label)}
    if a is not None:
        out["compare"] = compare_title(a, a.headline == NO_CURE_HEADLINE)
    return out
