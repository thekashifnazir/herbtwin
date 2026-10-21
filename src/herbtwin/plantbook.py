"""OpenPlantBook (open.plantbook.io), the free fallback when a plant has no RHS page (B5):
per-species light and soil-moisture bands. Its min_temp is a growing comfort, not frost
survival (calendula: 5 C where the RHS says H5), so frost is never read from it."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from herbtwin.config import Settings

TOKEN_URL = "https://open.plantbook.io/api/v1/token/"
SEARCH_URL = "https://open.plantbook.io/api/v1/plant/search"
DETAIL_URL = "https://open.plantbook.io/api/v1/plant/detail/{pid}/"
TIMEOUT_S = 15.0


@dataclass(frozen=True)
class Bands:
    pid: str
    light_lux: tuple[int, int] | None
    soil_moisture_pct: tuple[int, int] | None


class PlantBookFailed(Exception):
    """OpenPlantBook could not answer."""


def _band(d: dict, lo: str, hi: str) -> tuple[int, int] | None:
    a, b = d.get(lo), d.get(hi)
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in (a, b)):
        return None
    return (int(a), int(b)) if a <= b else None


@dataclass
class PlantBook:
    client_id: str
    client_secret: str
    http: httpx.Client

    def _call(self, method: str, url: str, **kw) -> dict:
        try:
            r = self.http.request(method, url, timeout=TIMEOUT_S, **kw)
        except httpx.HTTPError as e:
            raise PlantBookFailed(type(e).__name__) from e
        if r.status_code >= 400:
            raise PlantBookFailed(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise PlantBookFailed("reply was not JSON") from e
        if not isinstance(data, dict):
            raise PlantBookFailed("reply was not a JSON object")
        return data

    def bands(self, species: str) -> Bands | None:
        pid = " ".join(species.lower().split())
        token = self._call(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        ).get("access_token")
        if not isinstance(token, str) or not token:
            raise PlantBookFailed("no access token")
        auth = {"Authorization": f"Bearer {token}"}
        rows = self._call("GET", SEARCH_URL, params={"alias": pid}, headers=auth).get("results")
        if not isinstance(rows, list) or not any(
            isinstance(r, dict) and r.get("pid") == pid for r in rows
        ):
            return None
        d = self._call("GET", DETAIL_URL.format(pid=quote(pid)), headers=auth)
        light = _band(d, "min_light_lux", "max_light_lux")
        moist = _band(d, "min_soil_moist", "max_soil_moist")
        return Bands(pid, light, moist) if light or moist else None


def plantbook_on(settings: Settings) -> bool:
    """Open Plantbook is only asked when its keys are set (the home page names it then)."""
    return bool(settings.openplantbook_client_id and settings.openplantbook_client_secret)


def plantbook_from(settings: Settings, http: httpx.Client | None = None) -> PlantBook | None:
    if not (settings.openplantbook_client_id and settings.openplantbook_client_secret):
        return None
    return PlantBook(
        settings.openplantbook_client_id,
        settings.openplantbook_client_secret,
        http or httpx.Client(timeout=TIMEOUT_S),
    )
