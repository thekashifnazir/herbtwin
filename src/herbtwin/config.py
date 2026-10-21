"""Settings from the environment. Loaded once; stages receive a Settings object."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from herbtwin.usage import Limits

Backend = Literal["mock", "tokenfactory", "ollama"]
BACKENDS: tuple[Backend, ...] = ("mock", "tokenfactory", "ollama")


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str | None
    tavily_api_key: str | None
    langsmith_api_key: str | None
    home_lat: float | None  # developer fallback location; deploy leaves it unset
    home_lon: float | None
    photos_dir: Path
    backend: Backend
    observe_model: str
    advise_model: str
    fast_model: str
    tokenfactory_base_url: str
    ollama_base_url: str = "http://localhost:11434/v1/"
    tokenfactory_timeout_s: float = 60.0
    # the photo model's backup (FallbackAdapter) and how long either may take before the
    # next is asked; unset, one photo model with the Token Factory timeout
    observe_fallback_model: str = ""
    observe_timeout_s: float = 60.0
    # models whose server should skip its reasoning step (e.g. Nemotron Omni reading photos)
    no_thinking_models: frozenset[str] = frozenset()
    # accounts and plant history (optional; docs/SUPABASE.md)
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None  # account delete; the local export script
    site_url: str = "http://localhost:8000"  # the app's own address (= dashboard Site URL)
    # web search for the follow-up chat (spec section 6, D42): off unless switched on
    search_enabled: bool = False
    exa_api_key: str | None = None
    tinyfish_api_key: str | None = None  # TinyFish Search and Fetch (free; B5)
    openplantbook_client_id: str | None = None  # light and soil-moisture bands (B5)
    openplantbook_client_secret: str | None = None
    # Kash, 6 Oct: Tavily is kept for the demo but off in development to save credits
    tavily_enabled: bool = False
    # the live site (spec D63): the Worker's shared secret; unset locally, so the guard is off
    edge_secret: str | None = None
    # photo-read caps and the live budget (D59, D60): counted only on the live site
    caps_enabled: bool = False
    limits: Limits = Limits()
    # the budget warning by email through Resend (D60): all three, or no mail
    resend_api_key: str | None = None
    # the plant reads its answer aloud through ElevenLabs; unset, no voice button
    elevenlabs_api_key: str | None = None
    # and only with this on (21 Oct, Kash: "yeah let's get rid then"; it read the answer out
    # and cost $0.05 a play): off by default, so the voice is gone but can come back
    voice_enabled: bool = False
    mail_from: str | None = None
    alert_email: str | None = None
    # signs the unsubscribe link in reminder emails (D65); unset, no reminders at all
    reminder_secret: str | None = None
    judge_code: str | None = None  # the judges' code: skips the caps (D59); unset, no /judge
    # LangSmith traces (D64): on only with langsmith_api_key; deploy sets herbtwin-live
    langsmith_project: str = "herbtwin-dev"
    # the account's own host: an EU account's key gets 403 from the default US one
    langsmith_endpoint: str | None = None
    # the spot answer ("What can I grow here?", spot spec): the live deploy switches it on
    spot_enabled: bool = False
    # the trusted-page check's reader (stages/trusted_page.py), thinking off; round 5 was
    # tested on this model, so another one is untested
    check_model: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    # the trusted-page check itself (stages/trusted_page.py): on unless switched off; it also
    # needs Tavily, the search and Token Factory (pipeline.trusted_check_on)
    trusted_check: bool = True
    # "Shops we found for this" under the answer (shops.py): off unless switched on; it also
    # needs Tavily. Affiliate templates per retailer, "domain={url}-template;…", off unless set
    shop_links: bool = False
    shop_affiliates: str | None = None
    shop_daily_searches: int = 200  # Tavily calls a day for shop links and local help, then none
    # "Gardeners near <town>" under the answer (local_help.py), for a typed UK town; needs Tavily
    local_help: bool = False

    @property
    def tavily_key(self) -> str | None:
        """The Tavily key, only while HERBTWIN_TAVILY_ENABLED is on. Every Tavily use reads this."""
        return self.tavily_api_key if self.tavily_enabled else None

    @property
    def voice_on(self) -> bool:
        """The plant's voice: switched on (HERBTWIN_VOICE_ENABLED) and an ElevenLabs key set."""
        return self.voice_enabled and self.elevenlabs_api_key is not None

    @property
    def accounts_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def home(self) -> tuple[float, float] | None:
        if self.home_lat is None or self.home_lon is None:
            return None
        return self.home_lat, self.home_lon


_DMS = re.compile(
    r"""^\s*(?P<deg>\d{1,3})\s*[°º]\s*(?:(?P<min>\d{1,2})\s*['′’]\s*)?"""
    r"""(?:(?P<sec>\d{1,2}(?:\.\d+)?)\s*["″”]\s*)?(?P<hemi>[NSEW])\s*$""",
    re.IGNORECASE,
)


