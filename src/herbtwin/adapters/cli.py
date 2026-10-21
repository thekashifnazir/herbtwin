"""Subscription CLI models (Claude Code, Codex) as text adapters for eval judges.

No API key and no per-call bill: each call runs the vendor CLI non-interactively in an
empty scratch directory with tools disabled, so the judge sees only the prompt. Text
only; image judging stays on the local and Token Factory adapters for now.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable

from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter

Runner = Callable[..., subprocess.CompletedProcess]


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # already gone, or (macOS) only the dead, unreaped leader is left
        pass


def run_in_group(
    cmd: list[str], *, input: str, timeout: float, cwd: str, **_: object
) -> subprocess.CompletedProcess:
    """subprocess.run, but the command gets its own process group and the whole group is
    killed on timeout. A CLI that starts helper processes (MCP servers) which inherit
    stdout would otherwise keep the pipe open, and a plain timeout then waits forever."""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # a helper that left the group (setsid) still holds the pipe: stop reading
            proc.kill()
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
        raise
    finally:
        # helpers left behind by a finished call go too
        _kill_group(proc.pid)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


class _CLIAdapter(ModelAdapter):
    timeout_s = 180

    def __init__(self, model: str, run: Runner = run_in_group) -> None:
        self.model = model
        self._run = run
        self._cwd = tempfile.mkdtemp(prefix=f"herbtwin-{self.name}-")

    def _command(self, system: str) -> list[str]:
        raise NotImplementedError

    def _answer(self, stdout: str) -> str:
        raise NotImplementedError

    def _input(self, system: str, user: str) -> str:
        return user

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        t0 = time.perf_counter()
        try:
            proc = self._run(
                self._command(system),
                input=self._input(system, user),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=self._cwd,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise AdapterError(f"{self.name} {self.model}: {e}") from e
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            raise AdapterError(f"{self.name} {self.model}: exit {proc.returncode}: {tail}")
        out = self._answer(proc.stdout)
        self._record(
            CallRecord(
                model=self.model,
                stage=self.stage,
                prompt=f"{system}\n\n{user}",
                output=out,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                local=False,
            )
        )
        return out

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        raise AdapterError(f"{self.name} adapter is text-only")


class ClaudeCLIAdapter(_CLIAdapter):
    name = "claude-cli"

    def _command(self, system: str) -> list[str]:
        return [
            "claude",
            "-p",
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--system-prompt",
            system,
            "--model",
            self.model,
            "--output-format",
            "json",
        ]

    def _answer(self, stdout: str) -> str:
        # a local launcher may print terminal escape codes before the JSON object
        # (and again after it): decode the first JSON object only
        start = stdout.find("{")
        try:
            data, _ = json.JSONDecoder().raw_decode(stdout[max(start, 0) :])
        except json.JSONDecodeError as e:
            raise AdapterError(f"claude-cli: unreadable output: {stdout[-200:]}") from e
        if data.get("is_error"):
            raise AdapterError(f"claude-cli: {str(data.get('result'))[:300]}")
        return str(data.get("result", ""))


class CodexCLIAdapter(_CLIAdapter):
    name = "codex-cli"

    def _command(self, system: str) -> list[str]:
        cmd = [
            "codex",
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-c",
            'web_search="disabled"',
            # no MCP servers: a judge needs no tools, and the ones in a shared
            # ~/.codex/config.toml start helper processes on every call
            "-c",
            "mcp_servers={}",
        ]
        if self.model and self.model != "default":
            cmd += ["--model", self.model]
        return cmd + ["-"]

    def _input(self, system: str, user: str) -> str:
        # codex exec takes one prompt; the system text leads it
        return f"{system}\n\n{user}"

    def _answer(self, stdout: str) -> str:
        answer = None
        in_turn = False
        notices: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.started":
                in_turn = True
            elif event.get("type") == "item.completed":
                item = event.get("item") or {}
                kind = item.get("type")
                if kind == "agent_message":
                    answer = str(item.get("text") or "")
                elif kind == "error" and not in_turn:
                    # startup notices (e.g. an unrecognised setting in the user's
                    # config.toml) arrive as error items before the turn; not a failure
                    # by themselves, but kept in case no answer follows
                    notices.append(str(item.get("message"))[:200])
                    continue
                elif kind == "error":
                    raise AdapterError(f"codex-cli: {str(item.get('message'))[:300]}")
                elif kind not in ("reasoning", None):
                    raise AdapterError(f"codex-cli: unexpected {kind} item")
            elif event.get("type") in ("error", "turn.failed"):
                raise AdapterError(f"codex-cli: {json.dumps(event)[:300]}")
        if answer is None:
            detail = f" (startup notices: {' | '.join(notices)})" if notices else ""
            raise AdapterError(f"codex-cli: no agent message{detail}")
        return answer
