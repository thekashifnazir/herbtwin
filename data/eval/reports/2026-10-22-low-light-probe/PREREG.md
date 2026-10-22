# Low-light photo read probe: pre-registration (22 Oct 2026)

Written before any paid call; its sha256 goes in the report.

**Question.** Does the new `low_light` score (0 none, 1 slightly stretched or pale, 2 clearly
leggy, pale or leaning) fire on plants short of light, and stay quiet on the site's healthy
outdoor sample photos?

**Code.** branch fix/indoor-light-from-photo-and-window at db06db24 (the WIP commit): the
observe prompt and schema exactly as the app sends them.

**Photos (9).**
- The 6 home-page sample photos (src/herbtwin/web/static/samples/, openly licensed): 1 parsley
  healthy, 3 basil yellow leaves, 4 rosemary beetles, 5 coriander flowering, 6 basil downy
  mildew, 7 pea bed. All are outdoor plants in daylight: truth low_light 0 for every one.
  "Healthy" (the integrator's bar) = 1, 5 and 7, no light problem in any of the 6.
- 3 leggy indoor photos from the Stack Exchange set (data/external/s3, CC BY-SA, the asker's
  own words as truth): 37744_0 "leggy basil with small leaves"; 55376_0 "Kalanchoe issues.
  Leggy, yellowing leaves"; 22693_0 sedum "curl and etiolate". Truth: low_light >= 1.

**Models.** Both photo paths the app uses: HERBTWIN_OBSERVE_MODEL (the main read) and
HERBTWIN_OBSERVE_FALLBACK_MODEL (the backup), each on every photo, once (18 calls), via
`stages.observe.observe` with no hedge.

**Metrics.**
- False fires: samples with low_light >= 1, per model.
- Hits: leggy photos with low_light >= 1, per model.
- Missing: replies with no low_light (None).

**Decision rule (fixed now).** Per model, on the 3 healthy samples (1, 5, 7): more than 1 false
fire FAILS, as the integrator set it. Fires on the other samples (3, 4, 6) are reported too.
If the main model fails, weaken the prompt or drop the photo read and tell the integrator;
the INDOOR LIGHT block keeps the told window either way. Hits are reported, with no bar: 3
photos only show whether it can fire at all.

**Budget.** Under $1 (expected about $0.05). Stop at $1.
