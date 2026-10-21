# Judge calibration 2026-10-04-pairs_se-ollama-qwen3-14b-no-think

- Judge `ollama:qwen3:14b:no-think`; prompt hash `ac831a1b9c3e`; temperature 0 where the backend allows; git `559112f`
- Pairs 375; verdict rows 750: 750 ok, 0 unparseable, 0 call errors
- Position consistency 0.877 over 375 pairs; tie rate 0.000; first-position share of decisive verdicts 0.484
- Model-free baselines: preferred answer is longer 0.680, earlier 0.776

| Metric | Value | 95% CI | n |
|---|---|---|---|
| accuracy | 0.757 | 0.716 to 0.796 | 750 |
| accuracy_counting_unparseable_as_half | 0.757 | 0.716 to 0.796 | 750 |
| accuracy_diagnosis | 0.730 | 0.675 to 0.783 | 452 |
| accuracy_herb | 0.790 | 0.731 to 0.844 | 334 |
| accuracy_strong_pairs | 0.777 | 0.731 to 0.821 | 524 |
| accuracy_preferred_is_later | 0.756 | 0.667 to 0.839 | 168 |
| accuracy_preferred_is_shorter | 0.629 | 0.550 to 0.713 | 240 |
