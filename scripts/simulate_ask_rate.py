"""How often the squeeze is asked (spot spec section 9, "Ask rate"): random Great Britain
land cells x 5 settings x 12 months, through the real rule (spot_questions.squeeze_asked).
Offline and free; prints the shares.

    uv run python scripts/simulate_ask_rate.py [--points 500] [--seed 7]

Each cell's own map band, urban flag, pH and HadUK frost normals are used; the sun is the
defaults' estimate at a generic Midlands point and the typical coldest night is -7 C (no
network). "changes the list" is 100% by construction (rule 3); "changes the top 5" is the
stricter share the spec names.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import replace

from herbtwin.crops import Crop, load_calendar
from herbtwin.grow import GrowSpot, rank
from herbtwin.schemas import FrostNormals, PhRange, SpotRead, TextureBand, TexturePrior
from herbtwin.spot_priors import load_grid
from herbtwin.spot_questions import PLAUSIBLE, squeeze_asked, texture_prior
from herbtwin.sun import sun_hours

SETTINGS = ("pot", "trough", "raised_bed", "open_ground", "windowsill")
COLDEST = -7.0


def top5(crops: tuple[Crop, ...], spot: GrowSpot, band: TextureBand) -> frozenset[str]:
    certain = replace(spot, texture=TexturePrior(probs={band: 1.0}, source="squeeze"))
    return frozenset(p.crop_id for p in rank(crops, certain)["good_now"][:5])


def simulate(points: int, seed: int) -> dict:
    grid, crops = load_grid(), load_calendar()
    if grid is None or not crops:
        raise SystemExit("needs data/spot_grid/grid.bin.gz and data/crop_calendar/calendar.json")
    cells = random.Random(seed).sample(grid.cells(), points)
    sun = sun_hours(52.5, -1.5, None, None)
    reads = asks = top_changes = 0
    for e, n in cells:
        cell = grid.cell_at(e, n)
        frost = FrostNormals(
            air_frost_by_month=list(cell.air_frost_by_month) if cell.air_frost_by_month else None,
            typical_coldest_night_c=COLDEST,
        )
        ph = (
            PhRange(low=cell.ph[0], high=cell.ph[1], lime=cell.lime, source="ukceh_cs")
            if cell.ph
            else None
        )
        for setting in SETTINGS:
            medium = "soil" if setting in ("raised_bed", "open_ground") else "compost"
            read = SpotRead(setting=setting, medium=medium)
            prior = texture_prior(cell, read, None)
            for month in range(1, 13):
                spot = GrowSpot(
                    month=month,
                    year=2027,
                    setting=setting,
                    sun=sun,
                    frost=frost,
                    ph=ph,
                    texture=prior,
                )
                reads += 1
                if squeeze_asked(read, prior, spot, crops) != "ask":
                    continue
                asks += 1
                bands = [b for b, p in prior.probs.items() if b == prior.top or p > PLAUSIBLE]
                if len({top5(crops, spot, b) for b in bands}) > 1:
                    top_changes += 1
    return {
        "reads": reads,
        "asks": asks,
        "ask_share": round(asks / reads, 3) if reads else 0.0,
        "changes_the_list_share": 1.0 if asks else None,
        "changes_top5_share": round(top_changes / asks, 3) if asks else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--points", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    print(simulate(args.points, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
