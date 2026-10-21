"""The self-hosted Nemotron Nano job (19 Oct, Kash's yes, cap $12): the flags that bound its
cost and keep its run comparable with Token Factory's are pinned here."""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts" / "nano_selfhost"
JOB = (HERE / "job.sh").read_text()
SERVE = (HERE / "serve.sh").read_text()


def test_the_job_is_one_spot_b300_with_the_minimum_platform_timeout():
    create = JOB.split("  create)", 1)[1].split("\n    ;;", 1)[0]
    assert "--platform gpu-b300-sxm --preset 1gpu-24vcpu-346gb" in create
    assert "--preemptible --follows-spot-price" in create
    assert "--timeout 1h" in create and "--restart-policy never" in create
    # 1 h at the on-demand B300 price ($9.50/h) is the most one job can cost: under the $12 cap
    hours = int(re.search(r"--timeout (\d+)h", create)[1])
    assert hours * 9.50 <= 12


def test_the_server_exits_before_the_platform_timeout():
    hold = int(re.search(r'HOLD_MIN="\$\{HOLD_MIN:-(\d+)\}"', SERVE)[1])
    assert hold < 60


def test_it_serves_the_open_weights_under_token_factorys_name_with_thinking_off():
    assert "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16" in SERVE
    assert 'SERVED="${SERVED:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B}"' in SERVE
    assert "--reasoning-parser nemotron_v3" in SERVE  # any thinking stays out of the answer
    # off, as the app runs Nano on Token Factory (no_thinking_models; prereg amendment 1)
    assert """--default-chat-template-kwargs '{"enable_thinking": false}'""" in SERVE


def test_no_key_or_token_is_sent_to_the_job():
    assert "HF_TOKEN" not in JOB + SERVE and "--env-secret" not in JOB
    assert "NEBIUS_API_KEY" not in JOB + SERVE


def _create(tmp_path, out='echo \'{"resource_id": "job-x"}\'', key="k.pub", **env):
    # a stand-in nebius CLI: records each call, answers `ai job list` with $LIST and prints
    # `out` for anything else (`ai job create`)
    import os
    import subprocess

    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    fake = bin_ / "nebius"
    fake.write_text(
        '#!/usr/bin/env bash\necho "$@" >> "$CALLS"\n'
        'case "$*" in *"job list"*) echo "$LIST"; exit "${LIST_EXIT:-0}" ;; esac\n'
        f"{out}\n"
    )
    fake.chmod(0o755)
    if not (tmp_path / "k.pub").exists():
        cmd = ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / "k")]
        subprocess.run(cmd, check=True)
    run_env = {
        **os.environ,
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "CALLS": str(tmp_path / "calls"),
        "LEDGER": str(tmp_path / "ledger.txt"),
        "LIST": '{"items": []}',
        **env,
    }
    cmd = ["bash", str(HERE / "job.sh"), "create", str(tmp_path / key)]
    return subprocess.run(cmd, env=run_env, capture_output=True, text=True)


def _calls(tmp_path):
    # the `ai job create` calls only
    f = tmp_path / "calls"
    return sum("job create" in c for c in f.read_text().splitlines()) if f.exists() else 0


def _listed(*states):
    import json

    jobs = [{"metadata": {"name": "nano-selfhost"}, "status": {"state": s}} for s in states]
    jobs.append({"metadata": {"name": "other"}, "status": {"state": "RUNNING"}})
    return json.dumps({"items": jobs})


def test_every_nebius_call_names_a_cli_profile(tmp_path):
    _create(tmp_path)
    calls = (tmp_path / "calls").read_text().splitlines()
    assert len(calls) == 2 and all(c.startswith("--profile kash ai job ") for c in calls)
    _create(tmp_path, NEBIUS_PROFILE="other", BILLED_USD="1")
    assert (tmp_path / "calls").read_text().splitlines()[-1].startswith("--profile other ")
    # no bare `nebius` call is left in the script
    assert not re.search(r"^\s*(\w+=\$\()?nebius ", JOB, re.M)


def test_create_refuses_anything_but_a_public_key(tmp_path):
    # a private key would be uploaded to the job
    _create(tmp_path, out="true")
    (tmp_path / "ledger.txt").unlink()
    for key in ("k", "missing.pub"):
        refused = _create(tmp_path, key=key)
        assert refused.returncode == 3 and "not an SSH public key" in refused.stdout
    (tmp_path / "fake.pub").write_text("ssh-ed25519 AAAA not-a-key")
    assert _create(tmp_path, key="fake.pub").returncode == 3
    assert _calls(tmp_path) == 1 and not (tmp_path / "ledger.txt").exists()


