"""Paid check of the side-by-side comparison (C2 step 0, spec section 4).

Re-runs probe c's pair design through the real code (herbtwin.side_by_side) and checks the
bar: direction right on at least 9 of 10 public change pairs, at most 1 false change on 10
same pairs, the 3 parsley recoveries "improved" (or can't tell when the light check fires).
Garden info pairs are reported, not gated. Light for garden crops is C1's reading of the
full source photo at the public Heathrow grid cell (never the garden's own position).

    uv run python scripts/check_scoring.py --data ../../data              # quote only
    uv run python scripts/check_scoring.py --data ../../data --yes-paid --write-gate
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.light import read_light  # noqa: E402
from herbtwin.scoring import GATE_PATH, light_mismatch  # noqa: E402
from herbtwin.side_by_side import PROMPT_VERSION, Side, compare_pair  # noqa: E402
from herbtwin.tracing import StageTracer, TraceStore, bind  # noqa: E402
from herbtwin.where import exif_datetime, exif_exposure  # noqa: E402

PAIRS = Path(__file__).resolve().parents[1] / "data" / "scoring" / "pairs.json"
RUNS = Path("data/eval/runs")
SKY_URL = "https://api.open-meteo.com/v1/forecast"
PROXY = (51.47, -0.45)  # public Heathrow grid cell, never the garden
EST_TOKENS = (1600, 500)  # per call: two 1024 px photos in, a short reasoned reply out
CROP_MANIFESTS = (
    "external/garden_crops/manifest.json",
    "external/garden_crops/pass_20261003/manifest.json",
)


def crop_index(data: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rel in CROP_MANIFESTS:
        m = data / rel
        if m.exists():
            for c in json.loads(m.read_text()):
                out[c["id"]] = {**c, "path": m.parent / c["file"]}
    return out


def sky_for(client: httpx.Client, on: date) -> tuple[list[float | None], int]:
    resp = client.get(
        SKY_URL,
        params={
            "latitude": PROXY[0],
            "longitude": PROXY[1],
            "hourly": "shortwave_radiation",
            "start_date": on.isoformat(),
            "end_date": on.isoformat(),
            "timezone": "Europe/London",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    values = data["hourly"]["shortwave_radiation"]
    return (values if len(values) == 24 else []), data["utc_offset_seconds"]


def light_of(data: Path, photo: str, client: httpx.Client, skies: dict) -> str | None:
    """C1's light "now" for a garden crop, read from its full source photo."""
    p = data / "photos" / "all" / photo
    if not p.exists():
        return None
    raw = p.read_bytes()
    with Image.open(p) as img:
        taken = exif_datetime(img)
    if taken is None:
        return None
    if taken.date() not in skies:
        skies[taken.date()] = sky_for(client, taken.date())
    sky, offset = skies[taken.date()]
    reading, _ = read_light(exif_exposure(raw), taken, sky, indoor=False, sky_offset_s=offset)
    return reading.now if reading else None


def side(spec: dict, data: Path, crops: dict, client: httpx.Client, skies: dict) -> Side:
    if "crop" in spec:
        c = crops[spec["crop"]]
        light = light_of(data, c["source_photo"], client, skies)
        return Side(Path(c["path"]).read_bytes(), datetime.fromisoformat(c["taken_at"]), light)
    return Side((data / spec["path"]).read_bytes())


def verdict(results: list[dict]) -> tuple[bool, dict]:
    """The step-0 bar over the results (each: set, expect, verdict, light_guard)."""
    change = [r for r in results if r["set"] == "change"]
    same = [r for r in results if r["set"] == "same"]
    parsley = [r for r in results if r["set"] == "parsley"]
    right = sum(r["verdict"] == r["expect"] for r in change)
    false = sum(r["verdict"] in ("more", "less") for r in same)
    park = sum(
        r["verdict"] == "less" or (r["verdict"] == "cant_tell" and bool(r["light_guard"]))
        for r in parsley
    )
    counts = {
        "change_right": f"{right}/{len(change)}",
        "same_false": f"{false}/{len(same)}",
        "parsley_ok": f"{park}/{len(parsley)}",
    }
    sized = (len(change), len(same), len(parsley)) == (10, 10, 3)
    return sized and right >= 9 and false <= 1 and park == 3, counts


