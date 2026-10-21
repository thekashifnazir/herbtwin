"""Start, check and stop a Token Factory dedicated endpoint (billed per GPU-minute while ready).

Usage:
  uv run python scripts/dedicated_endpoint.py create   # Nemotron 3 Nano Omni on 1x H100, eu-north1
  uv run python scripts/dedicated_endpoint.py status [ID]
  uv run python scripts/dedicated_endpoint.py wait ID   # until ready; prints the routing key
  uv run python scripts/dedicated_endpoint.py stop ID   # enabled=false: no charge, can start again
  uv run python scripts/dedicated_endpoint.py start ID
  uv run python scripts/dedicated_endpoint.py delete ID

Uses the project key from settings and never prints it. Docs:
https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/operating.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.config import load_settings  # noqa: E402

CONTROL = "https://api.tokenfactory.nebius.com/v0/dedicated_endpoints"
OMNI = {
    "name": "herbtwin-omni-probe",
    "description": "Nemotron 3 Nano Omni reading plant photos (herbtwin probe)",
    "model_name": "nvidia/Nemotron-3-Nano-Omni",
    "flavor_name": "base",
    "gpu_type": "gpu-h100-sxm",
    "gpu_count": 1,
    "region": "eu-north1",
    "scaling": {"min_replicas": 1, "max_replicas": 1},
}
SHOWN = (
    "endpoint_id",
    "id",
    "name",
    "model_name",
    "routing_key",
    "status",
    "readiness",
    "lifecycle",
    "enabled",
    "region",
    "gpu_type",
    "gpu_count",
    "deployment",
    "created_at",
)


def summary(ep: dict) -> dict:
    """The fields worth printing; everything else stays out of the log."""
    return {k: ep[k] for k in SHOWN if k in ep}


def ready(ep: dict) -> bool:
    return (ep.get("deployment") or {}).get("readiness") == "ready"


def main(argv: list[str], client: httpx.Client | None = None) -> int:
    if not argv or argv[0] not in ("create", "status", "wait", "stop", "start", "delete"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if client is None:
        key = load_settings().nebius_api_key
        client = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60)
    if cmd == "create":
        r = client.post(CONTROL, json=OMNI)
    elif cmd == "status" and not rest:
        r = client.get(CONTROL)
    elif not rest:
        print(f"{cmd} needs an endpoint id", file=sys.stderr)
        return 2
    elif cmd == "status":
        r = client.get(CONTROL)  # no GET by id (405): list and pick
    elif cmd == "wait":
        while True:
            r = client.get(CONTROL)
            r.raise_for_status()
            mine = [e for e in r.json().get("data", []) if e.get("id") == rest[0]]
            if not mine:
                print(f"no endpoint {rest[0]}", file=sys.stderr)
                return 1
            if ready(mine[0]):
                break
            print(time.strftime("%H:%M:%S"), "not ready yet", flush=True)
            time.sleep(30)
    elif cmd in ("stop", "start"):
        r = client.patch(f"{CONTROL}/{rest[0]}", json={"enabled": cmd == "start"})
    else:
        r = client.delete(f"{CONTROL}/{rest[0]}")
    print(cmd, r.status_code)
    if r.status_code >= 400:
        print(r.text[:500])
        return 1
    if r.content:
        body = r.json()
        items = body.get("items", body.get("data")) if isinstance(body, dict) else body
        eps = items if isinstance(items, list) else [body]
        if cmd in ("status", "wait") and rest:
            eps = [e for e in eps if e.get("id") == rest[0]]
        for ep in eps:
            print(json.dumps(summary(ep), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