def test_jobs_nebius_lists_count_even_with_an_empty_ledger(tmp_path):
    # review 19 Oct: the ledger lives in one worktree; another checkout would start at zero
    two = _create(tmp_path, LIST=_listed("CANCELLED", "COMPLETED"), BILLED_USD="0")
    assert two.returncode == 3 and "Nebius 2" in two.stdout
    one = _create(tmp_path, LIST=_listed("FAILED"))
    assert one.returncode == 3 and "BILLED_USD" in one.stdout
    live = _create(tmp_path, LIST=_listed("RUNNING"), BILLED_USD="0")
    assert live.returncode == 3 and "still live" in live.stdout
    failed = _create(tmp_path, LIST="", LIST_EXIT="1")
    assert failed.returncode != 0
    # valid JSON from a failed CLI call still stops it (pipefail)
    assert _create(tmp_path, LIST='{"items": []}', LIST_EXIT="1").returncode != 0
    # an unknown shape is refused, not read as zero jobs
    odd = _create(tmp_path, LIST='{"jobs": [1]}')
    assert odd.returncode != 0 and "no items key" in odd.stderr
    assert _calls(tmp_path) == 0 and not (tmp_path / "ledger.txt").exists()
    assert _create(tmp_path, LIST=_listed("FAILED"), BILLED_USD="1.2").returncode == 0


def test_a_preemption_allows_one_re_create_only_when_the_first_job_was_cheap(tmp_path):
    # prereg amendment 2: two jobs at the on-demand price ($19) would pass the $12 cap
    first = _create(tmp_path)
    assert first.returncode == 0 and first.stdout.strip() == "job-x" and _calls(tmp_path) == 1
    for billed in ({}, {"BILLED_USD": "3"}, {"BILLED_USD": "nan"}):
        refused = _create(tmp_path, **billed)
        assert refused.returncode == 3 and "REFUSED" in refused.stdout
    assert _calls(tmp_path) == 1  # refused before the CLI was called
    assert _create(tmp_path, BILLED_USD="2.10").returncode == 0 and _calls(tmp_path) == 2
    third = _create(tmp_path, BILLED_USD="0")
    assert third.returncode == 3 and _calls(tmp_path) == 2


def test_a_done_request_before_ready_still_ends_the_job():
    wait = SERVE.split("until curl", 1)[1].split("done\n", 1)[0]
    assert "/tmp/done" in wait


def test_a_job_whose_output_does_not_parse_still_counts_against_the_cap(tmp_path):
    # review 19 Oct: a billed job with no ledger line would let a retry start a second job
    garbled = _create(tmp_path, out='echo "warning: new version"')
    assert "id not parsed" in garbled.stdout
    assert len((tmp_path / "ledger.txt").read_text().splitlines()) == 1
    assert _create(tmp_path).returncode == 3  # a re-create still needs BILLED_USD


def test_the_job_id_is_read_past_other_lines_and_pretty_json(tmp_path):
    out = """echo "note: spot"; printf '{\\n  "resource_id": "job-y"\\n}\\n'"""
    assert _create(tmp_path, out=out).stdout.strip() == "job-y"


def _stub_server(content):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            reply = {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            body = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def _check():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check", HERE / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_refuses_an_empty_answer(capsys):
    server, _ = _stub_server("")
    try:
        assert _check().main(["--base-url", f"http://127.0.0.1:{server.server_port}/v1/"]) == 1
    finally:
        server.shutdown()
    assert "NOT VALID ADVICE" in capsys.readouterr().out


def test_check_sends_the_evals_request_and_passes_valid_advice(capsys):
    import json

    advice = {"actions": ["shelter"], "primary": "shelter", "answer": "Shade it.", "ask": ""}
    server, seen = _stub_server(json.dumps(advice))
    try:
        assert _check().main(["--base-url", f"http://127.0.0.1:{server.server_port}/v1/"]) == 0
    finally:
        server.shutdown()
    assert "OK" in capsys.readouterr().out
    (body,) = seen
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["type"] == "json_schema" and body["temperature"] == 0


def test_an_empty_job_list_reads_as_no_jobs(tmp_path):
    assert _create(tmp_path, LIST="{}").returncode == 0 and _calls(tmp_path) == 1
