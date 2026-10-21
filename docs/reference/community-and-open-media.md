# Community Q&A, open video and public-domain books

Three source types the earlier sweeps did not cover: community question-and-answer
archives, openly licensed time-lapse video, and public-domain herb books plus dated UK
citizen-science photos. Checked live on 3 Oct 2026 unless marked [unverified].

## 1. Community question-and-answer corpora

| Source | Size | Photos | Answer-quality signal | Licence | Access | Fit |
|---|---|---|---|---|---|---|
| **Stack Exchange Gardening and Landscaping** | 18,756 questions, 26,665 answers, 7,958 accepted | 77% of the latest 100 `diagnosis` questions have an image; 96% for `diagnosis` + `houseplants`; 60% for `herbs` | accepted answer, per-answer score, question score, views | CC BY-SA 4.0 from 2 May 2018, 3.0 before; `content_license` per post | keyless API (300 requests a day per IP); archive.org `stackexchange` item holds `gardening.stackexchange.com.7z`, 43.6 MB, April 2024. The current quarterly dump is profile-gated with a no-LLM-training checkbox. | **Best: open, with photos and a preference signal** |
| HF `mlfoundations-dev/stackexchange_gardening` | 42,429 rows | no | votes stripped | no licence tag | HF | weak; use the dump |
| MIRAGE (arXiv 2506.20100) | built from 218k Ask Extension dialogues, 2012 to 2025; 35k+ curated | yes | expert-written answer | CC BY-SA 4.0 | HF | expert reference answers; US backyard gardening |
| AgMMU (arXiv 2504.10568) | 746 MCQ + 746 open; 57k facts; from 116,231 dialogues | yes | expert, human-verified | "cc", version unspecified | HF | multiple-choice evaluation |
| Ask Extension (raw) | over 946k tickets | yes | extension expert | all rights reserved | no API or export; robots.txt disallows the ticket paths | do not scrape; use MIRAGE or AgMMU |
| Reddit r/plantclinic, r/houseplants, r/herbs, r/gardening | counts not retrievable | yes | upvotes, noisy | Data API licence forbids sublicensing, ML training without rightsholder permission, and retention after termination | OAuth only | browse-only sanity checks |
| HF `bmeyer2025/plantclinic-care-corpus` | 5,038 passages | no | none | per-row licence field | HF | care passages, not Q&A |
| Plantational / EcoSage (arXiv 2401.06807) | about 1k plant-care dialogues | multimodal | expert reply | [unverified] | [unverified] | closest prior work, small |

Unusable: GardenWeb and Houzz (terms prohibit scraping), UBC Botanical Garden forums (no
open licence), Dave's Garden and the UK Grow Your Own forum (no export found). No paper
using Gardening Stack Exchange or r/plantclinic to evaluate LLM advice was found, though
the arXiv keyword searches returned empty, so treat that as unverified.

### Stack Exchange tag counts

| Tag | Count | Tag | Count |
|---|---|---|---|
| identification | 3,319 | pests | 572 |
| houseplants | 1,597 | fungus | 348 |
| diagnosis | 1,534 | herbs | 277 |
| plant-health | 1,328 | container-gardening | 270 |
| plant-care | 973 | basil | 179 |
| diseases | 885 | mint | 148 |
| leaves | 867 | rosemary | 40 |
| indoors | 783 | cilantro | 35 |
| watering | 665 | parsley | 19 |
| containers | 433 | wilting | 15 |
| | | chives | 8 |

No tags exist for sage, thyme, oregano, overwatering or yellowing. Title-word counts:
basil 159, mint 143, rosemary 43, cilantro 27, parsley 19, coriander 17, chives 14, sage
12, thyme 12, oregano 12, tarragon 3, lemon balm 2.

Intersections: `diagnosis` with an accepted answer 529; `diagnosis` + `houseplants` 270;
`plant-health` + `houseplants` 356; `diagnosis` + `basil` 27, + `herbs` 23, + `mint` 18.
Accepted: `houseplants` 612, `herbs` 146, `basil` 84.

