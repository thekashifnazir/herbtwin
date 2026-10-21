# Magpie TTS probe: NVIDIA's open speech model on our plant lines (15 Oct 2026)

**Result: Magpie speaks our plant advice clearly once the text is normalised, but we could
not get it running on a Nebius GPU inside the $2 budget.** NVIDIA Magpie TTS Multilingual
357M (`nvidia/magpie_tts_multilingual_357m`, v2607, NVIDIA Open Model License) read 12
plant-persona lines in each of its 5 English voices. Parakeet TDT 0.6B v2 transcribed every
clip back. With NeMo's text normaliser the word error rate was **0.35%** (4 word errors in
about 1,150 words, all from one voice: two words split by a pause). Every plant name came back right in every voice: Salvia,
rosemary, oregano, lemon balm, thyme, chives, parsley. Without the normaliser
(`do_tts`'s default, `apply_TN=False`), every number and every "°C" came out garbled in all
5 voices, and the error rate was 3.1%. The intelligibility numbers come from a free run on
the Mac's CPU. Two Nebius GPU jobs both failed while installing (an image change, then a
package that has to be compiled). A third was not started because, at today's spot price, it
might have pushed spend past $2, so there are **no GPU speed numbers**.
The fix for both failures is in the scripts but has not been run. ElevenLabs stays the voice.

