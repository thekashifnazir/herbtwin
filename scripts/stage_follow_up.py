"""Dev only: the follow-up loop on a local server, for screenshots. No paid calls, no real
accounts, nothing written to the repo (traces and cache go to a temp folder).

Usage: uv run python scripts/stage_follow_up.py [--port 8002]
The models are scripted (MockAdapter), sign-in is the tests' in-memory FakeAuth for
test@example.com, and history is MemoryHistory, so everything is gone when it stops. Before
serving it posts the judges' parsley sample twice, five days apart in London (after the
day-4 reminder), onto one plant, and leaves that plant's "Did you do it?" unanswered. The
weather is a made-up dry, mild month (so "water it" and the forecast agree) and the place
lookup is canned: nothing leaves the machine. Settings come from the dict below, not .env, so
search, Plantbook, voice and mail are all off. Every page carries a "Staged (test data)"
badge. Then open:

  /_dev/sign-in          signs this browser in as the test account (press the button)
  /plants                My plants: one plant, two visits
  /_dev/answer           the second visit's answer, with "Did you do it?"
  /_dev/reminder-email   the reminder email for the first visit, as its HTML renders
  /_dev/did-it-yes       answers Yes and shows the two-photo result
  /_dev/as-tester?next=  signs in without the button (for headless screenshots)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # the tests' fakes: FakeAuth and fake_accounts

import httpx  # noqa: E402
import respx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import Request, Response  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from herbtwin import reminders  # noqa: E402
from herbtwin.adapters.mock import MockAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.history import MemoryHistory  # noqa: E402
from herbtwin.pipeline import Deps  # noqa: E402
from herbtwin.stages.environment import OPEN_METEO_URL  # noqa: E402
from herbtwin.tracing import TraceStore  # noqa: E402
from herbtwin.web.accounts import set_session  # noqa: E402
from herbtwin.web.app import create_app  # noqa: E402
from herbtwin.where import GEOCODE_URL  # noqa: E402
from tests.fakes import FakeAuth, fake_accounts  # noqa: E402

EMAIL = "test@example.com"
USER = "stage-user"
SECRET = "stage-only-reminder-secret"  # signs the unsubscribe link in the staged email
PHOTO = ROOT / "docs" / "judges" / "samples" / "1-parsley-healthy.jpg"
FIRST, SECOND = datetime(2026, 10, 17, 9, tzinfo=UTC), datetime(2026, 10, 22, 9, tzinfo=UTC)

# what the photo model and the advisor "say": a thirsty parsley, then the two-photo compare
OBSERVE = {
    "species": [{"name": "Petroselinum crispum", "common_name": "parsley", "confidence": 0.9}],
    "is_plant": True,
    "water_stress": 2,
    "heat_light_stress": 0,
    "fine_leave_it": False,
    "symptoms": ["droop"],
    "leaf_cues": [],
    "soil_surface": "dry",
    "notes": "",
}
# the second photo, 5 days after watering: less droop, but the dry fortnight has dried the
# soil again, so the card's own trend line agrees with the compare's "less droop"
OBSERVE_AGAIN = {**OBSERVE, "water_stress": 1}
ADVICE = {
    "actions": ["water"],
    "primary": "water",
    "answer": "The leaves are drooping and the soil looks dry. Water it well at the base.",
    "ask": "How does the soil feel 2 cm down?",
    "confidence": "high",
}
ADVICE_AGAIN = {
    **ADVICE,
    "answer": "Less droop than on 17 Oct, but the soil looks dry again. Water it well at the base.",
}
# the compare asks twice each way round; "less" first then "more" second both mean less droop
COMPARE = [json.dumps({"change": c, "confidence": "high", "reason": "r"}) for c in ("less", "more")]
LONDON = {
    "results": [{"name": "London", "latitude": 51.5, "longitude": -0.12, "country_code": "GB"}]
}
BADGE = (
    b'<div role="note" style="position:fixed;right:16px;bottom:16px;z-index:99;padding:6px 14px;'
    b"border-radius:999px;background:#12291C;color:#fff;font:600 14px/1.3 system-ui,sans-serif;"
    b'box-shadow:0 2px 8px rgb(0 0 0/.3)">Staged (test data)</div>'
)


def dry_month() -> dict:
    """An Open-Meteo forecast reply for London: no rain, mild days, no frost, so the staged
    "water it" and the 2-week forecast tell the same story."""
    start = FIRST.date() - timedelta(days=14)
    days = [start + timedelta(days=i) for i in range((SECOND.date() - start).days + 15)]
    n = len(days)
    hours = [f"{d.isoformat()}T{h:02d}:00" for d in days for h in range(24)]
    return {
        "latitude": 51.5,
        "longitude": -0.12,
        "timezone": "Europe/London",
        "hourly": {
            "time": hours,
            "relative_humidity_2m": [65] * len(hours),
            "shortwave_radiation": [
                0 if int(t[11:13]) < 7 or int(t[11:13]) > 17 else 250 for t in hours
            ],
        },
        "daily": {
            "time": [d.isoformat() for d in days],
            "temperature_2m_max": [17.0] * n,
            "temperature_2m_min": [9.0] * n,
            "precipitation_sum": [0.0] * n,
            "et0_fao_evapotranspiration": [1.8] * n,
            "shortwave_radiation_sum": [8.0] * n,
            "daylight_duration": [37800] * n,
        },
    }


def build(port: int):
    now = [FIRST]
    scratch = Path(tempfile.mkdtemp(prefix="herbtwin-stage-"))  # traces and cache, not the repo
    hist, auth = MemoryHistory(), FakeAuth()
    settings = load_settings(
        {
            "HERBTWIN_HOME_LAT": "51.5",
            "HERBTWIN_HOME_LON": "-0.12",
            "HERBTWIN_REMINDER_SECRET": SECRET,
        }
    )
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBSERVE), json.dumps(OBSERVE_AGAIN)] + COMPARE * 2),
        advise_adapter=MockAdapter([json.dumps(ADVICE)] * 3 + [json.dumps(ADVICE_AGAIN)] * 3),
        settings=settings,
        trace_store=TraceStore(scratch / "traces.db"),
        cache_dir=scratch / "cache",
        workers=1,
    )
    site = f"http://127.0.0.1:{port}"
    app = create_app(deps, clock=lambda: now[0], accounts=fake_accounts(hist, auth), site_url=site)
    # the weather and the place, canned for the whole run; any other call fails loudly.
    # app.state.stage_weather.stop() puts httpx back (the tests do)
    weather = respx.mock(assert_all_called=False)
    weather.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=dry_month()))
    weather.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LONDON))
    weather.start()
    app.state.stage_weather = weather

    @app.middleware("http")
    async def staged_badge(request: Request, call_next):
        """Every HTML page says it is staged, so no screenshot passes for a live read."""
        r = await call_next(request)
        if not r.headers.get("content-type", "").startswith("text/html"):
            return r
        body = b"".join([chunk async for chunk in r.body_iterator])
        body = (
            body.replace(b"</body>", BADGE + b"</body>", 1) if b"</body>" in body else body + BADGE
        )
        out = Response(content=body, status_code=r.status_code)
        out.raw_headers = [h for h in r.raw_headers if h[0].lower() != b"content-length"] + [
            (b"content-length", str(len(body)).encode())
        ]
        return out

    seed = TestClient(app)
    seed.post("/auth/callback", data={"token_hash": auth.issue(USER, EMAIL), "type": "email"})
    photo = PHOTO.read_bytes()

    def visit() -> str:
        r = seed.post(
            "/analyse", files={"photo": (PHOTO.name, photo, "image/jpeg")}, data={"place": "London"}
        )
        if "/answers/" not in r.text:
            raise SystemExit(f"the staged read failed: {r.text[-400:]}")
        return r.text.rsplit("/answers/", 1)[1][:32]

    first = visit()
    now[0] = SECOND
    second = visit()
    store = hist.for_user(USER)
    plant = store.list_plants()[0]
    seed.post(f"/answers/{second}/plant", data={"plant_id": plant.id})

    @app.get("/_dev/sign-in", include_in_schema=False)
    def dev_sign_in():
        return RedirectResponse(f"/auth/callback?token_hash={auth.issue(USER, EMAIL)}&type=email")

    @app.get("/_dev/as-tester", include_in_schema=False)
    def dev_as_tester(next: str = "/plants"):
        """Signed in with no button, for a headless browser taking screenshots."""
        local = next.startswith("/") and not next.startswith("//") and "\\" not in next
        go = RedirectResponse(next if local else "/")
        set_session(go, auth.verify(auth.issue(USER, EMAIL), "email"), secure=False)
        return go

    answered: list[bool] = []

    @app.get("/_dev/did-it-yes", include_in_schema=False)
    def dev_did_it_yes():
        """Answers "Did you do it?" with Yes once (the two-photo compare runs, scripted),
        then shows the answer page, where the result replaces the question."""
        if not answered:
            seed.post(f"/answers/{second}/did-it", data={"did_it": "yes"})
            answered.append(True)
        return RedirectResponse(f"/answers/{second}")

    @app.get("/_dev/answer", include_in_schema=False)
    def dev_answer():
        return RedirectResponse(f"/answers/{second}")

    @app.get("/_dev/reminder-email", response_class=HTMLResponse, include_in_schema=False)
    def dev_email():
        r = reminders.schedule(store.get_answer(first), plant.name)
        if r is None:
            return HTMLResponse("No reminder: the first answer's action has no check window.", 404)
        e = reminders.email_for(r, site, reminders.sign(first, SECRET))
        head = (
            f"<p><b>From</b> herbtwin &lt;reminders@example.com&gt;<br><b>To</b> {html.escape(EMAIL)}"
            f"<br><b>Subject</b> {html.escape(e.subject)}<br><b>Sent</b> {r.due_on:%-d %b %Y}</p><hr>"
        )
        frame = "font:16px/1.5 -apple-system,Segoe UI,sans-serif;max-width:40rem;margin:40px auto;padding:0 16px"
        return f'<!doctype html><meta charset="utf-8"><title>{html.escape(e.subject)}</title><body style="{frame}">{head}{e.html}'

    return app, first, second


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8002)
    port = ap.parse_args().port
    app, first, second = build(port)
    print(
        f"staged: first answer {first}, second {second}; open http://127.0.0.1:{port}/_dev/sign-in"
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
