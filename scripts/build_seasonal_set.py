"""Build the seasonal "normal or problem" eval set (roadmap phase A).

Usage, from the main checkout (where data/external lives):
  uv run python scripts/build_seasonal_set.py [--dry-run] [--external DIR]
Writes data/eval/sets/seasonal_uk.jsonl. Deterministic: candidates are ranked by a
seeded hash of their key, so dropping an item in the hand-check pulls in the next one
without reshuffling the rest. Hand-check decisions live in
data/eval/seasonal/handcheck.json and are applied on every build.

Four kinds of item (the last two reuse a photo from the first two):
  normal          autumn dieback or colour on a plant that does that every year
  problem         disease, pests or decline that no month excuses
  counterfactual  a "normal" photo paired with June: the same pixels, now a problem
  season_control  a summer "problem" photo paired with October: still a problem
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.items import EvalItem, write_set  # noqa: E402

SET = "seasonal_uk"
SEED = "20261005"
AUTUMN = {9, 10, 11}
COUNTERFACTUAL_MONTH = 6
CONTROL_MONTH = 10
DEFAULT_PROBLEM_MONTH = 7  # undated problem photos: mid growing season
UK = {"United Kingdom", "Ireland"}  # the headline subset: UK timing (Ireland is close)
COUNTRY_ALIASES = {
    "UK": "United Kingdom",
    "GB": "United Kingdom",
    "US": "United States",
    "USA": "United States",
    "NZ": "New Zealand",
    "IE": "Ireland",
    "Irland": "Ireland",
    "Northern Ireland": "United Kingdom",
    "Kew": "United Kingdom",  # herb_pd place names standing in for a country
    "ips setubal": "Portugal",
}
DEFAULT_NORMS = Path("data/seasonal/norms_uk.json")

# Plants that die back or colour every autumn (genus or species prefix -> reason).
# Rosemary, sage, thyme and Polystichum stay green all winter, so their "coloured" photos
# are not seasonal and are left out; basil is an annual killed by cold, a different case.
SEASONAL_PLANTS: dict[str, str] = {
    "Mentha spicata": "autumn dieback to the rhizome",
    "Melissa officinalis": "autumn dieback to the crown",
    "Artemisia dracunculus": "autumn dieback to the rootstock",
    "Allium tuberosum": "leaves yellow and die back in autumn",
    "Allium schoenoprasum": "leaves yellow and die back in autumn",
    "Origanum vulgare": "autumn dieback of the top growth",
    "Acer palmatum": "autumn leaf colour before leaf fall",
    "Dryopteris filix-mas": "fronds brown in autumn (deciduous fern)",
    "Rosa": "autumn leaf colour and leaf drop",
}

# How many of each pool to take (after hand-check drops).
CAPS = {
    "normal/herb": 70,
    "normal/maple": 35,
    "normal/fern": 25,
    "normal/rose": 20,
    "problem/mint_rust": 20,
    "problem/basil_downy_mildew": 15,
    "problem/powdery_mildew_herbs": 18,
    "problem/aphids_on_herbs": 6,
    "problem/rose_black_spot": 10,
    "problem/rose_powdery_mildew": 8,
    "problem/houseplant_unhealthy": 4,
}
COUNTERFACTUAL_CAPS = {"herb": 25, "maple": 8, "fern": 10, "rose": 7}
# Season controls: a real problem photo from outside autumn, paired with October. Without
# them most problems are dated in summer and "autumn means normal" alone scores well.
CONTROL_CAPS = {
    "mint_rust": 12,
    "basil_downy_mildew": 6,
    "powdery_mildew_herbs": 10,
    "rose_black_spot": 6,
    "rose_powdery_mildew": 6,
}

# herb_pd_refs: disease classes only. Pest classes (vine weevil, slugs, fungus gnats,
# scale, mealybug) are mostly insects photographed off the plant, so no host to label.
HERB_PD_HOSTS = {
    "Puccinia menthae": "mentha",
    "Peronospora belbahrii": "ocimum basilicum",
    "Golovinomyces biocellatus": "lamiaceae",
    "Golovinomyces monardae": "monarda",
    "Erysiphe heraclei": "apiaceae",
    "Cavariella aegopodii": "apiaceae",
}
HERB_PD_REASONS = {
    "mint_rust": "mint rust (Puccinia menthae)",
    "basil_downy_mildew": "basil downy mildew (Peronospora belbahrii)",
    "powdery_mildew_herbs": "powdery mildew",
    "aphids_on_herbs": "aphid infestation",
}

ITSELIF = "s15/itselif__ornamental-plant-diseases-master-dataset"
ITSELIF_URL = "https://www.kaggle.com/datasets/itselif/ornamental-plant-diseases-master-dataset"
HOUSEPLANT = "s15/tarieretimitimi__houseplant-health-classification-dataset"
HOUSEPLANT_URL = (
    "https://www.kaggle.com/datasets/tarieretimitimi/houseplant-health-classification-dataset"
)


@dataclass
class Candidate:
    key: str  # "<source>/<id>", stable and unique; also the hand-check key
    pool: str  # "normal/herb", "problem/mint_rust", ...
    path: str
    plant: str
    month: int
    reason: str
    label_source: str
    licence: str
    tag: str
    source: str
    country: str | None = None
    month_assumed: bool = False  # undated photo: month is DEFAULT_PROBLEM_MONTH

    @property
    def group(self) -> str:
        return self.pool.split("/", 1)[1]


def _rank(key: str) -> str:
    return hashlib.sha256(f"{SEED}:{key}".encode()).hexdigest()


def _slug(text: str) -> str:
    """File stems like "Black Spot (10)" or "IMG_0797 Large" as id-safe "Black_Spot_10"."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _inat_licence(code: str) -> str:
    """iNaturalist licence codes ("cc-by-nc") in the display form the other sets use."""
    code = code.strip().lower()
    if code == "cc0":
        return "CC0"
    if code.startswith("cc-"):
        return "CC " + code[3:].upper()
    return code or "unknown"


