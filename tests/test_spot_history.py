"""A signed-in person's spots (spot spec D70): stored at the rounded place, owner-only,
and a compass reading reused at the same place for 60 days."""

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import respx

from herbtwin.adapters.supabase_store import SupabaseHistoryStore
from herbtwin.history import MemoryHistory, StoredSpot
from herbtwin.schemas import Aspect, Location, Spot, SpotRead

T0 = datetime(2026, 10, 4, 9, tzinfo=UTC)
HERE, THERE = (
    Location(lat=51.4787, lon=-0.2956, source="typed"),  # Kew Gardens
    Location(lat=51.443, lon=-0.276, source="typed"),  # Richmond Park
)
TAP = Aspect(heading_deg=191, pitch_deg=30, source="compass")


def _row(place=HERE, aspect=TAP, at=T0):
    return StoredSpot(id=str(uuid.uuid4()), taken_at=at, place=place, aspect=aspect,
                      spot=Spot(read=SpotRead(setting="raised_bed")), grow=None)  # fmt: skip


def test_memory_store_reuses_the_latest_tap_at_the_same_place_only():
    hist = MemoryHistory()
    me, other = hist.for_user("u1"), hist.for_user("u2")
    me.save_spot(_row(at=T0 - timedelta(days=10)))
    me.save_spot(
        _row(aspect=Aspect(heading_deg=180, source="tapped_direction"), at=T0 - timedelta(days=2))
    )
    me.save_spot(_row(aspect=None, at=T0 - timedelta(days=1)))
    me.save_spot(_row(place=THERE, at=T0))
    aspect, at = me.recent_aspect(HERE, T0 - timedelta(days=60))
    assert aspect.heading_deg == 180 and at == T0 - timedelta(days=2)
    assert me.recent_aspect(HERE, T0 - timedelta(days=1)) is None  # older than the window
    assert other.recent_aspect(HERE, T0 - timedelta(days=60)) is None


@respx.mock
def test_supabase_store_writes_the_rounded_place_and_reads_the_latest():
    url = "https://proj.supabase.co"
    store = SupabaseHistoryStore(url, "sb_publishable_x", "user-token", "u1", client=httpx.Client())
    post = respx.post(f"{url}/rest/v1/spots").mock(return_value=httpx.Response(201))
    store.save_spot(_row())
    body = json.loads(post.calls.last.request.content)
    assert (body["place_lat"], body["place_lon"]) == (51.48, -0.3) and body["aspect"][
        "heading_deg"
    ] == 191
    assert post.calls.last.request.headers["prefer"] == "resolution=merge-duplicates"
    get = respx.get(f"{url}/rest/v1/spots").mock(
        return_value=httpx.Response(
            200,
            json=[{"aspect": TAP.model_dump(mode="json"), "taken_at": "2026-10-03T09:00:00+00:00"}],
        )
    )
    aspect, at = store.recent_aspect(HERE, T0 - timedelta(days=60))
    q = get.calls.last.request.url.params
    assert q["place_lat"] == "eq.51.48" and q["aspect"] == "not.is.null" and q["limit"] == "1"
    assert aspect == TAP and at.date() == date(2026, 10, 3)


MIGRATION = (
    Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20261014120000_spots.sql"
)


def test_the_migration_ties_spots_to_the_account_and_refuses_raw_gps():
    """Offline stand-in for an RLS cascade check (plan amendment 3): admin has no grant on
    spots, so the local stack cannot see that a deleted account's spots went."""
    sql = " ".join(MIGRATION.read_text().lower().split())
    assert re.search(
        r"user_id uuid not null default auth\.uid\(\) references auth\.users \(id\) "
        r"on delete cascade",
        sql,
    )
    assert "enable row level security" in sql and "to service_role" not in sql
    for col in ("place_lat", "place_lon"):
        assert f"{col} = round({col}::numeric, 2)::double precision" in sql
