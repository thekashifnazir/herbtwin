# NVIDIA models in HerbTwin: which does which job, and why (17 Oct 2026)

Every text model call in the app is NVIDIA Nemotron on Nebius Token Factory. Each job got
the model that measured best for it on our own evals, not the biggest one: **Super
decides, Nano talks.** Ultra, the largest, was tested for the advice and as a judge, and
does not advise; since 19 Oct it reads trusted gardening pages for the quote check. The photo step is the exception: four NVIDIA vision models were tested
against GLM-5.3-Flash and none was close on naming the plant.

## Who does what

| Job | Model | Why this one |
|---|---|---|
| The advice: the main action and why | **Nemotron 3 Super** (`nvidia/nemotron-3-super-120b-a12b`), asked 3 times | Of the three Nemotron 3 sizes on expert-labelled questions, no worse on the main action and clearly the least over-treatment (table below). Three asks: how many agree feeds the confidence shown |
| The follow-up chat ("Ask about this plant") and the plant's spoken line | **Nemotron 3 Nano** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), reasoning off | A short tool loop where speed matters: 10/10 on the scripted what-if check, in about half Super's time ([chat-on-nano.md](chat-on-nano.md)) |
| The trusted-page check: does a trusted gardening page say the same as the answer? | **Nemotron 3 Ultra** (`nvidia/Nemotron-3-Ultra-550b-a55b`), thinking off, up to six sentences per answer, a second short pass for each with conditions | It reads each sentence into a fixed form and code decides; the answer quotes the page, and confidence never changes. Pre-registered: round 5 4/435 false agrees on blind labels, round 6 0/191 on real pages |
| Reading the photo | GLM-5.3-Flash (not NVIDIA) | Names the species right 0.846 of the time on the live prompt; the best NVIDIA vision model, Nemotron 3.5 Super VL, got 0.627 (below) |

The hackathon track says "reach for Nemotron 3 Ultra when you need serious reasoning". We
tried it where reasoning matters most here, the advice, and it did not earn the seat: it
over-treats (below). As a judge it agrees with people as well as the other judges we have
tested, but our rule that a judge never shares a model family with what it grades (D11)
means it cannot grade the Nemotron advisor.

## The advice: Nano, Super and Ultra on the same questions

150 Stack Exchange gardening questions (the accepted expert answer gives the action), same
prompt (`7ba44f01d95b`), one ask each, scored on the main action. Over-treatment = the
model said "treat it" where the expert did not. 95% bootstrap intervals.

| Model | Main action matches the expert | Over-treatment | Cost (150 questions) |
|---|---|---|---|
| Nemotron 3 Nano 30B-A3B | 0.420 [0.340, 0.500] | 0.073 | $0.19 |
| **Nemotron 3 Super 120B-A12B** | **0.440** [0.360, 0.520] | **0.020** [0.000, 0.047] | $0.41 |
| Nemotron 3 Ultra 550B-A55B | 0.393 [0.313, 0.467] | 0.127 [0.080, 0.180] | $0.52 |

On 200 MIRAGE plant-care questions (a published benchmark): Super 0.435 [0.365, 0.505],
over-treatment 0.010 [0.000, 0.025]; **Ultra 0.423 [0.352, 0.495], over-treatment 0.082
[0.046, 0.122]** ($0.86; 4 of 200 answers stayed invalid after one repair).

So Ultra picks the main action no better than Super, and on both sets it recommends a
treatment the expert did not give six to eight times as often. The intervals for
over-treatment do not overlap on either set. Ultra does ask the right follow-up question
more often (when the expert asked one first: 0.935 against Super's 0.613 on Stack
Exchange), but a gardener told to spray a healthy plant is the worse error. For the same
reason it is not a tie-breaker for Super's asks: a tie is where the advice is least
certain, which is where an over-treating voice does the most harm. Most headline changes
were not ties anyway (next section).