def _seasonal_reason(taxon: str) -> str | None:
    for prefix, reason in SEASONAL_PLANTS.items():
        if taxon == prefix or taxon.startswith(prefix + " "):
            return reason
    return None


def _country(raw: str) -> str | None:
    """Source country spellings ("UK", "GB", "US", "NZ", "") on one form, or None."""
    raw = raw.strip()
    return COUNTRY_ALIASES.get(raw, raw) or None


def norm_key(plant: str, norm_plants: set[str]) -> str | None:
    """The key normal_for() should get: the taxon, its binomial, or its genus, whichever
    the UK norms hold (any rose -> "rosa"). None when no norm covers the plant; a genus
    or family host ("mentha", "apiaceae") never borrows a species norm."""
    words = plant.split()
    for key in (plant, " ".join(words[:2]), words[0] if words else ""):
        if key in norm_plants:
            return key
    return None


def load_norm_plants(path: Path) -> set[str]:
    return {row["plant"] for row in json.loads(path.read_text())}


def s12_candidates(external: Path, manual: dict[str, str]) -> list[Candidate]:
    """Autumn photos annotated "colored leaves"/"no live leaves", plus UK autumn photos
    a viewer labelled as dieback (`manual`, keyed by photo id)."""
    manifest = external / "s12" / "manifest.csv"
    if not manifest.is_file():
        return []
    out = []
    with manifest.open(newline="") as f:
        for row in csv.DictReader(f):
            reason = _seasonal_reason(row["taxon_name"])
            if reason is None or row["hemisphere"] != "N" or row["status"] != "ok":
                continue
            if not (external / "s12" / row["file"]).is_file():
                continue
            month = int(row["month"])
            annotated = row["source"] == "leaf_annotation" and row["annotation"] in (
                "colored leaves",
                "no live leaves",
            )
            if annotated and month in AUTUMN:
                label_source = "inat_annotation"
            elif row["source"] == "uk_autumn_widened" and row["photo_id"] in manual:
                label_source = "manual"
            else:
                continue
            out.append(
                Candidate(
                    key=f"inat/{row['photo_id']}",
                    pool=f"normal/{row['group']}",
                    path=f"s12/{row['file']}",
                    plant=row["taxon_name"].lower(),
                    month=month,
                    reason=reason,
                    label_source=label_source,
                    licence=_inat_licence(row["photo_licence"]),
                    tag=row["tag"],
                    source=f"https://www.inaturalist.org/observations/{row['observation_id']}",
                    country=_country(row["country"]),
                )
            )
    return out


def herb_pd_candidates(external: Path) -> list[Candidate]:
    index = external / "s16" / "herb_pd_refs" / "index.csv"
    if not index.is_file():
        return []
    out = []
    with index.open(newline="") as f:
        for row in csv.DictReader(f):
            host = HERB_PD_HOSTS.get(row["taxon"])
            if host is None or row["class"] not in HERB_PD_REASONS:
                continue
            if not (external / "s16" / "herb_pd_refs" / row["file"]).is_file():
                continue
            mm = row["date"][5:7]
            dated = mm.isdigit() and 1 <= int(mm) <= 12
            month = int(mm) if dated else DEFAULT_PROBLEM_MONTH
            out.append(
                Candidate(
                    key=f"herb_pd/{Path(row['file']).stem}",
                    pool=f"problem/{row['class']}",
                    path=f"s16/herb_pd_refs/{row['file']}",
                    plant=host,
                    month=month,
                    reason=HERB_PD_REASONS[row["class"]],
                    label_source="dataset_class",
                    licence=row["licence"],
                    tag=row["tag"],
                    source=row["source_url"],
                    country=_country(row["country_or_region"]),
                    month_assumed=not dated,
                )
            )
    return out