Bodies are short (median about 420 characters) with zero to three images. Image hosts are
`i.sstatic.net` (newer) and `i.stack.imgur.com` (older). The dump is text only; images are
fetched by URL.

### How we use it

- **Test questions.** About 270 to 350 houseplant diagnosis questions, almost all with photos. Herb problem questions: about 400 to 500 across tags and titles, about 60% with photos, about half with an accepted answer [estimate]. Basil and mint dominate.
- **Judge calibration.** Build pairs from questions with two or more answers, where the accepted answer or a score gap of at least 3 marks the human-preferred one. Show a judge both blind in random order and measure agreement with the human preference. Skip pairs with a gap under 2 and control for answer age, since earlier answers collect more votes.
- **Reference answers.** Accepted answers with a score of at least 3. Acceptance reflects the asker's satisfaction, not verified correctness, so pair with MIRAGE for expert references.
- **Problem prior.** Tag co-occurrence within `diagnosis` and `houseplants` (leaves, watering, pests, fungus, diseases) gives the frequency of real questions.
- **Licence handling.** Keep `content_license`, link and author per post. Share-alike applies to any redistributed derivative; a private evaluation set is fine. Evaluation is not training.

## 2. Openly licensed time-lapse video

Published science withholds its RGB stress series, so video is the remaining source of
image time series. Licences confirmed from live metadata; nothing was downloaded in the
sweep.

| # | Title | Link | Length and resolution | Shows | Licence |
|---|---|---|---|---|---|
| 1 | **Ocimum basilicum.ogv** | commons.wikimedia.org/wiki/File:Ocimum_basilicum.ogv | 22.6 s at 50 fps, 1080p (about 1,130 frames) | thirsty potted basil recovering after watering; 4 h 45 min, one photo every 15 s, dated | CC BY-SA 3.0 |
| 2 | Excessively dramatic revival of a basil plant | youtube.com/watch?v=M_vxOs8phjI | 24 s, 1080p | potted basil dried by heat, watered, 6 h recovery | CC BY |
| 3 | **Peace Lily Hydronasty (Time Lapse)** | youtube.com/watch?v=1C3K3uiijmA | 24 s, 1080p | very thirsty peace lily from the moment of watering, 6 h | CC BY |
| 4 | Plant perking up (spathiphyllum) | youtube.com/watch?v=O26CaN95rL0 | 64 s, 480p | peace lily unwatered 3 to 4 days; one photo every 10 s for over an hour | CC BY |
| 5 | Spathiphyllum perking up | youtube.com/watch?v=kvVwkVFPKbw | 4 s, 480p | same plant, one photo every 2 min | CC BY |
| 6 | Fittonia watered.ogv | commons.wikimedia.org/wiki/File:Fittonia_watered.ogv | 17.9 s, 1920×1200 | Fittonia houseplant recovering, 3.5 h | CC BY-SA 3.0 |
| 7 | The Basil Plant | youtube.com/watch?v=EYuEdHrueXw | 20 s, 720p | basil unwatered for a week, coming back | CC BY |
| 8 | **61 Day Basil Timelapse** | youtube.com/watch?v=fhMAhmapDVg | 61 s, 2160p60 | basil growth from sprout, 61 days, photo every 10 min, uniform light | CC BY |
| 9 | sunflower recovery, time lapse | youtube.com/watch?v=LEAbx31A6oA | 117 s, 1080p | forgotten potted sunflower recovering, 4 h | CC BY |
| 10 | Rehydrating Sunflower Shoots | youtube.com/watch?v=ZIeO3g5BP7I | 211 s, 1080p | microgreen tray rehydrating | CC BY |
| 11 | Flower recovery from water stress | youtube.com/watch?v=8bzVZv8cJ-o | 7 s, 1080p50 | potted flower, 8 h 37 min recovery | CC BY |
| 12 | timelapse of hydrangea unwilting | youtube.com/watch?v=yIhCkY5KVV8 | 5 s, 2160p | frames 30 s apart, about 70 min | CC BY |
| 13 | Aerogarden 4 weeks, tomatoes and basil | commons.wikimedia.org (Aerogarden_Time_Lapse_Video_-_4_weeks_-_Tomatoes_and_Basil.webm) | 118 s, 1080p | hydroponic basil growth, 4 weeks | CC BY 3.0 |
| 14 | Wilting flower time lapse.webm | commons.wikimedia.org/wiki/File:Wilting_flower_time_lapse.webm | 46.7 s, 1080p | cut flower wilting (the dry-down direction) | CC BY 3.0 |
| 15 | Epipremnum money plant growth, 2 months | youtube.com/watch?v=PdSOSWZZs5o | 2 h 24 min, 1080p | pothos, two months continuous; may contain watering cycles (unverified) | CC BY |