The live app asks Super three times (temperatures 0, 0.7, 0.7) so that agreement can feed
the confidence. Panel scores on the earlier prompt: 0.427 [0.347, 0.500] Stack Exchange,
0.410 [0.340, 0.475] MIRAGE (`b1b-*`).

## Does Super use the plant model? (17 Oct)

`scripts/eval_plant_model.py`: 60 synthetic items (basil, parsley, rosemary, spearmint,
thyme x frost night, heavy rain, long dry spell, mild weather x a pot whose soil the person
described, a pot, a plant in the ground). Super's 3-ask panel answered each twice with the
PLANT MODEL block on and twice with it off; WEATHER, CARE FACTS and YOU TOLD US were
identical in both arms. Right answer: a gardener's rule per scenario (shelter, don't
water, water, leave it). $0.72 (the run's last progress line: 240 rows, $0.7180).

| | Plant model off | On | On minus off (95% CI) |
|---|---|---|---|
| Main action fits the rule | 0.925 [0.858, 0.983] | 0.958 [0.917, 0.992] | +0.033 [-0.033, +0.108] |
| Frost scenario: did not shelter | 0.200 [0.000, 0.400] | 0.033 [0.000, 0.100] | -0.167 [-0.367, +0.000] |
| Watered outside the dry spell | 0 | 0 | 0 |
| Treatment as main action | 0 | 0 | 0 |

- **Overall: no measurable difference** (the interval includes zero). Super reads the
  WEATHER block well on its own.
- **Where it mattered: basil before a 7 °C night.** Each herb's frost night was 3 °C below
  its own damage line: -7 to -13 °C for parsley, rosemary, spearmint and thyme, which
  Super sheltered in both arms; 7 °C for basil, which is damaged below about 10 °C.
  Without the plant model Super left basil out 6 of 6 times; with its "cold risk Monday
  if left out" line it sheltered 5 of 6. The whole frost effect rests on basil (3 items,
  6 rows an arm); the interval's upper end is exactly 0. It is the model's job in
  miniature: turning a forecast number into this plant's consequence.
- **Where the model arm did worse (4 of 60 items, each on one of its two repeats):**
  rosemary and thyme in pots in heavy rain said "shelter" (move the pot out of the rain,
  defensible for Mediterranean herbs, so the rule is strict there; the off arm said it
  as often across those herbs' rain items, so it is not the model's doing), and rosemary
  and thyme in the dry spell said "leave it" instead of "water".
- **Caveat:** each scenario's right answer is a rule on the same weather the plant model
  reads. This shows Super uses the model's forecast when given it, not that its advice is
  more correct against experts.

## Headline steadiness (17 Oct): measured, not fixed

One judge photo (healthy parsley) said "Cut it back." in one run and "Leave it for now" in
the next. `scripts/panel_steadiness.py` reads a photo once, then runs the advice on that
same reading 5 times. Two runs over 10 photos (the 5 judge samples and 5 of our garden
photos): **10 of 50 headlines differed from that photo's usual answer, both times.** Four
photos never changed in either run (flowering coriander, rosemary beetles, two garden
herbs); a fifth (garden chives) was steady in the first run only. The
changes sit on photos where two actions are both reasonable (healthy parsley: leave it or
cut it back; yellowing basil: cut it back or shelter it) and on two unclear garden photos.

