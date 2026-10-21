# Expert review: a professional gardener grades 3 answers (19 Oct 2026)

**What:** a paid, independent check of the app's advice by a professional gardener with
more than 3 years of hands-on experience, hired through Tendem. Cost: **$47.86**. The
reviewer gave permission to quote the grades and short excerpts; their identity is not
published.

**Scope:** 3 public Creative Commons sample photos: s012 oregano, s014 mint, s052 basil.
The brief ([2026-10-19-expert-review-brief.txt](2026-10-19-expert-review-brief.txt)) is
the exact advice text the gardener graded. It lists 5 photos; the purchased scope was
later cut to 3, so s021 (rosemary) and s063 (sage) were **not reviewed**. The context
given was "a UK garden in mid-October" and nothing else about the owner.

**Raw result:** [2026-10-19-expert-review.csv](2026-10-19-expert-review.csv), one row per
photo, as delivered.

## Verdicts

| Photo | Our headline | First action | Overall (1 to 5) |
| --- | --- | --- | --- |
| s012 oregano | Move it to better light. | Acceptable | 3 |
| s014 mint | Keep it away from your other plants. | Acceptable | 3 |
| s052 basil | Cut it back. | Acceptable | 3 |

None was graded Wrong or Harmful; none was graded what the gardener would say themselves (5).

## The 4 points, and what we changed (plus drainage, added later)

1. **Season-blind pruning (s012).** "trim the leggy, woody stems to encourage bushier
   growth" sat beside our own "Dies back further and rests through winter". The gardener's
   view: only a light tidy of the longest stems and dead base material suits October.
   **Changed:** for perennial herbs that rest through the UK winter (oregano, thyme, mint,
   sage, rosemary, chives, garlic chives, tarragon, lemon balm), from September to February
   no line on the page cuts for growth. An advisor's closing clause that does is dropped from
   the reason and from the reply to a question; a sentence with no clean place to cut goes
   whole, and one that holds the cut off ("wait until spring") stays. A sourced "if you do"
   line written for the growing season ("keeps mint bushy") is not shown. A cut-back card becomes "Give it a light tidy"
   with "only a light tidy now: dead material and the longest straggly tips. The main
   cut-back waits for spring." From March to August the same advice is unchanged.
2. **A blanket "don't water" (s014).** "Don't: Water it. Worse than leaving it." was
   "unsupported by the photo; mint likes moist soil and pots under cover can dry out".
   **Changed:** when the soil is unknown (nothing told, none visible in the photo), the card
   is headed "Check first: Water only if the top of the compost is dry" ("soil" for a plant
   in the ground), with the twin's
   comparison kept under it. The spoken line and the chat say the same check.
3. **The wrong priority for a tender herb (s052).** "Cut it back." led a stressed outdoor
   basil in mid-October, with cold protection left for later in the week. The gardener said
   to bring the pot indoors now. **Changed:** a tender herb (harmed by a chill above
   freezing, such as basil, and only from a verified plant pack) outside from October to
   March, with a cold night ahead or a struggling look outdoors, now leads with "Bring it
   indoors to a bright windowsill." A bed-grown plant gets "Protect it from the weather."
   instead, with "cover it before they come". Cutting back moves to Also do. Treating a
   problem, watering and "leave it" keep their place.
   **Confidence** falls with no weight refitted. When no advisor chose the lead, agreement
   reads 0 of 3 and is given the fitted "1 of 3" weight: a rule extended by hand, since the
   panel never returned 0 before and no eval row has it (`scripts/fit_confidence.py` now
   counts 0 with 1, so a refit matches). The advisor's own sureness is read as low, as when
   the twin leads. The page notes that the advisors led with cutting it back.
4. **Out of proportion (s014).** "Keep it away from your other plants" for one insect and
   no damage was "harmless but excessive". **Changed:** isolation leads only for damage the
   photo shows, a pest in numbers, or a problem the photo check names. Otherwise the
   headline is "Check under the leaves, and flick off any insects you find.", and an
   isolation card is dropped from Also do.
5. **Drainage (s052), added later (#298).** The gardener's first step went on: "check the
   tray: empty it if there is any water in it". It was first left out, since standing
   water was not visible in the photo. **Changed:** every "Bring it indoors to a bright
   windowsill." for a plant not in the ground now adds its own line, "If it stands in a
   tray or saucer, tip out any water there: roots left sitting in water can rot." A bed
   never gets it.

Each change has a test in `tests/test_expert_review.py` that fails without it. The tests
rebuild the gardener's quoted lines from the brief.

## Not changed, and caveats

- **Precision of confidence and weather (general comment).** The gardener found "7 in 10"
  and weather claims "more precise than a single photo allows". The in-ten figures are
  measured hit rates. This review gives no new data to recalibrate them, so they stand.
- **Tendem's own independent-check note** flagged caveats around the consistency of the
  s052 verdict and grade, and around the general comment on cold protection. Quote the
  grades and short excerpts only, as the permission covers.
- **Small sample.** 3 answers from 1 reviewer is evidence of specific faults, not a
  measured quality rate.
