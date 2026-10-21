# Confidence weights

`weights.json`: how much each factor (photo, forecast, agreement, season and so on)
moves the "How sure we are" line on an answer (two levels on the page since 19 Oct; the
`in_ten` figures here are the 5 Oct fit and are no longer shown). The base, advisor, agreement and
repair weights are fitted by `scripts/fit_confidence.py` over our own evaluation runs;
the rest are set by hand. No third-party content. MIT, with the code.