def _folder_candidates(
    external: Path, rel: str, pool: str, plant: str, reason: str, licence: str, tag: str, url: str
) -> list[Candidate]:
    folder = external / rel
    if not folder.is_dir():
        return []
    # key: source, then every folder below it (the split too, as train/ and test/ reuse
    # file names), then the file stem
    _, source_dir, *subdirs = rel.split("/")
    prefix = "/".join([source_dir.split("__")[0], *subdirs])
    return [
        Candidate(
            key=f"{prefix}/{_slug(p.stem)}",
            pool=pool,
            path=f"{rel}/{p.name}",
            plant=plant,
            month=DEFAULT_PROBLEM_MONTH,
            reason=reason,
            label_source="dataset_class",
            licence=licence,
            tag=tag,
            source=url,
            month_assumed=True,
        )
        for p in sorted(folder.iterdir())
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]


def folder_candidates(external: Path) -> list[Candidate]:
    # itselif's CC0 claim is disputed (web-sourced images), so test-only (INDEX.md).
    out = []
    for split in ("test", "train"):
        out += _folder_candidates(
            external,
            f"{ITSELIF}/rose/{split}/rose_black_spot",
            "problem/rose_black_spot",
            "rosa",
            "rose black spot (Diplocarpon rosae)",
            "CC0-1.0 (as stated, disputed)",
            "test-only",
            ITSELIF_URL,
        )
        out += _folder_candidates(
            external,
            f"{ITSELIF}/rose/{split}/rose_powdery_mildew",
            "problem/rose_powdery_mildew",
            "rosa",
            "rose powdery mildew (Podosphaera pannosa)",
            "CC0-1.0 (as stated, disputed)",
            "test-only",
            ITSELIF_URL,
        )
    out += _folder_candidates(
        external,
        f"{HOUSEPLANT}/data_raw/Unhealthy",
        "problem/houseplant_unhealthy",
        "houseplant",
        "indoor plant in decline (no season excuses it)",
        "CC BY-SA 4.0",
        "safe-to-train",
        HOUSEPLANT_URL,
    )
    return out


def load_handcheck(path: Path) -> dict:
    if not path.is_file():
        return {"ok": [], "drop": {}, "no_counterfactual": {}, "manual_dieback": {}}
    return json.loads(path.read_text())


def _order(c: Candidate, salt: str = "") -> tuple[bool, str]:
    """UK photos first (the headline subset), then a seeded hash of the key."""
    return (c.country not in UK, _rank(salt + c.key))


def _take(cands: Iterable[Candidate], cap: int) -> list[Candidate]:
    return sorted(cands, key=_order)[:cap]


def select(
    cands: list[Candidate], handcheck: dict
) -> tuple[list[Candidate], list[Candidate], list[Candidate]]:
    """(chosen, counterfactual sources, control sources): drops applied, pools capped by rank."""
    drop = handcheck.get("drop", {})
    by_pool: dict[str, list[Candidate]] = {}
    for c in cands:
        if c.key not in drop:
            by_pool.setdefault(c.pool, []).append(c)
    chosen = []
    for pool in sorted(by_pool):
        chosen += _take(by_pool[pool], CAPS.get(pool, 0))
    no_cf = handcheck.get("no_counterfactual", {})
    cf_sources = []
    for group, cap in COUNTERFACTUAL_CAPS.items():
        eligible = [c for c in chosen if c.pool == f"normal/{group}" and c.key not in no_cf]
        # rank by a second hash so the twin subset is not just the top of the pool
        cf_sources += sorted(eligible, key=lambda c: _order(c, "cf:"))[:cap]
    control_sources = []
    for group, cap in CONTROL_CAPS.items():
        eligible = [c for c in chosen if c.pool == f"problem/{group}" and c.month not in AUTUMN]
        control_sources += sorted(eligible, key=lambda c: _order(c, "ctl:"))[:cap]
    return chosen, cf_sources, control_sources


