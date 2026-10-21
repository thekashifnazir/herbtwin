# Evaluation methods borrowed from other advice domains

How medicine, law, tutoring and customer service evaluate advice quality, and what plan 2
takes from them. Swept 3 Oct 2026. Verified against arXiv or publisher pages unless marked
† (paywalled, cited from memory, spot-check before relying on it).

## 1. Medical advice evaluation

- **Arora et al. 2025, HealthBench, OpenAI**, arxiv.org/abs/2505.08775. 5,000 conversations, 48,562 physician-written example-specific rubric criteria from 262 physicians, each weighted −10 to +10; score = earned points / max positive points, clipped to 0 to 1. Context-seeking and responding under uncertainty are first-class themes. Grader validated by macro-F1 on 60,896 criterion-level labels against physician-to-physician agreement of 55 to 75%. Borrow: weighted criteria with negative items; validate the judge against the human ceiling.
- **Singhal et al. 2025, Med-PaLM 2, Nature Medicine**, arxiv.org/abs/2305.09617. 12-axis per-answer rubric that splits harm into extent and likelihood and separates omission from irrelevant content; 3 physician raters per item, 4 on adversarial items. Borrow: two-part harm anchor; overlap of 3, 4 on hard cases.
- **Bedi et al. 2025, MedHELM, Stanford**, arxiv.org/abs/2505.23802. An LLM jury agreed with clinicians at ICC 0.47, above clinician-to-clinician ICC 0.43. Borrow: report ICC beside kappa and frame judge agreement relative to the human ceiling.
- MCQ accuracy does not predict long-form quality (Med-PaLM 2 scored 86.5% on MedQA yet physicians flagged harm and omission in free text). Keep species ID as the only closed-form line.

## 2. Other advice domains

- **Magesh et al. 2024, Hallucination-free? Assessing legal AI research tools**, arxiv.org/abs/2405.20362. Scores groundedness separately from correctness: correct-and-grounded, correct-but-misgrounded, hallucinated, incomplete. Commercial tools hallucinated 17 to 33%. Borrow: split our evidence line.
- **Maurya et al. 2025, MRBench, NAACL**, arxiv.org/abs/2412.09416. 8 tutoring dimensions on a 3-level scale (yes / to some extent / no), mean Cohen's kappa 0.71. Small open judges correlated −0.37 to 0.11 with humans. Borrow: 3-level anchors; never assume a judge is usable without validating it.
- **Yao et al. 2024, tau-bench**, arxiv.org/abs/2406.12045. Customer-service agents scored by pass^k over repeated trials. Borrow: test-retest of the pipeline is a headline metric.
- FinBen (arxiv.org/abs/2402.12659) and LegalBench† are classification-only; nothing to borrow.

## 3. Rubric design

- **Preston and Colman 2000**†, Acta Psychologica. Reliability poor at 2 to 4 points, rises to about 7, flat beyond; raters prefer 5 to 7. 5 is defensible; 3 only for binary-shaped items.
- **Smith and Kendall 1963, behaviourally anchored rating scales**†. Each scale point described by an observable behaviour, not an adjective.
- **Shankar et al. 2024, Who validates the validators?**, arxiv.org/abs/2404.12272. Criteria drift: graders refine criteria while grading. Pilot-grade real outputs before freezing.
- **Thakur et al. 2024, Judging the judges**, arxiv.org/abs/2406.12624. Percent agreement hides different score assignments; use chance-corrected statistics; LLM judges skew lenient.
- **Wallach et al. 2025, Evaluating generative AI is a social-science measurement challenge, ICML**, arxiv.org/abs/2502.00561. Systematise, operationalise, validate each construct; show each rubric line is not a proxy for another.
- Weighted binary checklists (HealthBench) and 3-level scales (MRBench) both beat unanchored Likert on agreement.

## 4. Crowd rating quality control

- **Douglas et al. 2023, Data quality in online human-subjects research, PLOS ONE**, doi:10.1371/journal.pone.0279720. About 500 per platform; Prolific and CloudResearch had the best attention-check pass rates and lowest cost per quality respondent ($1.90 vs MTurk $4.36).
- **Prolific researcher help**, researcher-help.prolific.com. Minimum pay £6 or $8 an hour, recommended £9 or $12; rejections only for failed attention checks under stated conditions.
- **Ustalov et al. 2024, Crowd-Kit, JOSS 9(96)**, arxiv.org/abs/2109.08584, github.com/Toloka/crowd-kit. `pip install crowd-kit`: majority vote, Dawid-Skene, GLAD, MACE and others; no ordinal method, so use the median for 1 to 5 scores.
- **Snow et al. 2008, Cheap and fast, but is it good?**†, EMNLP. About 4 averaged non-expert labels match one expert on 5 NLP tasks. Overlap of 3 to 4 lay raters is evidence-based.
- No paper gives a clean lay-vs-expert weighted kappa on a 5-point advice scale. Expect lay kappa below 0.71 and measure it.

