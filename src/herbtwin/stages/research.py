"""Species -> KnowledgePack. Seed (CC0) first; else the species' RHS page, read and parsed,
with OpenPlantBook bands as the fallback (B5); cached."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import httpx

from herbtwin.config import Settings
from herbtwin.plantbook import Bands, PlantBook, PlantBookFailed, plantbook_from
from herbtwin.reading import Page, PageReader, page_reader_from, scrub
from herbtwin.rhs import (
    HARDINESS_C,
    RhsFacts,
    find_rhs,
    is_species_page,
    names_species,
    parse_rhs,
    rhs_finder_from,
    species_slug,
)
from herbtwin.schemas import KnowledgePack
from herbtwin.search import WebSearch

log = logging.getLogger(__name__)
FACT_CHARS = 200  # sun and water lines in the care block
CULTIVATION_CHARS = 300
CACHE_VERSION = "v2"  # v1 packs held unread search links (before B5) and are never reused

# Names models commonly emit for the six herbs, mapped to the seed's accepted name.
SYNONYMS: dict[str, str] = {
    "rosmarinus officinalis": "Salvia rosmarinus",
    "mentha piperita": "Mentha spicata",  # hybrid marker "x" is dropped before lookup
    "ocimum basilicum": "Ocimum basilicum",
    "mentha spicata": "Mentha spicata",
    "petroselinum crispum": "Petroselinum crispum",
    "coriandrum sativum": "Coriandrum sativum",
    "salvia rosmarinus": "Salvia rosmarinus",
    "thymus vulgaris": "Thymus vulgaris",
    "salvia officinalis": "Salvia officinalis",
    "allium tuberosum": "Allium tuberosum",
    "allium schoenoprasum": "Allium schoenoprasum",
    "melissa officinalis": "Melissa officinalis",
    "origanum vulgare": "Origanum vulgare",
    "artemisia dracunculus": "Artemisia dracunculus",
    # unambiguous common names (a bare "mint" or "chives" stays unresolved on purpose)
    "sage": "Salvia officinalis",
    "common sage": "Salvia officinalis",
    "rosemary": "Salvia rosmarinus",
    "garlic chives": "Allium tuberosum",
    "chinese chives": "Allium tuberosum",
    "parsley": "Petroselinum crispum",
    "spearmint": "Mentha spicata",
    "peppermint": "Mentha spicata",
    "lemon balm": "Melissa officinalis",
    "oregano": "Origanum vulgare",
    "tarragon": "Artemisia dracunculus",
    "basil": "Ocimum basilicum",
    "coriander": "Coriandrum sativum",
    "cilantro": "Coriandrum sativum",
    "thyme": "Thymus vulgaris",
}


def normalise_species(name: str) -> str:
    """Resolve a model's species string to the seed's accepted Latin name.

    Models answer in several shapes: "Salvia officinalis", "Common sage (Salvia officinalis)",
    "Salvia officinalis (common sage)", "ocimum basilicum L.". Try the bracketed part and the
    outer part; the first that hits the synonym table wins. Otherwise the stripped input.
    """
    inner = re.search(r"\(([^)]+)\)", name)
    candidates = [name]
    if inner:
        candidates = [inner.group(1), re.sub(r"\([^)]*\)", " ", name)]
    for cand in candidates:
        words = [w for w in re.sub(r"[^a-z\s]", " ", cand.lower()).split() if w != "x"]
        key = " ".join(words[:2])
        if key in SYNONYMS:
            return SYNONYMS[key]
    return name.strip()


# Species thresholds the seed CSV does not carry; from the spec's cited sources.
# (basil chilling: PMC10352081; others are extension-service hardiness, pots 2-3 C less hardy.)
FROST_C: dict[str, tuple[float, float]] = {
    "Ocimum basilicum": (10.0, 5.0),
    "Coriandrum sativum": (0.0, -3.0),
    "Petroselinum crispum": (-4.0, -7.0),
    "Mentha spicata": (-6.0, -12.0),
    "Salvia rosmarinus": (-6.0, -9.0),
    "Thymus vulgaris": (-10.0, -16.0),
    # garden herbs added 2026-10-02; extension-service hardiness, pots treated 2-3 C less hardy
    "Salvia officinalis": (-5.0, -10.0),
    "Origanum vulgare": (-8.0, -15.0),
    "Artemisia dracunculus": (-6.0, -12.0),
    "Melissa officinalis": (-8.0, -15.0),
    "Allium tuberosum": (-8.0, -15.0),
    "Allium schoenoprasum": (-10.0, -20.0),
}
KC: dict[str, float] = {
    "Mentha spicata": 1.0
}  # FAO-56 Table 12 "mint" mid-season ~1.15, pot-scaled
DEFAULT_KC = 0.85  # FAO-56 "small vegetables" mid-season band 0.70-1.05


def _seed_rows() -> dict:
    with resources.files("herbtwin.data").joinpath("openplantdb_herbs.json").open() as f:
        return json.load(f)


def seed_pack(species: str) -> KnowledgePack | None:
    species = normalise_species(species)
    row = _seed_rows().get(species)
    if row is None:
        return None
    raw = row["raw"]
    damage, severe = FROST_C.get(species, (5.0, 0.0))
    return KnowledgePack(
        species=species,
        common_name=row["common_name"],
        kc=KC.get(species, DEFAULT_KC),
        water_need=str(raw.get("water", "unknown")),
        sun=str(raw.get("sun", "unknown")),
        frost_damage_c=damage,
        frost_severe_c=severe,
        notes=str(raw.get("directions", ""))[:500],
        sources=["openplantdb (CC0)"],
        verified=True,
    )


def _slug(species: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", species.lower()).strip("-")


@dataclass
class Lookup:
    """Where care facts come from for a plant the seed file lacks (B5)."""

    finder: WebSearch | None = None  # finds the species' RHS page
    reader: PageReader | None = None  # reads it, keeping a local copy
    plantbook: PlantBook | None = None  # light and soil-moisture bands


def lookup_from(settings: Settings, pages_dir: Path) -> Lookup:
    http = httpx.Client(timeout=20)
    return Lookup(
        rhs_finder_from(settings, http),
        page_reader_from(settings, http, pages_dir),
        plantbook_from(settings, http),
    )


def _is_species(page: Page, species: str) -> bool:
    return is_species_page(page.final_url, species) and names_species(
        page.title, page.text, species
    )


def _rhs(species: str, lookup: Lookup) -> tuple[RhsFacts, Page, str | None] | None:
    if lookup.finder is None or lookup.reader is None:
        return None
    found = find_rhs(species, lookup.finder)
    if found is None:
        return None
    url, by = found
    page = lookup.reader.read(
        url,
        accept=lambda p: _is_species(p, species) and parse_rhs(p.text).hardiness is not None,
    )
    if page is None or not _is_species(page, species):
        return None  # a stale id redirects to another plant: never borrow its facts
    return parse_rhs(page.text), page, by


def _bands(species: str, plantbook: PlantBook | None) -> Bands | None:
    if plantbook is None:
        return None
    try:
        return plantbook.bands(species)
    except PlantBookFailed as e:  # never fails the run; fewer facts
        log.warning("openplantbook failed for %r: %s", species, e)
        return None


def _pack(
    species: str, common: str, rhs: tuple[RhsFacts, Page, str | None] | None, bands: Bands | None
) -> KnowledgePack:
    sun = water = None
    damage, severe = 5.0, 0.0
    sources: list[str] = []
    notes: list[str] = []
    verified = rhs is not None and rhs[0].hardiness is not None
    if not verified:  # first, so the 500-character cap never cuts it
        notes.append("frost thresholds are generic")
    found_with = None
    if rhs is not None:
        facts, page, found_with = rhs
        sources.append(page.final_url)
        notes.append(f"read from the RHS page on {page.fetched_on}")
        if facts.position:
            sun = f"RHS: {facts.position.lower()}"
        wet = [f"moisture {facts.moisture.lower()}"] if facts.moisture else []
        if facts.drought_resistant:
            wet.append("drought resistant")
        water = "RHS: " + "; ".join(wet) if wet else None
        if facts.hardiness:
            damage, severe = HARDINESS_C[facts.hardiness]
            notes.append(f"RHS hardiness {facts.hardiness}")
        if facts.cultivation:
            notes.append(scrub(facts.cultivation, CULTIVATION_CHARS))
    if bands is not None:
        sources.append(f"openplantbook: {bands.pid}")
        if sun is None and bands.light_lux:
            sun = "OpenPlantBook: light {}-{} lux".format(*bands.light_lux)
        if water is None and bands.soil_moisture_pct:
            water = "OpenPlantBook: soil moisture {}-{}%".format(*bands.soil_moisture_pct)
    return KnowledgePack(
        species=species,
        common_name=common,
        kc=DEFAULT_KC,
        water_need=scrub(water, FACT_CHARS) or "unknown",
        sun=scrub(sun, FACT_CHARS) or "unknown",
        frost_damage_c=damage,
        frost_severe_c=severe,
        notes=scrub("; ".join(notes), 500),  # page text is data: fence runs removed
        sources=sources,
        verified=verified,
        found_with=found_with,
    )


def _default_pack(species: str, common: str) -> KnowledgePack:
    return KnowledgePack(
        species=species,
        common_name=common,
        kc=DEFAULT_KC,
        water_need="unknown",
        sun="unknown",
        frost_damage_c=5.0,
        frost_severe_c=0.0,
        notes="default pack; thresholds are generic; no care page was found",
        verified=False,
    )


def research(
    species: str, common_name: str, *, cache_dir: Path, lookup: Lookup | None = None
) -> KnowledgePack:
    species = normalise_species(species)
    pack = seed_pack(species)
    if pack is not None:
        return pack
    cache = cache_dir / f"{_slug(species)}.{CACHE_VERSION}.json"
    if cache.exists():
        return KnowledgePack.model_validate_json(cache.read_text())
    if lookup is None or "-" not in species_slug(species):  # no lookup for a genus or "unknown"
        return _default_pack(species, common_name)
    rhs = _rhs(species, lookup)
    facts = rhs[0] if rhs else None
    needs_bands = facts is None or facts.position is None or facts.moisture is None
    bands = _bands(species, lookup.plantbook) if needs_bands else None
    if rhs is None and bands is None:  # nothing found: not cached, so a later key refetches
        return _default_pack(species, common_name)
    pack = _pack(species, common_name, rhs, bands)
    if pack.verified:  # an unverified pack is looked up again next time (review, B5)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(pack.model_dump_json(indent=2))
    return pack
