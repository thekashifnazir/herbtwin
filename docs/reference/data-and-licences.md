# Data and licences

What herbtwin ships and fetches, where each piece comes from, and its licence.

| Data | Source | Licence |
|---|---|---|
| Herb care facts (`src/herbtwin/data/openplantdb_herbs.json`) | OpenPlantDB | CC0 1.0 |
| UK season norms (`data/seasonal/`) | Written for this project; each row cites RHS, NC State or other extension pages | MIT, with sources per row |
| Outcomes, "what happens if you do it" (`data/outcomes/`) | Paraphrased facts, each row citing its RHS or extension page | MIT, with sources per row |
| Crop calendar (`data/crop_calendar/`) | RHS, Garden Organic and seed-company pages per row, plus the [Plant Variety Database](https://github.com/bripatch/plant-variety-database) | Plant Variety Database: CC BY 4.0 |
| 1 km soil, frost and sun grid (`data/spot_grid/`) | BGS, UKCEH, Met Office HadUK-Grid | Open Government Licence ([credits](../../data/spot_grid/README.md)) |
| Sample photos (`docs/judges/samples/`, and copies with thumbnails in `src/herbtwin/web/static/samples/`) | iNaturalist, Wikimedia Commons | CC0 / CC BY ([credits](../judges/samples/CREDITS.md)) |
| "In about a week" pictures (`src/herbtwin/web/static/twin/`) | Edits of four sample photos, made with Qwen-Image-Edit-2509 (Apache-2.0) | Each keeps its source photo's licence; credit per picture in `manifest.json` |
| Plant name synonyms (`src/herbtwin/evals/species_synonyms.json`) | Kew World Checklist of Vascular Plants (WCVP) v16 | CC BY 3.0 |
| Eval sets (`data/eval/sets/`) | Stack Exchange Gardening, GBIF and others | ids and labels only; per-row source and licence |

Fetched live, not stored here: weather and place names from Open-Meteo (CC BY 4.0; its
free API is for non-commercial use), UK postcodes from postcodes.io (OS OpenData and
ONSPD), care bands from OpenPlantBook (its own terms), and RHS plant pages and search
results (publishers' copyright, linked, not copied). Full credits: [NOTICE](../../NOTICE).
Python dependencies are MIT, BSD or Apache-2.0.