**Toloka status, verified 3 Oct 2026.** The old Python SDK (toloka-kit) was archived in
July 2024 and the old docs redirect to the homepage, but Toloka runs through a new agent
CLI: TypeScript pipelines, `toloka check`, `plan`, `apply`, a mandatory cost forecast
before any paid run, expert labelling tasks, login via `toloka login --browser`.
Bootstrap at platform.toloka.ai/agents/SKILL.md, runbook at
platform.toloka.ai/agents/data-labeling.md. The Toloka credit stays in the plan; Prolific
plus Crowd-Kit is the fallback.

## 5. Harm and confidence

- **Kalai et al. 2025, Why language models hallucinate, OpenAI**, arxiv.org/abs/2509.04664. Binary scoring rewards guessing; penalise confident errors more than abstention and state a confidence target in the grading instructions.
- **Röttger et al. 2024, XSTest, NAACL**, arxiv.org/abs/2308.01263. Over-refusal is scored as its own failure. Our harm line needs two-sided anchors: over-treatment and needless escalation.
- **Kirichenko et al. 2025, AbstentionBench**, arxiv.org/abs/2506.09038. Reasoning fine-tuning degraded abstention by 24%. Include unanswerable photos in the test set.
- **Tian et al. 2023, Just ask for calibration, EMNLP**, arxiv.org/abs/2305.14975. Verbalised confidence beats token probabilities for RLHF models, about 50% relative reduction in calibration error.
- **Xiong et al. 2024, Can LLMs express their uncertainty?, ICLR**, arxiv.org/abs/2306.13063. Verbalised confidence is systematically overconfident; multi-sample consistency helps.

## 6. Reporting standards

- **Miller 2024, Adding error bars to evals, Anthropic**, arxiv.org/abs/2411.00640. Cases are a sample; report SE and CI, clustered SEs for multi-photo plants, paired differences between models, power analysis first.
- **Reuel et al. 2024, BetterBench, NeurIPS**, arxiv.org/abs/2411.12990. 46-item checklist; most benchmarks omit significance and reproducibility.
- **Wang et al. 2024, LLMs are not fair evaluators**, arxiv.org/abs/2305.17926. Order swap flipped 66 of 80 verdicts; balanced-position calibration.
- **Gehrmann, Clark, Sellam 2023, Repairing the cracked foundation, JAIR**, arxiv.org/abs/2202.06935. Report annotator count and qualification, instructions verbatim, agreement, scale design.
- **Gallifant et al. 2025, TRIPOD-LLM, Nature Medicine**†. Model version, prompt text, decoding parameters and human-rater protocol as mandatory items.
- **Gu et al. 2024, A survey on LLM-as-a-judge**, arxiv.org/abs/2411.15594.

## 7. Changes to plan 2 this supports

1. Each of the six rubric lines becomes a short weighted checklist with three anchors (yes, partly, no) written as observable behaviours; the 1 to 5 is derived from checklist points, never asked for directly.
2. Negative-weighted items; "cannot tell from this photo, show me X" outscores any confident wrong diagnosis or action. The harm line covers over-treatment (repot, fungicide, feed when unneeded) and needless escalation, with extent and likelihood.
3. Evidence grounding splits into correct vs grounded: a right diagnosis citing a feature not visible in the photo scores below a right diagnosis with visible evidence.
4. Pilot-grade 30 to 50 real outputs with two raters before freezing the rubric; validate every judge per line with weighted kappa and ICC against human gold, report it beside the human-to-human ceiling, and drop judges below that ceiling instead of averaging them in.
5. Rating protocol: overlap of 3 lay raters (4 on adversarial or unanswerable cases), 2 gold items per batch of about 20, pay at or above £9 an hour on Prolific or the Toloka cost forecast, median for 1 to 5 scores and Dawid-Skene for checklist items; seed the set with unanswerable photos; ask the model for a numeric confidence so calibration error is reported beside the uncertainty line.
6. Report like an experiment: n per cell, 95% CIs with clustered SEs by plant, paired model deltas, weighted kappa and ICC per line, pass^k over 3 reruns, position-swap rate per judge, and judge model id, prompt hash, temperature and rubric version in the header.