def _item(
    c: Candidate,
    norm_plants: set[str],
    *,
    kind: str,
    verdict: str,
    month: int,
    reason: str,
    label_source: str,
    suffix: str = "",
) -> EvalItem:
    return EvalItem(
        id=f"{SET}/{c.key}{suffix}",
        set=SET,
        path=c.path,
        root="external",
        label={
            "plant": c.plant,
            "month": month,
            "verdict": verdict,
            "reason": reason,
            "label_source": label_source,
            "kind": kind,
            "group": c.group,
            # the key the UK norms know this plant by; None = no norm, score apart
            "norm_key": norm_key(c.plant, norm_plants),
            "country": c.country,
            "uk": c.country in UK,
            # the source photo has no date: its month is assumed (DEFAULT_PROBLEM_MONTH)
            "undated": c.month_assumed,
        },
        # twins share a cluster: the same photo must not count as two independent results
        cluster=c.key,
        licence=c.licence,
        tag=c.tag,
        source=c.source,
    )


def build(
    external: Path, handcheck: dict, norm_plants: set[str]
) -> tuple[list[EvalItem], list[Candidate]]:
    manual = handcheck.get("manual_dieback", {})
    cands = s12_candidates(external, manual) + herb_pd_candidates(external)
    cands += folder_candidates(external)
    dupes = [k for k, n in Counter(c.key for c in cands).items() if n > 1]
    if dupes:  # one hand-check key must never cover two photos
        raise ValueError(f"duplicate candidate keys: {sorted(dupes)[:5]}")
    chosen, cf_sources, control_sources = select(cands, handcheck)
    items = []
    for c in chosen:
        kind = c.pool.split("/")[0]
        items.append(
            _item(
                c,
                norm_plants,
                kind=kind,
                verdict=kind,
                month=c.month,
                reason=c.reason,
                label_source=c.label_source,
            )
        )
    for c in cf_sources:
        items.append(
            _item(
                c,
                norm_plants,
                kind="counterfactual",
                verdict="problem",
                month=COUNTERFACTUAL_MONTH,
                reason=f"not seasonal in June ({c.reason} belongs to autumn)",
                label_source="counterfactual_month",
                suffix=f"@m{COUNTERFACTUAL_MONTH:02d}",
            )
        )
    for c in control_sources:
        items.append(
            _item(
                c,
                norm_plants,
                kind="season_control",
                verdict="problem",
                month=CONTROL_MONTH,
                reason=f"{c.reason}; autumn does not excuse it",
                label_source="counterfactual_month",
                suffix=f"@m{CONTROL_MONTH:02d}",
            )
        )
    return items, chosen


def summary(items: list[EvalItem], chosen: list[Candidate], handcheck: dict) -> str:
    lines = [f"{len(items)} items"]
    lines.append("verdict: " + str(dict(Counter(i.label["verdict"] for i in items))))
    lines.append("kind:    " + str(dict(Counter(i.label["kind"] for i in items))))
    lines.append("tag:     " + str(dict(Counter(i.tag for i in items))))
    lines.append("source:  " + str(dict(Counter(i.label["label_source"] for i in items))))
    uk = [i for i in items if i.label["uk"]]
    lines.append("UK only: " + str(dict(Counter(i.label["verdict"] for i in uk))))
    normed = [i for i in items if i.label["norm_key"]]
    lines.append("norm_key:" + str(dict(Counter(i.label["verdict"] for i in normed))))
    per = Counter((i.label["kind"], i.label["group"]) for i in items)
    for (kind, group), n in sorted(per.items()):
        lines.append(f"  {kind:15} {group:22} {n}")
    checked = set(handcheck.get("ok", [])) | set(handcheck.get("drop", {}))
    unchecked = [c.key for c in chosen if c.key not in checked]
    lines.append(f"chosen photos not yet hand-checked: {len(unchecked)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument(
        "--norms",
        type=Path,
        default=DEFAULT_NORMS,
        help="UK seasonal norms JSON; label.norm_key is resolved against its plant keys",
    )
    ap.add_argument("--dry-run", action="store_true", help="print counts, write nothing")
    ap.add_argument("--list-unchecked", action="store_true", help="print unchecked paths")
    args = ap.parse_args(argv)
    if not args.external.is_dir():
        print(f"no holdings at {args.external}; run from the main checkout", file=sys.stderr)
        return 2
    if not args.norms.is_file():
        print(f"no norms at {args.norms}; pass --norms", file=sys.stderr)
        return 2
    handcheck = load_handcheck(args.eval_dir / "seasonal" / "handcheck.json")
    items, chosen = build(args.external, handcheck, load_norm_plants(args.norms))
    if args.list_unchecked:
        checked = set(handcheck.get("ok", [])) | set(handcheck.get("drop", {}))
        for c in chosen:
            if c.key not in checked:
                print(f"{c.key}\t{c.pool}\t{c.path}")
        return 0
    print(summary(items, chosen, handcheck))
    if not args.dry_run:
        out = args.eval_dir / "sets" / f"{SET}.jsonl"
        write_set(out, items)
        print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