def parse_coordinate(raw: str, name: str, axis: Literal["lat", "lon"]) -> float:
    """Accept decimal degrees ("51.50", "-0.12") or D°M'S"H ("51°30'26.5\"N").

    The hemisphere letter is required in the DMS form and must match the axis, because a
    longitude pasted without its W silently lands 100 km away. Values must be finite and
    within range.
    """
    text = raw.strip()
    limit = 90.0 if axis == "lat" else 180.0
    try:
        value = float(text)
    except ValueError:
        m = _DMS.match(text)
        if not m:
            raise ValueError(
                f"{name} must be decimal degrees or D°M'S\"H with a hemisphere letter, got {text!r}"
            ) from None
        minutes, seconds = int(m["min"] or 0), float(m["sec"] or 0)
        if minutes >= 60 or seconds >= 60:
            raise ValueError(
                f"{name}: minutes and seconds must be below 60, got {text!r}"
            ) from None
        hemi = m["hemi"].upper()
        if hemi not in ("NS" if axis == "lat" else "EW"):
            raise ValueError(
                f"{name}: hemisphere {hemi} does not belong on a {axis}, got {text!r}"
            ) from None
        value = int(m["deg"]) + minutes / 60 + seconds / 3600
        if hemi in ("S", "W"):
            value = -value
    if not math.isfinite(value) or abs(value) > limit:
        raise ValueError(f"{name} must be within ±{limit:g} degrees, got {text!r}")
    return value