One line for the write-up: *NVIDIA's open Magpie TTS read our 12 plant-care lines in all 5
English voices with a 0.35% word error rate (checked by NVIDIA's own Parakeet ASR), and got
every herb name right, but only after text normalisation: without it every number and
"°C" was garbled.*

## What ran

- **Lines:** 12 plant-persona sentences, 15 to 23 words, written to include the hard
  cases: herb names, weekdays, a temperature (`3°C`), digits (`12 days`, `2 to 3 weeks`),
  British spellings (`centimetres`, `fertiliser`) and an em dash
  (`scripts/magpie_probe/lines.json`).
- **Voices:** the open checkpoint has **5** built-in English speakers (Aria, Jason, John,
  Leo, Sofia; the log reads `num_speakers=5`). It has no emotion control: `do_tts` takes
  only text, language, a text-normalisation flag, CFG and a speaker index. The brief's
  "10 voices plus Happy/Sad/Calm" looks like the hosted NIM's voice list, not these
  weights (not checked).
- **Round trip:** each clip resampled to 16 kHz and transcribed by
  `nvidia/parakeet-tdt-0.6b-v2`. `scripts/magpie_probe/score.py` puts both sides in a
  standard form: lower case, digits written as words, `°C` spelled out, American spellings
  and `cm` mapped to the British forms, and the homophone `time` for `thyme` allowed.
  It then counts word edits per voice and checks which watched words came back. A bare
  "C" is **not** read as "celsius", so a garbled temperature counts as an error.
- **Text normalisation:** NeMo's own English normaliser, built and called exactly as
  `do_tts(apply_TN=True)` builds and calls it (`scripts/magpie_probe/tn.py`). It changed 3 of
  the 12 lines (`3°C`, `12`, `2 to 3`). Those 3 lines were rendered again in every voice
  from the normalised text.
- **Where:** M4 Max CPU, fp32, NeMo 3.0.0, torch 2.14.1 (free). 75 clips, 6.4 minutes of
  audio. A few clips are kept outside git for listening later.

## Numbers

| | Raw text (`apply_TN=False`, the default) | With NeMo text normalisation |
|---|---|---|
| Word error rate, all 12 lines x 5 voices | 3.1% | **0.35%** |
| Number and °C lines spoken right | 0 of 15 | **15 of 15** |
| Plant names and weekdays heard right | 100% | 100% |
| Clips with any error | 17 of 60 | 2 of 60 |

The "with normalisation" row uses the normalised clips for the 3 changed lines and the raw
clips for the other 9, because normalisation leaves those 9 unchanged (`changed_lines` in
`probe.py`, `as_normalised` in `score.py`; both tested).

Word error rate by voice (all 12 lines):

| Voice | Raw text | Normalised | Note |
|---|---|---|---|
| Aria | 2.6% | **0.0%** | |
| Jason | 2.6% | **0.0%** | |
| Leo | 3.0% | **0.0%** | |
| Sofia | 3.0% | **0.0%** | |
| John | 4.3% | 1.7% | "to day", "window sill": a pause inside the word, heard as two |

What the raw text turned into (Parakeet's transcript):

| Line | Asked for | Heard |
|---|---|---|
| L05 | dropping to 3°C | "dropping to C" (4 voices), "to a sea" (John) |
| L09 | It's been 12 days | "It's been A days", "all day", "in days", "et day" |
| L11 | every 2 to 3 weeks | "every A to A weeks", "E to E", "E to A" |

The tokenizer also logs every em dash as an unknown character and drops it. It phonemises
some words and leaves others as letters, picking differently on each call (one clip had
`ˈθɝzˌdeɪ`, the next `THURSDAY`). The clips still came back word-perfect, but that is
where any variation between runs comes from.

Speed and audio (CPU only; GPU not measured):

| Measure | Value |
|---|---|
| Real-time factor, M4 Max CPU (synthesis time / audio length) | 1.73 median, 2.19 worst: slower than real time |
| Synthesis per line (6 to 7 s of audio, median) | 10.6 to 12.9 s median per voice |
| First call after load ("Hello from the garden.") | 2.0 s |
| Model load, warm cache (`import nemo` alone ~50 s) | ~60 s; 4.5 to 8.5 min on first use or while other downloads ran |
| Text normaliser build (amd64 container under emulation) | 65 s |
| Loudness | RMS -21.8 to -26.2 dBFS, peak 0.69 at most, no clipping |
| Failures | 0 of 75 clips |

## Nebius: what happened

Both GPU jobs used the pattern from the fine-tune probe: a Serverless AI job, preemptible
B300 (the only GPU in the project's quota), scripts injected with `--inject-file` and an
SSH copy-out route ready (`scripts/magpie_probe/{launch,run,fetch}.sh`).

| Job | Created to container start | What failed | Container time |
|---|---|---|---|
| `magpie-tts-probe` | 4 min 48 s (provisioning 1.3, VM start 1.4, 3.3 GB image pull 2.0) | `uv pip install` refused: the `pytorch/pytorch:2.14.1-cuda13.0` image now uses the system Python, which is marked externally managed (PEP 668) | 10 s |
| `magpie-tts-probe-2` | 5 min 17 s | `nemo-toolkit[tts]` pulls `pyopenjtalk` (Japanese G2P) and `nemo_text_processing` pulls `cdifflib`. Neither ships a Linux cp312 wheel, both need a C compiler, and the runtime image has none | 20 s |

The B300 itself was fine: torch 2.14.1+cu130 (built for sm_100) ran a CUDA matmul on it,
although the model card's hardware list stops at Hopper.

**Spend:** 2 jobs, about 12 minutes of VM lifetime, **30 seconds of container time**. The
B300 spot price was above $2 a GPU-hour today (a $2 price-cap policy was accepted but
blocked from scheduling). The billing calculator quoted $6.30 an hour, against the
"from $0.99" on the prices page and the ~$1.06 the 12 Oct jobs implied. So the estimate is
**$0.40 to $1.25** if all 12 minutes of VM time are billed at $2 to $6.30 an hour, and
about $0.05 if only container time is. The Nebius billing page has the
exact figure. With the conservative rate a third attempt (5 minutes of cold start plus about
5 minutes of work) would have gone past $2, so it was not started.

**Next run, if wanted** (about $1 to $1.50 at today's spot price): `run.sh` now installs
`build-essential` and `cmake` first and allows installs into the system Python. Launch with
`SYNTH_MIN=6 scripts/magpie_probe/launch.sh magpie-tts-probe-3 KEY.pub 15`, then
`score.py` on the `raw.jsonl` that `fetch.sh` copies back.

## Friction, for the tool-feedback write-up

Time lost in brackets.

1. **Spot price is hidden until you bid** (15 min). The prices page says B300 from $0.99,
   and earlier jobs paid about $1. Today the market was above $2. The only ways to see it
   were the billing calculator (which needs a project id flag the error message does not
   name) or creating a pricing policy and watching it go `BLOCKED`. Raising a bid needs
   care, because it is a spend decision.
2. **No short cost cap on jobs** (5 min). `nebius ai job create --timeout` has a 1-hour
   minimum, so a 15-minute budget needs your own watchdog (`launch.sh` cancels at a
   wall-clock cap; `run.sh` runs under `timeout`).
3. **Five minutes from create to container, every time** (10 min over 2 jobs).
   Provisioning, VM start and image pull happen again on every job, and you pay for that
   time. Fine for a batch job; it rules out on-demand speech without an always-on endpoint.
4. **The base image changed under us** (one job, ~6 min). The `pytorch/pytorch` 2.14
   images use a system Python marked externally managed (PEP 668); the older conda-based
   images did not. pip and uv refuse to install into it until told to
   (`UV_BREAK_SYSTEM_PACKAGES=1`).
5. **NeMo TTS needs a compiler on Linux** (one job, ~7 min, plus 6 min locally).
   `pyopenjtalk` (only for Japanese) and `cdifflib` build from source. A runtime CUDA image
   or `python:3.12-slim` cannot install `nemo-toolkit[tts]` and `nemo_text_processing`
   without `build-essential` and `cmake`. On the Mac it builds with Xcode, so it worked
   locally.
6. **Hidden downloads** (part of the 4.5 to 8.5 minute first load). The 1.47 GB checkpoint
   also pulls the 425 MB NanoCodec, a 377 MB WavLM speaker encoder, fetched twice (as
   `.bin` and `.safetensors`), and a ByT5 tokenizer: about 2.6 GB before the first word.
   WavLM is a training-time loss model that inference never uses.
7. **The default skips text normalisation, and failure is silent.** `do_tts` defaults to
   `apply_TN=False`, and that garbled every number and °C here. If the normaliser fails to
   start, Magpie logs a warning and speaks the raw text. `nemo_text_processing` needs
   `pynini`, which has no macOS wheel, so normalisation can only be tested on Linux (we
   used an amd64 container under emulation).
8. **The open checkpoint is smaller than the catalogue.** It has 5 voices and no emotion
   control, and zero-shot voice cloning was removed in this release. The model card's
   tested hardware list stops at H100.

What worked: the weights are not gated. NeMo 3.0.0 from PyPI installs next to torch 2.14.1
with no torch swap. The API is three lines (`from_pretrained`, `do_tts`, write the wav).
Parakeet made an easy, free intelligibility check. `nebius ai job create --dry-run`
catches bad flags before any spend. The B300 ran a cu130 torch build.

## Against ElevenLabs (the app's voice)

- **Intelligibility:** with normalisation, Magpie's open model was word-perfect in 4 of 5
  voices on our lines, herb names included. That is good enough for the app. ElevenLabs
  was not scored here; `score.py` can score its clips the same way (any engine's wavs,
  then the Parakeet transcripts).
- **Running it:** ElevenLabs is a hosted API billed per character, with no GPU or cold
  start on our side. Magpie needs our own GPU. A serverless job takes about 5 minutes to
  start, so speaking live means an always-on endpoint, which is too expensive until judging
  ends. On CPU it is 1.7 times slower than real time.
- **Text handling:** with Magpie we would have to run NeMo's normaliser ourselves (Linux
  only, about a minute to build). ElevenLabs handles numbers and units itself (its own
  claim, not measured here).
- **Voices:** Magpie has 5 English voices and no emotion control in the open weights.
- **Verdict:** keep ElevenLabs for the product. Magpie is a credible open option for
  batch-rendered audio (pre-recorded prompts, offline narration) if its text is normalised
  first.

## Files

- Code: `scripts/magpie_probe/` (`lines.json`, `probe.py`, `tn.py`, `score.py`,
  `run.sh`, `launch.sh`, `fetch.sh`), test `tests/test_magpie_probe_score.py`.
- Outside git: the run rows, summaries and the clips, in the session's scratch folder.
