"""Opt-in: uv run pytest -m live -q -rs. Loads .env first so the skip only fires with no key."""

import os
from datetime import UTC, datetime

import pytest
from dotenv import load_dotenv

from herbtwin.config import load_settings
from herbtwin.pipeline import analyse, build_deps

load_dotenv()
pytestmark = pytest.mark.live


@pytest.mark.skipif(
    not os.environ.get("HERBTWIN_NEBIUS_API_KEY"), reason="no HERBTWIN_NEBIUS_API_KEY in .env"
)
def test_real_pipeline_on_sage_photo(tmp_path):
    settings = load_settings()
    assert settings.backend == "tokenfactory", "set HERBTWIN_BACKEND=tokenfactory in .env"
    deps = build_deps(settings, trace_db=tmp_path / "live.db")
    photo_path = settings.photos_dir / "gate" / "sage.jpg"
    assert photo_path.exists(), f"put the risk-gate sage photo at {photo_path}"
    photo = photo_path.read_bytes()
    rec = analyse(deps, photo, "image/jpeg", received=datetime.now(UTC))
    assert rec.observation is not None, rec.failures
    assert rec.observation.is_plant
    assert rec.answer is not None, rec.failures
    s = deps.trace_store.summary(rec.record_id)
    print(f"\nlive run: {s['calls']} calls, ${s['cost_usd']:.4f}, {s['latency_ms']} ms")


@pytest.mark.skipif(
    not os.environ.get("HERBTWIN_NEBIUS_API_KEY"), reason="no HERBTWIN_NEBIUS_API_KEY in .env"
)
def test_real_photo_model_reads_three_photos_of_one_plant_in_one_call():
    # the riskiest assumption of "add up to three photos": the photo model takes several
    # images in one request. Openly licensed photos only: the home page's two basil samples
    # (Forest and Kim Starr, CC BY 3.0 US, one plant on one day) and a close crop of the first
    import io
    from pathlib import Path

    from PIL import Image

    from herbtwin.adapters import get_observe_adapter
    from herbtwin.stages.observe import observe
    from herbtwin.where import strip_metadata

    samples = Path(__file__).parents[1] / "src/herbtwin/web/static/samples"
    main = (samples / "3-basil-yellow-leaves.jpg").read_bytes()
    with Image.open(io.BytesIO(main)) as img:
        w, h = img.size
        buf = io.BytesIO()
        img.crop((w // 3, h // 3, 2 * w // 3, 2 * h // 3)).save(buf, "JPEG", quality=92)
    other = (samples / "6-basil-downy-mildew.jpg").read_bytes()
    photos = [
        (strip_metadata(d, "image/jpeg"), "image/jpeg") for d in (main, buf.getvalue(), other)
    ]
    settings = load_settings()
    assert settings.backend == "tokenfactory", "set HERBTWIN_BACKEND=tokenfactory in .env"
    calls = []
    adapter = get_observe_adapter(settings)
    adapter.on_call = calls.append
    obs = observe(adapter, photos[0][0], "image/jpeg", more=photos[1:])
    assert obs.is_plant and obs.species and "basil" in obs.species[0].common_name.lower()
    assert len(calls) == 1, "one call for all three photos (a repair would make two)"
    c = calls[0]
    print(
        f"\n3-photo read: {c.model} {c.latency_ms} ms, {c.input_tokens} in, "
        f"{c.output_tokens} out, ${c.cost_usd:.4f}"
    )
