"""The app starts the way production does: create_app() with no deps passed in.

Every other web test passes deps, so a line that only works with test deps (21 Oct: the shop
and local-help finders read deps.http while deps was None) crashed the live container at start
and no test saw it.
"""

from herbtwin.config import load_settings
from herbtwin.web import app as web_app


def test_the_app_starts_with_no_deps_passed_and_the_tavily_extras_on(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # build_deps writes traces.db in the working directory
    env = {
        "HERBTWIN_BACKEND": "mock",
        "HERBTWIN_TAVILY_ENABLED": "1",
        "HERBTWIN_TAVILY_API_KEY": "test-key-not-real",
        "HERBTWIN_SHOP_LINKS": "1",
        "HERBTWIN_LOCAL_HELP": "1",
    }
    monkeypatch.setattr(web_app, "load_settings", lambda: load_settings(env))

    app = web_app.create_app()

    assert app.state.shops is not None
    assert app.state.local_help is not None