Also open and adjacent, found in the same sweep:

- **Zenodo 8256382, "Study of Leaf Wilt in Soybean Plants"**: 1,892 RGB field images with an **expert wilting score 0 to 4**, CC BY 4.0, 656 MB. Stills, not a series. **The only open expert-scored wilting image set found in any sweep**; the Purdue potted set remains request-only.
- Rascio 2020 (PMC7355443, CC BY): supplementary zip with two videos of wheat leaves wilting and recovering under heat.
- Zenodo 18371436: balsam fir branch time-lapse, CC BY 4.0.
- Negatives for "movement that is not wilting": Oxalis photonasty and pea de-etiolation (Commons, CC BY-SA 3.0).

Summary:

- About 11 reusable water-stress **recovery** sequences: 3 basil, 3 peace lily (two share a plant), 1 Fittonia, the rest sunflower and ornamentals. **True dry-down of a potted herb or houseplant: none found**; only a cut flower and possibly hidden inside the long growth videos.
- Free labels: time since watering per frame where the caption gives cadence or total duration; days without water before the clip for two; species in every title. Wilting onset is labelled nowhere.
- No mint, parsley, coriander, sage, rosemary or thyme sequence exists under any open licence. The garden photo series is the only route to dry-down data for those.
- Licence caveats: YouTube's CC licence is the uploader's self-declaration and downloading runs against YouTube's terms, so keep video ids and attribution and do not redistribute frames; Commons BY-SA frames carry share-alike. Coverr's licence forbids dataset and AI use. Pexels, Pixabay and Videvo blocked the check.

## 3. Public-domain and open books