- **Show the temperature-0 answer instead of the vote?** It looked steadier in the first
  run (chance two repeats agree 0.74 against the vote's 0.68) and less steady in the
  second (0.66 against 0.70): pooled 0.70 against 0.69. Temperature 0 is not repeatable
  on Token Factory, so no rule over the same three asks fixes this. The vote stays: it
  also keeps out treatments the temperature-0 answer alone would give (6 of 350 eval
  answers, none the other way).
- **Ultra as tie-breaker?** No: it over-treats (above), and most changes were 2-of-3
  majorities changing side, not ties.
- **What would work:** replay the first answer when the identical photo comes again (the
  record already carries `photo_sha256`). Not done here: it is a product choice, since it
  hides real disagreement rather than removing it. The answer already shows how many of
  the three asks agreed.

Rows: `data/eval/reports/2026-10-17-panel-steadiness-{1,2}.json` (coarse action per ask
and repeat, the headline shown; the first run also has Ultra's answer per repeat). The
second run was made with the temperature-0 rule as an unmerged experiment (it was
reverted, so that run cannot be repeated from the committed code); its shown action and
agreement count follow that rule. The comparison above uses the recorded asks of both
runs, which do not depend on the rule.

## Ultra as a judge

Free-text advice can only be graded by a model judge, and a judge is only trusted once it
agrees with people. The test: 375 Stack Exchange answer pairs where voters preferred one answer,
each judged in both orders (750 verdicts). Because people tend to prefer the earlier and
the longer answer, the judge must also beat chance on the pairs where the preferred
answer was the later one and where it was the shorter one (rule D18).

| Judge | Agrees with people | Same verdict both orders | Preferred was later | Preferred was shorter | Cost |
|---|---|---|---|---|---|
| **Nemotron 3 Ultra** | **0.750** [0.706, 0.789] | **0.908** | 0.687 [0.590, 0.778] | 0.665 [0.585, 0.748] | $1.73 |
| Claude Sonnet 5.5 (4 Oct) | 0.715 [0.672, 0.756] | 0.872 | 0.744 [0.655, 0.821] | 0.608 [0.525, 0.688] | subscription |
| Qwen3-14B, local, thinking off (4 Oct) | 0.757 [0.716, 0.796] | 0.877 | 0.756 [0.667, 0.839] | 0.629 [0.550, 0.713] | free |

Ultra passes D18 (both checks above 0.5). It agrees with people about as well as the
other two (the intervals overlap) and gave the same verdict in both orders most often
(over the 368 pairs with two valid verdicts). 7 of 750 verdicts were not valid JSON and
are counted separately (0.747 if counted as half). About $0.0023 a verdict. Under D11 it
may grade non-Nemotron answers (for example, a comparison of other models' advice), not
the live advisor's.

## The NVIDIA vision models we tried for the photo step

Same photos and scorer as GLM-5.3-Flash (the live photo model). Each model is compared
with GLM on the same observe prompt: the earlier prompt (`44ea8edaea55`, 12 to 15 Oct) or
the live one (`35b1b37a0ad4`, from 16 Oct). Species: 150 public photos, top 1. Decline:
120 public photos, balanced accuracy.

| Model | Where it ran | Prompt | Species right, top 1 | Spotting a declining plant | Time a photo |
|---|---|---|---|---|---|
| GLM-5.3-Flash (live) | Token Factory | live | **0.846** [0.785, 0.899] (149 scored) | **0.900** [0.842, 0.950] | 8.2 s |
| Nemotron 3.5 Super VL | Token Factory per token, reasoning off, $0.00055 a photo | live | 0.627 [0.547, 0.707] | 0.833 [0.774, 0.894] | **1.6 s** |
| GLM-5.3-Flash | Token Factory | earlier | 0.867 [0.81, 0.92] | 0.883 | 9.4 to 10.9 s |
| Nemotron 3 Nano Omni | Token Factory dedicated endpoint, 1x H100, about $0.60 | earlier | 0.587 [0.51, 0.67] | **0.975** | 1.6 to 1.9 s |
| Cosmos-Reason2-32B | Nebius AI Cloud job, 1x B300, vLLM, about $1 | earlier | 0.574 | 0.892 | |
| Cosmos-Reason1-7B | same job | earlier | 0.540 | not run | |

Naming the plant is the step everything else hangs on (the care facts, the season, the
plant model), so GLM keeps it. Nemotron Nano Omni was the best at spotting decline and 5x
faster, but never named lemon balm or garlic chives and failed the two-photo "did it
change?" check. Details: [nemotron-vision-probe.md](nemotron-vision-probe.md) and
[cosmos-reason-probe.md](cosmos-reason-probe.md).

Nemotron 3.5 Super VL, a Nemotron vision model new on Token Factory per token (not
listed on 12 Oct), is the best NVIDIA model on species and 5x faster than GLM there, but it never
named garlic chives, tarragon or soft shield fern and missed a third of the declining
plants. It must run with reasoning off: with reasoning on it filled the 4,096-token output
limit with no answer. Details: [nemotron-super-vl-probe.md](nemotron-super-vl-probe.md).

## Other NVIDIA models we tried

- **Nemotron 3.5 Lightning for the chat:** about twice as fast a reply and level with Nano
  on the what-if check, but it floods tool calls under `tool_choice: "required"` and adds
  US wording; the chat stays on Nano ([chat-on-lightning.md](chat-on-lightning.md)).
- **NVIDIA Magpie TTS for the plant's voice:** clear speech once the text is normalised
  (0.35% word errors, every plant name right), but not run on a Nebius GPU inside its
  budget; the live voice stays on ElevenLabs ([magpie-tts-probe.md](magpie-tts-probe.md)).

## Fine-tuning a small Nemotron

Nemotron 3 Nano 4B, LoRA-tuned on 242 of Super's answers that matched the experts (one
Nebius AI Cloud job on a B300, about $2), scored 0.400 against Super's 0.440 on Stack
Exchange and 0.420 against 0.435 on MIRAGE, both inside the noise. Tuning cut its own
over-treatment from 19% to 9% (Stack Exchange) and 18% to 2% (MIRAGE). It stays an eval
finding: serving it would need an always-on GPU, against about $0.0025 a question for
Super on Token Factory. Details: [fine-tune-nano-probe.md](fine-tune-nano-probe.md).

## Reproduce

From the main checkout (where `data/external` lives), with `HERBTWIN_ENV_FILE` set. Each
paid script needs `--yes-paid`, and a budget stop caps the spend (`panel_steadiness.py`
checks it after each repeat, so it can go over by one). The judge's quote assumed 400
output tokens a verdict and came in under the real $1.73: our run stopped at a $1.60
budget ($1.608 spent, from its stop line) and a second run with the same `--run-id`
finished from the cache ($0.122, the report's `spent_this_run_usd`).

```
uv run python scripts/eval_advice.py --set actions_se --limit 150 --backend tokenfactory \
  --model nvidia/Nemotron-3-Ultra-550b-a55b --workers 4 --budget 2.5 --yes-paid
uv run --with pyarrow python scripts/eval_advice.py --set actions_mirage --backend tokenfactory \
  --model nvidia/Nemotron-3-Ultra-550b-a55b --workers 4 --budget 1.2 --yes-paid
uv run python scripts/judge_pairs.py --judge tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b \
  --workers 4 --budget 1.6 --yes-paid --run-id 2026-10-17-pairs_se-nemotron-ultra
uv run python scripts/panel_steadiness.py docs/judges/samples/*.jpg --repeats 5 --budget 1 --yes-paid
```

The steadiness runs also used 5 garden photos that are not committed (Kash's own), and
the first run added `--side-model nvidia/Nemotron-3-Ultra-550b-a55b`; the command above
covers the 5 public judge samples only.

Reports: `data/eval/reports/{ultra-se-150-p7ba,ultra-mirage-p7ba,super-se-150-p7ba,
super-mirage-p7ba,nano30b-se-150,2026-10-17-pairs_se-nemotron-ultra,
2026-10-04-pairs_se-claude-claude-sonnet-5-5}.md`.

Photo-step reports (live prompt): the Files section of
[nemotron-super-vl-probe.md](nemotron-super-vl-probe.md).
