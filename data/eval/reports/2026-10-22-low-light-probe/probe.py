"""Low-light probe (PREREG.md beside this file). Run from the branch's worktree:
uv run --env-file ../../.env python probe.py OUT.json"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.stages.observe import ObserveError, observe  # noqa: E402

MAIN = Path.cwd()  # the main checkout, which holds data/external
PHOTOS = [
    ("sample-1-parsley-healthy", "src/herbtwin/web/static/samples/1-parsley-healthy.jpg", 0),
    ("sample-3-basil-yellow", "src/herbtwin/web/static/samples/3-basil-yellow-leaves.jpg", 0),
    ("sample-4-rosemary-beetles", "src/herbtwin/web/static/samples/4-rosemary-beetles.jpg", 0),
    (
        "sample-5-coriander-flowering",
        "src/herbtwin/web/static/samples/5-coriander-flowering.jpg",
        0,
    ),
    ("sample-6-basil-mildew", "src/herbtwin/web/static/samples/6-basil-downy-mildew.jpg", 0),
    ("sample-7-pea-bed", "src/herbtwin/web/static/samples/7-pea-bed.jpg", 0),
    ("se-37744-leggy-basil", str(MAIN / "data/external/s3/images/37744_0.jpg"), 1),
    ("se-55376-leggy-kalanchoe", str(MAIN / "data/external/s3/images/55376_0.jpg"), 1),
    ("se-22693-etiolated-sedum", str(MAIN / "data/external/s3/images/22693_0.jpg"), 1),
]
settings = load_settings()
spent = [0.0]
rows = []
import os  # noqa: E402

# the deployed backup (the private working repo's `deploy.sh`); the local settings leave it unset
BACKUP = settings.observe_fallback_model or "deepseek-ai/DeepSeek-V4.1-Flash"
ROLES = [("main", settings.observe_model), ("backup", BACKUP)]
ROLES = [r for r in ROLES if r[0] in os.environ.get("PROBE_ROLES", "main,backup").split(",")]
for role, model in ROLES:
    adapter = get_adapter("tokenfactory", model, settings, timeout_s=120)
    adapter.on_call = lambda rec: spent.__setitem__(0, spent[0] + (rec.cost_usd or 0.0))
    for pid, path, truth in PHOTOS:
        if spent[0] >= 1.0:
            raise SystemExit("budget reached")
        t0 = time.perf_counter()
        try:
            obs = observe(adapter, Path(path).read_bytes(), "image/jpeg", hedge_after_s=None)
            got = {
                "low_light": obs.low_light,
                "setting": obs.setting,
                "species": obs.species[0].common_name if obs.species else None,
                "notes": obs.notes,
            }
        except ObserveError as e:
            got = {"error": str(e)[:200]}
        rows.append(
            {
                "role": role,
                "model": model,
                "photo": pid,
                "truth_min": truth,
                "seconds": round(time.perf_counter() - t0, 1),
                **got,
            }
        )
        print(role, pid, got.get("low_light", got.get("error")), flush=True)
Path(sys.argv[1]).write_text(json.dumps({"spent_usd": round(spent[0], 4), "rows": rows}, indent=1))
print("spent", round(spent[0], 4))
