"""One plant-name matcher for the season norms and the outcomes table (D32).

Models name plants in many shapes: "Rosemary (Salvia rosmarinus)", "Mentha sp.",
"ocimum basilicum L.", "Mint". This tries the whole name, then the binomial, then the
genus, against the keys and common names in data/seasonal/norms_uk.json. A genus
resolves only to a genus-level entry ("mentha", "rosa"): it never borrows a species
norm, and an unknown name returns no key rather than the nearest one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Literal

from herbtwin.seasonal import load_norms

MatchHow = Literal["exact", "binomial", "genus", "none"]


@dataclass(frozen=True)
class PlantMatch:
    key: str | None
    how: MatchHow


NO_MATCH = PlantMatch(None, "none")


def _clean(text: str) -> str:
    """Lower case, punctuation out (cultivar quotes and hyphens kept), hybrid "x" dropped."""
    words = re.sub(r"[^a-z\s'-]", " ", text.casefold()).split()
    return " ".join(w for w in words if w != "x")


def _parts(name: str) -> list[str]:
    """The bracketed part and the outer part, bracketed first; or the whole name."""
    inner = re.search(r"\(([^)]+)\)", name)
    if not inner:
        return [name]
    return [inner.group(1), re.sub(r"\([^)]*\)", " ", name)]


_BINOMIAL = re.compile(r"^[A-Z][a-z]+ [a-z][a-z-]+(?: [a-z][a-z-]+)?$")
_GENUS_FIRST = re.compile(r"^[A-Z][a-z]+ [a-z]")  # e.g. "Mentha sp."


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _names(name: str, common_name: str) -> tuple[str, str]:
    """The common and Latin names, each once: the photo reader puts the common name in
    brackets after the Latin one, or the other way round."""
    common = " ".join(common_name.split())
    if name.count("(") == 1 and name.count(")") == 1:
        parts = [" ".join(p.split()) for p in _parts(name)]
        latin = next(
            (p for p in parts if _BINOMIAL.match(p)),
            next((p for p in parts if _GENUS_FIRST.match(p)), parts[-1]),
        )
    else:  # no brackets, or broken ones: the name as it came, without them
        latin = " ".join(re.sub(r"[()]", " ", name).split())
    return common, latin


def name_parts(name: str, common_name: str) -> tuple[str, str]:
    """The page's big name and the Latin one under it: "Basil" over "Ocimum basilicum" (the
    answer-first band, design wave 1). A plant with one name keeps it big and nothing under.
    Built from the names, never from display_name's string: "mint (spearmint)" put
    "spearmint) (Mentha spicata" in the Latin line (review)."""
    common, latin = _names(name, common_name)
    if common and latin and latin.casefold() in common.casefold():
        # the reader put a common name where the Latin goes ("Basil" with "sweet basil"):
        # one name, never shown in italics as if it were Latin (#311 review)
        return _cap(common), ""
    if not latin:
        return _cap(common), ""
    if not common or common.casefold() == latin.casefold():
        return _cap(latin), ""
    return _cap(common), latin


# a place's adjective keeps its capital mid-sentence: "maybe Italian parsley"
_PLACE_WORD = re.compile(
    r"^(?:Chinese|Cuban|Egyptian|English|French|German|Greek|Indian|Italian|Japanese|Korean|"
    r"Mediterranean|Mexican|Moroccan|Persian|Roman|Russian|Solomon|Spanish|St|Swiss|Thai|"
    r"Turkish|Vietnamese|Welsh)\b"
)


def name_in_sentence(name: str, common_name: str) -> str:
    """The plant's name to follow other words ("Not clear: maybe mint"): the common name
    with a lower-case first letter, as the readers capitalise it ("Mint"); a Latin name and
    a place's adjective keep their capitals (22 Oct site walk 2: "Mint (not sure)" as the
    heading read as the answer)."""
    common, latin = _names(name, common_name)
    if not common or (latin and common.casefold() == latin.casefold()):
        return _cap(latin)
    return common if _PLACE_WORD.match(common) else common[:1].lower() + common[1:]


def display_name(name: str, common_name: str) -> str:
    """How a plant is named on the page: "Common name (Latin name)"; shown as the reader
    gave it, the common name appeared twice."""
    big, latin = name_parts(name, common_name)
    return f"{big} ({latin})" if latin else big


@cache
def _vocab() -> dict[str, str]:
    """Cleaned name -> norm key: every norm key and common name, plus true synonyms."""
    vocab: dict[str, str] = {}
    for norm in load_norms():
        for name in (norm.plant, *norm.common_names):
            vocab.setdefault(_clean(name), norm.plant)
    synonyms = json.loads(
        resources.files("herbtwin.evals").joinpath("species_synonyms.json").read_text()
    )["synonyms"]
    keys = set(vocab.values())
    for old, accepted in synonyms.items():
        if accepted in keys:
            vocab.setdefault(_clean(old), accepted)
    return vocab


@cache
def _genus_keys() -> frozenset[str]:
    return frozenset(n.plant for n in load_norms() if " " not in n.plant)


def match_plant(name: str) -> PlantMatch:
    parts = [p for p in (_clean(p) for p in _parts(name)) if p]
    vocab = _vocab()
    for p in parts:
        if p in vocab:
            return PlantMatch(vocab[p], "exact")
    for p in parts:
        binomial = " ".join(p.split()[:2])
        if " " in binomial and binomial in vocab:
            return PlantMatch(vocab[binomial], "binomial")
    for p in parts:
        genus = p.split()[0]
        if genus in _genus_keys():
            return PlantMatch(genus, "genus")
    return NO_MATCH


def match_species(name: str, common_name: str) -> PlantMatch:
    found = match_plant(name)
    return found if found.key is not None else match_plant(common_name)
