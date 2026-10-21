"""Two real users on the local stack (`supabase start`), for the store's contract tests."""

import subprocess
import uuid

import httpx
import pytest


def local_env() -> dict[str, str]:
    try:
        out = subprocess.run(
            ["supabase", "status", "-o", "env"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("no local Supabase (supabase start)")
    env = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {k: v.strip('"') for k, v in env.items()}


def signed_up(env: dict[str, str]) -> tuple[str, str]:
    """A fresh local user: (access token, user id). Local auth auto-confirms."""
    email = f"{uuid.uuid4().hex[:10]}@store.test"
    r = httpx.post(
        f"{env['API_URL']}/auth/v1/signup",
        headers={"apikey": env["PUBLISHABLE_KEY"]},
        json={"email": email, "password": f"pw-{uuid.uuid4().hex}"},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return d["access_token"], d["user"]["id"]
