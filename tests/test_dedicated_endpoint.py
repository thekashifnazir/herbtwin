import importlib.util
import json
from pathlib import Path

import httpx

_spec = importlib.util.spec_from_file_location(
    "dedicated_endpoint", Path(__file__).parents[1] / "scripts" / "dedicated_endpoint.py"
)
de = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(de)


def _client(seen, reply=None):
    def handle(req):
        seen.append((req.method, str(req.url), req.content))
        return httpx.Response(200, json=reply or {})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_stop_disables_the_endpoint_so_it_stops_billing():
    seen = []
    assert de.main(["stop", "ep1"], _client(seen)) == 0
    method, url, body = seen[0]
    assert method == "PATCH" and url.endswith("/v0/dedicated_endpoints/ep1")
    assert json.loads(body) == {"enabled": False}


def test_create_asks_for_one_h100_and_never_more_than_one_replica():
    seen = []
    de.main(["create"], _client(seen, {"endpoint_id": "ep1", "routing_key": "rk"}))
    sent = json.loads(seen[0][2])
    assert sent["model_name"] == "nvidia/Nemotron-3-Nano-Omni" and sent["gpu_count"] == 1
    assert sent["scaling"] == {"min_replicas": 1, "max_replicas": 1}


def test_printed_summary_keeps_only_known_fields(capsys):
    reply = {"data": [{"id": "ep1", "routing_key": "rk", "secret_thing": "zzz"}]}
    de.main(["status", "ep1"], _client([], reply))
    out = capsys.readouterr().out
    assert "rk" in out and "zzz" not in out


def test_commands_on_one_endpoint_need_its_id():
    assert de.main(["stop"], _client([])) == 2


def test_ready_reads_the_deployment_readiness():
    assert de.ready({"deployment": {"status": "running", "readiness": "ready"}})
    assert not de.ready({"deployment": {"status": "starting", "readiness": "not_ready"}})
    assert not de.ready({"deployment": {"readiness": "partially_ready"}})