| Title | Author, year | Link | Status | Covers | Caveat |
|---|---|---|---|---|---|
| **Culinary Herbs: Their Cultivation, Harvesting, Curing and Uses** | M. G. Kains, 1912 | gutenberg.org/ebooks/21414 | public domain in the USA and UK | per-herb cultivation, harvest, drying | US climate, dated pest advice. **Best single embeddable text.** |
| Savory Herbs: Culture and Use | M. S. Lowman, USDA, 1946 | archive.org `CAT87204893` | US government work | per-herb culture | US climate, OCR only |
| Seasoning Herbs for Indoor Growing; Grow Herbs for Flavor, Fun and Garden Trimming | USDA, 1935; 1942 | archive.org `seasoningherbsfo1935unit`, `growherbsforflav1942unit` | US government work | herbs in pots | short |
| House Plants (Farmers' Bulletin) | F. L. Mulford, USDA, 1941 | archive.org `CAT87203744` | US government work | light, water, potting | US |
| The Book of Town and Window Gardening | F. A. Bardswell, c.1903 | gutenberg.org/ebooks/57251 | public domain USA; UK unverified | urban, window-box and container growing, UK | closest to a London setting |
| The Herb-Garden | F. A. Bardswell, 1911 | archive.org `cu31924003382201` | public domain USA; UK unverified | UK herb garden culture | dated |
| The Book of Herbs | R. Northcote, 1903 | gutenberg.org/ebooks/60050 | public domain USA; UK since 2021 | English herb growing and uses | lore-heavy |
| A Garden of Herbs | E. S. Rohde, 1922 | archive.org `gardenofherbsbei00rohdrich` | flagged not in copyright | old English herb garden | more recipes than agronomy |
| Profitable Herb Growing and Collecting | A. B. Teetgen, 1916 | archive.org `cu31924002811838` | public domain USA; UK unverified | UK herb cultivation | commercial slant |
| The Kitchen Garden and the Cook | C. M. de Candia Pearse | gutenberg.org/ebooks/78799 | public domain USA and UK | alphabetical vegetable and herb cultivation | dated |
| In-Door Gardening for Every Week in the Year | W. Keane, c.1860 | gutenberg.org/ebooks/31423 | public domain | week-by-week UK indoor calendar | very dated |
| Gardening Indoors and Under Glass | F. F. Rockwell, 1912 | gutenberg.org/ebooks/22484 | public domain USA only; UK copyright until 2047 | house plants, watering, pests | not UK-clean |
| A Modern Herbal | M. Grieve, ed. C. F. Leyel, 1931 | archive.org | Grieve's text is UK public domain since 2012; Leyel's editorial matter probably in copyright to end 2027 [unverified] | all our herbs | **not cleanly embeddable until 2027 to 2028** |
| Wikibooks Horticulture | community | en.wikibooks.org/wiki/Horticulture | CC BY-SA | pages exist for rosemary, basil, lemon balm, Japanese maple, and genus Salvia and Thymus; missing for 8 of our herbs | partial |

Use old books for cultivation habit and seasonal behaviour only. Their pest and chemical
advice is obsolete and must never be surfaced as a recommendation.

## 4. Dated UK photos of our herbs (iNaturalist)

Place ids: United Kingdom 6857, Greater London 66357. All counts have photos. "Open" means
CC0, CC BY or CC BY-SA.

| Species | UK total | Open | Open + NC | Captive | Oct + Nov | Oct + Nov open | Oct + Nov open + NC | Peak month |
|---|---|---|---|---|---|---|---|---|
| Salvia officinalis | 808 | 76 | 619 | 711 | 54 | 6 | 44 | Jun |
| Salvia rosmarinus | 1,995 | 260 | 1,548 | 1,723 | 138 | 28 | 116 | Apr |
| Artemisia dracunculus | 10 | 0 | 7 | 4 | 0 | 0 | 0 | Jun |
| Origanum vulgare | 5,546 | 1,402 | 4,491 | 230 | 201 | 82 | 175 | Jul |
| Allium tuberosum | 80 | 13 | 63 | 27 | 13 | 2 | 11 | Sep |
| Allium schoenoprasum | 993 | 155 | 779 | 302 | 7 | 4 | 7 | May |
| Petroselinum crispum | 453 | 65 | 356 | 147 | 22 | 3 | 13 | Apr |
| Mentha spicata | 1,148 | 264 | 972 | 154 | 34 | 8 | 28 | Aug |
| Melissa officinalis | 1,907 | 564 | 1,594 | 188 | 93 | 41 | 77 | Apr |
| Thymus vulgaris | 232 | 29 | 189 | 218 | 9 | 0 | 8 | May |
| Ocimum basilicum | 170 | 8 | 126 | 162 | 13 | 1 | 8 | Jul |
| Coriandrum sativum | 135 | 23 | 100 | 45 | 10 | 5 | 9 | Jun |
| Acer palmatum | 2,298 | 210 | 1,746 | 2,150 | 370 | 47 | 271 | Apr, second peak Oct |

An "autumn appearance" reference from strictly open photos is possible for oregano, lemon
balm, rosemary and Japanese maple only. With non-commercial licences added, sage, spearmint
and parsley become possible; garlic chives, coriander, basil, thyme and chives are
marginal; tarragon has none. Widening to September through November helps the marginal
ones.

Query (swap `taxon_id`; add `cc-by-nc,cc-by-nc-sa` to widen; page with `page=`):

```
https://api.inaturalist.org/v1/observations?taxon_id=51738&place_id=6857&photos=true&month=10,11&photo_license=cc0,cc-by,cc-by-sa&per_page=200&order_by=observed_on
```

Each result carries `observed_on`, `captive`, `place_guess`, and per photo `url`,
`license_code`, `attribution`. Replace `square` with `medium` or `original`. Most herb
records are captive and therefore "casual" grade: do not filter on research grade, and
treat identifications as less vetted. About one request a second.
