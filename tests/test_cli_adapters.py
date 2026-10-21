import json
import subprocess

import pytest

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.cli import ClaudeCLIAdapter, CodexCLIAdapter


def _runner(stdout="", code=0, stderr="", seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    return run


def test_claude_cli_runs_without_tools_or_settings_and_returns_the_result():
    seen = {}
    a = ClaudeCLIAdapter("claude-sonnet-5-5", run=_runner(json.dumps({"result": "ok"}), seen=seen))
    assert a.complete("sys", "question") == "ok"
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--system-prompt") + 1] == "sys"
    assert seen["input"] == "question" and seen["cwd"] != "."


def test_claude_cli_error_result_becomes_adapter_error():
    a = ClaudeCLIAdapter("m", run=_runner(json.dumps({"is_error": True, "result": "limit"})))
    with pytest.raises(AdapterError, match="limit"):
        a.complete("s", "u")


def test_codex_cli_reads_the_agent_message_and_prefixes_the_system_text():
    events = [
        {"type": "item.completed", "item": {"type": "reasoning", "text": "hmm"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"better": "A"}'}},
        {"type": "turn.completed", "usage": {}},
    ]
    seen = {}
    a = CodexCLIAdapter("default", run=_runner("\n".join(map(json.dumps, events)), seen=seen))
    assert a.complete("sys", "q") == '{"better": "A"}'
    assert seen["input"].startswith("sys\n\nq") and "--model" not in seen["cmd"]


def test_codex_cli_tool_activity_or_failure_is_an_error():
    tool = {"type": "item.completed", "item": {"type": "command_execution"}}
    with pytest.raises(AdapterError, match="command_execution"):
        CodexCLIAdapter("m", run=_runner(json.dumps(tool))).complete("s", "u")
    with pytest.raises(AdapterError, match="exit 1"):
        CodexCLIAdapter("m", run=_runner("", code=1, stderr="boom")).complete("s", "u")


def test_cli_adapters_are_text_only():
    with pytest.raises(AdapterError, match="text-only"):
        ClaudeCLIAdapter("m", run=_runner()).complete_with_image("s", "u", b"x", "image/jpeg")


def test_claude_cli_skips_terminal_escape_codes_before_the_json():
    esc = "\x1b]6;1;bg;red;brightness;204\x07"
    noisy = esc + json.dumps({"result": "ok"}) + esc + "\n"
    assert ClaudeCLIAdapter("m", run=_runner(noisy)).complete("s", "u") == "ok"


def test_codex_cli_ignores_config_warnings_before_the_turn_starts():
    warn = {
        "type": "item.completed",
        "item": {"type": "error", "message": "Codex is ignoring 1 unrecognized setting"},
    }
    events = [
        {"type": "thread.started"},
        warn,
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
    ]
    a = CodexCLIAdapter("m", run=_runner("\n".join(map(json.dumps, events))))
    assert a.complete("s", "u") == "ok"


def test_codex_cli_error_during_the_turn_still_fails():
    events = [
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "error", "message": "model overloaded"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
    ]
    with pytest.raises(AdapterError, match="model overloaded"):
        CodexCLIAdapter("m", run=_runner("\n".join(map(json.dumps, events)))).complete("s", "u")


def test_codex_cli_pre_turn_error_without_an_answer_still_fails_and_says_why():
    events = [{"type": "item.completed", "item": {"type": "error", "message": "not logged in"}}]
    with pytest.raises(AdapterError, match="no agent message.*not logged in"):
        CodexCLIAdapter("m", run=_runner(json.dumps(events[0]))).complete("s", "u")


def test_a_timed_out_call_does_not_hang_on_a_grandchild_holding_the_pipe():
    # The real failure: codex exec started helper processes that kept stdout open, so a
    # plain subprocess timeout killed the parent and then waited forever for EOF.
    import time

    from herbtwin.adapters.cli import run_in_group

    t0 = time.perf_counter()
    with pytest.raises(subprocess.TimeoutExpired):
        run_in_group(["bash", "-c", "sleep 60 & sleep 60"], input="", timeout=1, cwd=".")
    assert time.perf_counter() - t0 < 10


def test_run_in_group_returns_output_like_subprocess_run():
    from herbtwin.adapters.cli import run_in_group

    proc = run_in_group(["bash", "-c", "cat; echo done"], input="hi\n", timeout=10, cwd=".")
    assert proc.returncode == 0 and proc.stdout == "hi\ndone\n"


def test_codex_judge_runs_without_mcp_servers():
    seen = {}
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}]
    CodexCLIAdapter("m", run=_runner(json.dumps(events[0]), seen=seen)).complete("s", "u")
    cmd = seen["cmd"]
    assert cmd[cmd.index("mcp_servers={}") - 1] == "-c"


def test_a_helper_that_leaves_the_group_cannot_hang_a_timed_out_call():
    # an MCP helper may call setsid() itself and so survive killpg on our group
    import sys
    import time

    from herbtwin.adapters.cli import run_in_group

    escape = (
        "import os, time\n"
        "if os.fork() == 0:\n"
        "    os.setsid(); time.sleep(30)\n"
        "else:\n"
        "    time.sleep(30)\n"
    )
    t0 = time.perf_counter()
    with pytest.raises(subprocess.TimeoutExpired):
        run_in_group([sys.executable, "-c", escape], input="", timeout=1, cwd=".")
    assert time.perf_counter() - t0 < 15
