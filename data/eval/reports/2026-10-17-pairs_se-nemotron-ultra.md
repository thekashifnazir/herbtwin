# Judge calibration 2026-10-17-pairs_se-nemotron-ultra

- Judge `tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b`; prompt hash `ac831a1b9c3e`; temperature 0 where the backend allows; git `56e9638`
- Pairs 375; verdict rows 750: 743 ok, 7 unparseable, 0 call errors
- Position consistency 0.908 over 368 pairs; tie rate 0.003; first-position share of decisive verdicts 0.513
- Model-free baselines: preferred answer is longer 0.680, earlier 0.776

| Metric | Value | 95% CI | n |
|---|---|---|---|
| accuracy | 0.750 | 0.706 to 0.789 | 743 |
| accuracy_counting_unparseable_as_half | 0.747 | 0.703 to 0.786 | 750 |
| accuracy_diagnosis | 0.722 | 0.667 to 0.778 | 446 |
| accuracy_herb | 0.784 | 0.726 to 0.841 | 333 |
| accuracy_strong_pairs | 0.783 | 0.736 to 0.833 | 521 |
| accuracy_preferred_is_later | 0.687 | 0.590 to 0.778 | 166 |
| accuracy_preferred_is_shorter | 0.665 | 0.585 to 0.748 | 236 |
