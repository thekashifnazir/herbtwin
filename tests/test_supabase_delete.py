"""Account delete against the real local stack: photos, rows and sign-in gone, a dead
token refused, and a retry still reports success (spec section 5)."""

import uuid
from datetime import UTC, datetime

import pytest

from herbtwin.adapters.supabase_store import SupabaseHistoryStore, delete_folder
from herbtwin.auth import SupabaseAuth
from herbtwin.history import Evidence, HistoryError, StoredAnswer
from herbtwin.schemas import Observation
from herbtwin.web.accounts import Accounts, delete_account
from tests.supabase_local import local_env, signed_up

pytestmark = pytest.mark.supabase


def test_delete_account_end_to_end():
    env = local_env()
    url, key = env["API_URL"], env["PUBLISHABLE_KEY"]
    secret = env.get("SECRET_KEY") or env["SERVICE_ROLE_KEY"]
    token, uid = signed_up(env)
    store = SupabaseHistoryStore(url, key, token, uid)
    plant = store.create_plant("Sage", "salvia officinalis", "salvia", None)
    aid = uuid.uuid4().hex
    path = store.put_photo(aid, b"jpeg", b"thumb")
    store.add_answer(
        StoredAnswer(
            id=aid,
            plant_id=plant.id,
            taken_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            photo_path=path,
            observation=Observation(
                species=[],
                is_plant=True,
                water_stress=1,
                heat_light_stress=0,
                fine_leave_it=False,
                symptoms=[],
                leaf_cues=[],
                soil_surface="dry",
            ),
            evidence=Evidence(
                location=None,
                taken_at_source="exif",
                environment=None,
                pack=None,
                season=None,
                notes=[],
                failures=[],
                season_missing=None,
                weather_missing=None,
            ),
            answer=None,
            told=None,
        )
    )
    auth = SupabaseAuth(url, key, secret)
    acc = Accounts(
        auth=auth,
        store_for=lambda u, t: SupabaseHistoryStore(url, key, t, u),
        secure=False,
        delete_folder=lambda u: delete_folder(url, secret, u),
    )
    delete_account(acc, uid)
    assert auth.user_exists(uid) is False
    with pytest.raises(HistoryError):
        store.put_photo(uuid.uuid4().hex, b"late", b"late")  # the dead token cannot upload
    assert delete_folder(url, secret, uid) == 0  # nothing left behind
    delete_account(acc, uid)  # a retry is safe