def _positive_seconds(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{key} must be a number of seconds, got {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be positive, got {raw!r}")
    return value


def _positive_number(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{key} must be a number, got {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be positive, got {raw!r}")
    return value


def _positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{key} must be a whole number above 0, got {raw!r}")
    return int(raw)


def _limits(env: Mapping[str, str]) -> Limits:
    d = Limits()
    return Limits(
        day_reads=_positive_int(env, "HERBTWIN_DAILY_READS", d.day_reads),
        visitor_reads=_positive_int(env, "HERBTWIN_VISITOR_READS", d.visitor_reads),
        budget_usd=_positive_number(env, "HERBTWIN_LIVE_BUDGET_USD", d.budget_usd),
        read_cost_usd=_positive_number(env, "HERBTWIN_READ_COST_USD", d.read_cost_usd),
        refine_cost_usd=_positive_number(env, "HERBTWIN_REFINE_COST_USD", d.refine_cost_usd),
        chat_cost_usd=_positive_number(env, "HERBTWIN_CHAT_COST_USD", d.chat_cost_usd),
        voice_cost_usd=_positive_number(env, "HERBTWIN_VOICE_COST_USD", d.voice_cost_usd),
    )


_ON, _OFF = {"1", "true", "yes", "on"}, {"", "0", "false", "no", "off"}


def _count(env: Mapping[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    if not raw.isdigit():
        raise ValueError(f"{key} must be a whole number, got {raw!r}")
    return int(raw)


def _switch(env: Mapping[str, str], key: str) -> bool:
    raw = (env.get(key) or "").strip().lower()
    if raw in _ON:
        return True
    if raw in _OFF:
        return False
    raise ValueError(f"{key} must be one of 1/true/yes/on or 0/false/no/off, got {raw!r}")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ
    has_lat, has_lon = bool(env.get("HERBTWIN_HOME_LAT")), bool(env.get("HERBTWIN_HOME_LON"))
    if has_lat != has_lon:
        raise ValueError("set both or neither of HERBTWIN_HOME_LAT and HERBTWIN_HOME_LON")
    backend = env.get("HERBTWIN_BACKEND", "mock")
    if backend not in BACKENDS:
        raise ValueError(f"HERBTWIN_BACKEND must be one of {', '.join(BACKENDS)}")
    if env.get("HERBTWIN_RECOMMEND_MODEL") and not env.get("HERBTWIN_ADVISE_MODEL"):
        # phase A retired recommend: the one advisor is configured under a new name
        raise ValueError(
            "HERBTWIN_RECOMMEND_MODEL is gone; set HERBTWIN_ADVISE_MODEL "
            "(e.g. nvidia/nemotron-3-super-120b-a12b) in .env"
        )
    nebius_key = env.get("HERBTWIN_NEBIUS_API_KEY") or None
    if backend == "tokenfactory" and not nebius_key:
        raise ValueError("HERBTWIN_NEBIUS_API_KEY is required for the tokenfactory backend")
    site = (env.get("HERBTWIN_SITE_URL") or "http://localhost:8000").strip().rstrip("/")
    if not site.startswith(("http://", "https://")):
        raise ValueError(f"HERBTWIN_SITE_URL must start with http:// or https://, got {site!r}")
    supabase_url = (env.get("HERBTWIN_SUPABASE_URL") or "").strip().rstrip("/") or None
    tf_timeout = _positive_seconds(env, "HERBTWIN_TOKENFACTORY_TIMEOUT_S", 60.0)
    return Settings(
        nebius_api_key=nebius_key,
        tavily_api_key=env.get("HERBTWIN_TAVILY_API_KEY") or None,
        langsmith_api_key=env.get("HERBTWIN_LANGSMITH_API_KEY") or None,
        home_lat=parse_coordinate(env["HERBTWIN_HOME_LAT"], "HERBTWIN_HOME_LAT", "lat")
        if has_lat
        else None,
        home_lon=parse_coordinate(env["HERBTWIN_HOME_LON"], "HERBTWIN_HOME_LON", "lon")
        if has_lon
        else None,
        photos_dir=Path(env.get("HERBTWIN_PHOTOS_DIR", "data/photos")),
        backend=backend,  # type: ignore[arg-type]
        observe_model=env.get("HERBTWIN_OBSERVE_MODEL", ""),
        advise_model=env.get("HERBTWIN_ADVISE_MODEL", ""),
        fast_model=env.get("HERBTWIN_FAST_MODEL", ""),
        check_model=env.get("HERBTWIN_CHECK_MODEL") or Settings.check_model,
        trusted_check=(
            _switch(env, "HERBTWIN_TRUSTED_CHECK")
            if (env.get("HERBTWIN_TRUSTED_CHECK") or "").strip()
            else True
        ),
        tokenfactory_base_url=env.get(
            "HERBTWIN_TOKENFACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
        ),
        ollama_base_url=env.get("HERBTWIN_OLLAMA_BASE_URL", "http://localhost:11434/v1/"),
        tokenfactory_timeout_s=tf_timeout,
        observe_fallback_model=(env.get("HERBTWIN_OBSERVE_FALLBACK_MODEL") or "").strip(),
        observe_timeout_s=_positive_seconds(env, "HERBTWIN_OBSERVE_TIMEOUT_S", tf_timeout),
        no_thinking_models=frozenset(
            m.strip() for m in env.get("HERBTWIN_NO_THINKING_MODELS", "").split(",") if m.strip()
        ),
        supabase_url=supabase_url,
        supabase_publishable_key=env.get("HERBTWIN_SUPABASE_PUBLISHABLE_KEY") or None,
        supabase_secret_key=env.get("HERBTWIN_SUPABASE_SECRET_KEY") or None,
        site_url=site,
        search_enabled=_switch(env, "HERBTWIN_SEARCH_ENABLED"),
        shop_links=_switch(env, "HERBTWIN_SHOP_LINKS"),
        local_help=_switch(env, "HERBTWIN_LOCAL_HELP"),
        shop_affiliates=(env.get("HERBTWIN_SHOP_AFFILIATES") or "").strip() or None,
        shop_daily_searches=_count(env, "HERBTWIN_SHOP_DAILY_SEARCHES", 200),
        exa_api_key=env.get("HERBTWIN_EXA_API_KEY") or None,
        tinyfish_api_key=env.get("HERBTWIN_TINYFISH_API_KEY") or None,
        openplantbook_client_id=env.get("HERBTWIN_OPENPLANTBOOK_CLIENT_ID") or None,
        openplantbook_client_secret=env.get("HERBTWIN_OPENPLANTBOOK_CLIENT_SECRET") or None,
        tavily_enabled=_switch(env, "HERBTWIN_TAVILY_ENABLED"),
        edge_secret=env.get("HERBTWIN_EDGE_SECRET") or None,
        caps_enabled=_switch(env, "HERBTWIN_CAPS_ENABLED"),
        limits=_limits(env),
        judge_code=(env.get("HERBTWIN_JUDGE_CODE") or "").strip() or None,
        reminder_secret=(env.get("HERBTWIN_REMINDER_SECRET") or "").strip() or None,
        resend_api_key=env.get("HERBTWIN_RESEND_API_KEY") or None,
        elevenlabs_api_key=(env.get("HERBTWIN_ELEVENLABS_API_KEY") or "").strip() or None,
        voice_enabled=_switch(env, "HERBTWIN_VOICE_ENABLED"),
        mail_from=(env.get("HERBTWIN_MAIL_FROM") or "").strip() or None,
        alert_email=(env.get("HERBTWIN_ALERT_EMAIL") or "").strip() or None,
        langsmith_project=(env.get("HERBTWIN_LANGSMITH_PROJECT") or "").strip() or "herbtwin-dev",
        langsmith_endpoint=_https_url(env, "HERBTWIN_LANGSMITH_ENDPOINT"),
        spot_enabled=_switch(env, "HERBTWIN_SPOT_ENABLED"),
    )


def _https_url(env: Mapping[str, str], name: str) -> str | None:
    url = (env.get(name) or "").strip().rstrip("/")
    if url and not url.startswith("https://"):
        raise ValueError(f"{name} must start with https://, got {url!r}")
    return url or None