def gates(results: list[dict]) -> dict[str, tuple[bool, dict]]:
    """The bar per signal. Posture keeps the parsley rule (verdict above); browning and
    colour need at least 10 change and 10 same pairs of their own, direction right on 90%
    of the change pairs and a false change on at most 10% of the same pairs."""
    out = {"posture": verdict([r for r in results if r["signal"] == "posture"])}
    for signal in ("tissue", "colour"):
        mine = [r for r in results if r["signal"] == signal]
        change = [r for r in mine if r["set"] == "change"]
        same = [r for r in mine if r["set"] == "same"]
        if len(change) < 10 or len(same) < 10:
            continue  # too few pairs to judge: the signal stays untested
        right = sum(r["verdict"] == r["expect"] for r in change)
        false = sum(r["verdict"] in ("more", "less") for r in same)
        ok = right >= math.ceil(0.9 * len(change)) and false <= math.floor(0.1 * len(same))
        out[signal] = (
            ok,
            {"change_right": f"{right}/{len(change)}", "same_false": f"{false}/{len(same)}"},
        )
    return out


def _missing(pairs: list[dict], data: Path, crops: dict) -> list[str]:
    out = set()
    for p in pairs:
        for s in (p["earlier"], p["later"]):
            if ("crop" in s and s["crop"] not in crops) or (
                "path" in s and not (data / s["path"]).exists()
            ):
                out.add(p["id"])
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="folder holding external/ and photos/")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-gate", action="store_true")
    args = ap.parse_args()
    pairs = json.loads(PAIRS.read_text())["pairs"]
    settings = load_settings()
    model = settings.observe_model
    price = TokenFactoryAdapter.PRICING.get(model)
    calls = 4 * len(pairs)
    quote = (
        f"${calls * (EST_TOKENS[0] * price[0] + EST_TOKENS[1] * price[1]) / 1e6:.3f}"
        if price
        else "unknown (no price for this model)"
    )
    print(
        f"{len(pairs)} pairs, up to {calls} calls (plus retries) on {model or 'no model'}; quote {quote}"
    )
    data = Path(args.data)
    crops = crop_index(data)
    missing = _missing(pairs, data, crops)
    if missing:
        print(f"missing images for {missing}: is --data the main checkout's data/?")
        return 2
    if args.dry_run or not args.yes_paid:
        print("quote only: pass --yes-paid to spend")
        return 0
    run_id = uuid.uuid4().hex
    RUNS.mkdir(parents=True, exist_ok=True)
    store = TraceStore(RUNS / "check_scoring_traces.db")
    adapter = bind(
        get_adapter(settings.backend, model, settings), "compare", StageTracer(store, run_id)
    )
    results: list[dict] = []
    skies: dict = {}
    with httpx.Client(timeout=20) as client:
        for p in pairs:
            a = side(p["earlier"], data, crops, client, skies)
            b = side(p["later"], data, crops, client, skies)
            guard = light_mismatch(a.light, b.light)
            if guard:
                got = {"verdict": "cant_tell", "reason": "light changed", "looks": []}
            else:
                c = compare_pair(adapter, a, b, p["signal"], model=model, workers=4)
                looks = [look.model_dump() for look in c.looks]
                got = {"verdict": c.verdict, "reason": c.reason, "looks": looks}
            keep = {k: p[k] for k in ("id", "set", "signal", "expect")}
            results.append({**keep, "light_guard": guard, "light": [a.light, b.light], **got})
            flag = " (light changed)" if guard else ""
            print(f"{p['id']:<13} {p['set']:<8} expect {p['expect']:<5} got {got['verdict']}{flag}")
    judged = gates(results)
    ok, counts = judged["posture"]
    cost = store.summary(run_id)["cost_usd"]
    out = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "pass": ok,
        "counts": counts,
        "gates": {k: {"pass": v[0], "counts": v[1]} for k, v in judged.items()},
        "cost_usd": cost,
        "results": results,
    }
    (RUNS / "check_scoring.json").write_text(json.dumps(out, indent=1))
    for signal, (passed, got) in judged.items():
        print(f"{signal}: {'PASS' if passed else 'FAIL'} {got}")
    print(f"{'PASS' if ok else 'FAIL'} {counts}; cost ${cost:.4f}")
    if args.write_gate:
        gate = json.loads(GATE_PATH.read_text())
        gate["prompt_version"] = PROMPT_VERSION
        for signal, (passed, _) in judged.items():
            gate["signals"][signal] = "passed" if passed else "failed"
        found = ", ".join(f"{k} {v[1]}" for k, v in judged.items())
        gate["note"] = (
            f"set by scripts/check_scoring.py on {date.today()}: {model}, {found}, "
            f"${cost:.3f}; a signal without 10 change and 10 same pairs stays untested"
        )
        GATE_PATH.write_text(json.dumps(gate, indent=2) + "\n")
        print(f"gate written: {gate['signals']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
