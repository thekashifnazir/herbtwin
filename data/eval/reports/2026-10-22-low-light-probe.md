# Low-light signs from the photo: probe (22 Oct 2026)

**Result: PASS.** The new `low_light` score never fired on the six outdoor sample photos, with
either photo model. It fired on the leggy indoor photos 2 of 3 times with the main model and
1 of 3 with the backup.

Pre-registered in `2026-10-22-low-light-probe/PREREG.md` before any call (sha256
`73116bc4e3d967e45e8f781fa76ee8130e5a45da21f01d21f409e47915fc6733`). Code: branch
fix/indoor-light-from-photo-and-window at db06db24. Scored once.

| Photo | Truth | Main (GLM-5.3-Flash) | Backup (DeepSeek-V4.1-Flash) |
|---|---|---|---|
| sample 1 parsley, healthy | 0 | 0 | 0 |
| sample 3 basil, yellow leaves | 0 | 0 | 0 |
| sample 4 rosemary, beetles | 0 | 0 | 0 |
| sample 5 coriander, flowering | 0 | 0 | 0 |
| sample 6 basil, downy mildew | 0 | 0 | 0 |
| sample 7 pea bed | 0 | 0 | 0 |
| SE 37744 "leggy basil with small leaves" | ≥1 | **2** | **2** |
| SE 55376 "Kalanchoe … leggy" | ≥1 | **2** | 0 |
| SE 22693 sedum "etiolate" | ≥1 | not given | 0 |

- **False fires: 0 of 6 samples, for both models.** The bar was more than 1 of the 3 healthy
  samples (1, 5, 7) failing.
- **Hits:** main 2 of 3, backup 1 of 3. Three photos show only that it can fire; they do not
  measure recall.
- **One main reply left the score out** (the sedum). The field is optional, so a missing score
  is "not known" and never read as "no sign".
- The SE photos are CC BY-SA from gardening.stackexchange.com questions 37744, 55376 and
  22693. The truth is each asker's own words.

**Run notes.**
- The first run read all 9 photos on the main model, then stopped on the backup: its model id
  is set only in the deploy (the private working repo's `deploy.sh`), not locally. Main's scores were printed
  before the stop (`main_out.txt`); the backup was then run alone with the deployed id. No
  photo was read twice.
- Spend: backup $0.0238 (recorded). The main run's spend was not saved; at GLM's ~$0.0016 a
  read it was about $0.015. Total about $0.04.
