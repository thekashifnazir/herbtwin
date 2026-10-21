# Judge calibration 2026-10-04-pairs_se-claude-claude-sonnet-5-5

- Judge `claude:claude-sonnet-5-5`; prompt hash `ac831a1b9c3e`; temperature 0 where the backend allows; git `d24c774`
- Pairs 375; verdict rows 750: 750 ok, 0 unparseable, 0 call errors
- Position consistency 0.872 over 375 pairs; tie rate 0.000; first-position share of decisive verdicts 0.468
- Model-free baselines: preferred answer is longer 0.680, earlier 0.776

| Metric | Value | 95% CI | n |
|---|---|---|---|
| accuracy | 0.715 | 0.672 to 0.756 | 750 |
| accuracy_counting_unparseable_as_half | 0.715 | 0.672 to 0.756 | 750 |
| accuracy_diagnosis | 0.708 | 0.650 to 0.759 | 452 |
| accuracy_herb | 0.737 | 0.674 to 0.796 | 334 |
| accuracy_strong_pairs | 0.731 | 0.677 to 0.782 | 524 |
| accuracy_preferred_is_later | 0.744 | 0.655 to 0.821 | 168 |
| accuracy_preferred_is_shorter | 0.608 | 0.525 to 0.688 | 240 |
