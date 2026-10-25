# Results: first-time users on the live site, Toloka (run 23 Oct 2026)

Scored once, against `data/eval/prereg/2026-10-22-toloka-site-study.md` (as amended 23 Oct).
Aggregates and paraphrases only; the raw export stays in `data/external/` (off git).

## The run

- Pipeline "Site test 22 Oct - USE THIS ONE", task t01, sample **Rosemary beetles**, overlap 11.
- **11 workers, 11 distinct annotator ids.** Opened 12:04–17:57 UTC, last submitted 18:12 UTC, 23 Oct.
- **Site revision:** 10 workers on `herbtwin-00098-5dd`. **Deviation:** the 11th worker opened the
  task at 17:57 UTC, after a deploy at 16:32–16:34 UTC (`herbtwin-00100-2zj`: "What can I grow
  here?" switched off, cap re-applied). The answer page for this sample was not changed by it.
  That worker's row is kept.
- **Broken task:** none. Every worker reached an answer page and filled every field.
- **Filler:** no worker was excluded.

## Reach

**11 of 11** reached an answer page (Q2 = yes). No limit pages, no errors.

## Reference headline

"Pick the beetles off by hand." (5 of 11) is the answer page's action heading for this sample
that day. It ties with the plant's name, which 5 also pasted (Rosemary / Salvia rosmarinus) but
which names no action. 1 pasted "Curled parsley", the home page's example card.

## Measures

Two fresh blind labellers, each seeing only the reference headline, Q3–Q6 and the rules.
**They agreed on all 44 labels** (11 workers × 4 measures).

| | Measure | Result | Wilson 95% | Bar | |
| --- | --- | --- | --- | --- | --- |
| **P1** | Right action | **6 / 11 (55%)** | 28%–79% | ≥ 70% | **missed** |
| S1 | Found the source | 6 / 11 (55%) | 28%–79% | ≥ 60% | missed |
| S2 | Used the Ask box | 9 / 11 (82%) | 52%–95% | ≥ 70% | **met** |
| S3 | Check next | 4 / 11 (36%) | 15%–65% | reported | |

- **P1 misses (5):** 3 gave a watering instruction instead of the beetle action (one "water it
  today", two "don't water it"), 1 described the website in general, and 1 named the "answer 3
  quick questions" step.
- **S1 misses (5):** vague answers ("a database", "gardening sources", the site's own name) or a
  place on the page with no source named. The self-ratings were higher: 8 said "found".
- **S2 misses (2):** one wrote a single word rather than a question; one watering question
  ("how often do I water") was answered as off topic.

## S4 Clarity and trust (1–5)

- Clarity: median **4**; counts 3: 1, 4: 5, 5: 5.
- Trust: median **4**; counts 3: 1, 4: 6, 5: 4.

## S5 Confusions (one subagent's coding)

| Theme | Count | Paraphrase |
| --- | --- | --- |
| Nothing confused me | 3 | |
| Slow or missing model reply | 3 | the chat reply was slow enough to seem lost; one question never answered |
| Page too busy or complex | 2 | too much information; complex for a first visit |
| Unclear where the answer ends | 1 | only the top part, or the details below too? |
| Asking questions feels complicated | 1 | the Ask steps felt like a lot |
| "Plant twin" unexplained | 1 | didn't know what the twin meant |

## S6 Time

Median **890 s (14.8 min)**, range 312–1,390 s. The task was priced for 5 minutes.

## Who took part

Phone 7, computer 4. Plants looked after: none 3, one to five 5, more than five 3.

## What we changed (24 Oct)

- **#517:** the action is now the answer page's biggest words, a step above the plant's name.
  Under a job the twin can't weigh, the twin's verdict reads "Nothing else is needed for water
  or frost" and says it can't model pests, instead of "Nothing beats leaving it". The twin
  explains itself in plain words, "Where this came from" is marked off, and the card ends with
  "That's your answer". Asked how often to water while the answer says hold off, the chat
  now says how often.
- **#518:** a chat source note such as "(RHS)" no longer dangles once its sentence is cut.
- Not re-tested with people: the Toloka credit is spent.

## Limits

One sample, one site revision (bar one worker), 11 paid strangers using our sample photo, not a plant of their own.
A usability probe, not a rate: at n = 11 the intervals are wide.
