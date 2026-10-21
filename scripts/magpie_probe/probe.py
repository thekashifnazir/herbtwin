"""Runs inside the Nebius GPU job: Magpie TTS renders every line with every baked English
voice, then Parakeet transcribes each clip back (the round trip that score.py turns into a
word error rate). Writes /work/out/raw.jsonl, /work/out/timings.json and the wav files.

  python3 probe.py --lines lines.json --out /work/out [--limit N]

Timings are wall clock on the GPU, with torch.cuda.synchronize around each call.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

T0 = time.time()
STAMPS: dict[str, float] = {}


def stamp(name: str) -> None:
    STAMPS[name] = round(time.time() - T0, 2)
    print(f"STAMP {name} +{STAMPS[name]}s", flush=True)


def changed_lines(lines: list[dict], normalised: dict[str, str]) -> dict[str, str]:
    """The normalised pass: only lines whose normalised text differs from the raw text (the
    rest would repeat the raw pass), and only lines in this run."""
    raw = {x["id"]: x["text"] for x in lines}
    return {k: v for k, v in normalised.items() if k in raw and v != raw[k]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0, help="lines per voice (0 = all)")
    ap.add_argument("--tts", default="nvidia/magpie_tts_multilingual_357m")
    ap.add_argument("--asr", default="nvidia/parakeet-tdt-0.6b-v2")
    ap.add_argument("--device", default="cuda", help="cpu for a free local check of the script")
    ap.add_argument("--voices", type=int, default=0, help="first N voices only (0 = all)")
    ap.add_argument("--tn-file", type=Path, help="tn.py output; adds the normalised pass")
    ap.add_argument("--tn-wait", type=int, default=600, help="seconds to wait for --tn-file")
    ap.add_argument("--raw-lines", default="", help="comma ids for the raw pass (default all)")
    ap.add_argument("--stop-synth-at", type=float, default=0, help="epoch s: stop synthesis")
    args = ap.parse_args()
    lines = json.loads(args.lines.read_text())
    if args.limit:
        lines = lines[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import soundfile as sf
    import torch

    cuda = args.device == "cuda"

    def sync() -> None:
        if cuda:
            torch.cuda.synchronize()

    stamp("import_torch")
    from huggingface_hub import hf_hub_download
    from nemo.collections.tts.models import MagpieTTSModel

    stamp("import_nemo")
    path = hf_hub_download(args.tts, "magpie_tts_multilingual_357m.nemo")
    stamp("download_tts")
    model = MagpieTTSModel.restore_from(path, map_location="cpu").to(args.device).eval()
    sync()
    stamp("load_tts")
    n_voices = model.num_baked_speakers
    names = ["Aria", "Jason", "John", "Leo", "Sofia"]  # the model card's speaker_map order
    voices = [(i, names[i] if i < len(names) else f"speaker{i}") for i in range(n_voices)]
    if args.voices:
        voices = voices[: args.voices]
    print(f"VOICES {n_voices}: {voices}", flush=True)
    sr = model.output_sample_rate if hasattr(model, "output_sample_rate") else 22050

    t = time.time()
    model.do_tts("Hello from the garden.", language="en", apply_TN=False, speaker_index=0)
    sync()
    first_call = round(time.time() - t, 3)
    stamp("first_tts_call")

    rows = []
    wav_dir = args.out / "wav"
    wav_dir.mkdir(exist_ok=True)
    raw_ids = set(args.raw_lines.split(",")) if args.raw_lines else {x["id"] for x in lines}
    passes = [("raw", {x["id"]: x["text"] for x in lines if x["id"] in raw_ids})]
    tn_build_s = None
    if args.tn_file:
        deadline = time.time() + args.tn_wait
        if args.stop_synth_at:
            deadline = min(deadline, args.stop_synth_at)
        # the raw pass runs first while tn.py compiles its grammars on the CPU
        passes.append(("tn", None))
    for tag, texts in passes:
        if texts is None:
            while not args.tn_file.exists() and time.time() < deadline:
                time.sleep(2)
            if not args.tn_file.exists():
                print("NOTE no text normalisation file in time; tn pass skipped", flush=True)
                continue
            tn = json.loads(args.tn_file.read_text())
            tn_build_s = tn["build_s"]
            print(f"NOTE tn_build_s {tn_build_s}", flush=True)
            texts = changed_lines(lines, tn["lines"])
            stamp("tn_ready")
        # line-major, so a deadline drops whole lines, never whole voices
        for line_id, text in texts.items():
            for idx, voice in voices:
                if args.stop_synth_at and time.time() > args.stop_synth_at:
                    print(f"NOTE synthesis deadline: stopped at {tag} {line_id}", flush=True)
                    break
                row = {"tn": tag, "voice": voice, "line": line_id, "text": text}
                try:
                    sync()
                    t = time.time()
                    audio, audio_len = model.do_tts(
                        text, language="en", apply_TN=False, speaker_index=idx
                    )
                    sync()
                    synth = time.time() - t
                    x = audio[0, : int(audio_len[0])].float().cpu().numpy()
                    dur = len(x) / sr
                    peak = float(np.max(np.abs(x))) if len(x) else 0.0
                    rms = float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
                    wav = wav_dir / f"{tag}-{voice}-{line_id}.wav"
                    sf.write(wav, x, sr, subtype="PCM_16")
                    row |= {
                        "synth_s": round(synth, 3),
                        "audio_s": round(dur, 3),
                        "rtf": round(synth / dur, 4) if dur else None,
                        "peak": round(peak, 4),
                        "rms_dbfs": round(20 * np.log10(rms), 2) if rms else None,
                        "clip_frac": round(float(np.mean(np.abs(x) >= 0.999)), 6),
                        "wav": wav.name,
                    }
                except Exception as exc:  # one bad clip must not end the run
                    row["error"] = f"{type(exc).__name__}: {exc}"[:300]
                print("CLIP", json.dumps(row), flush=True)
                rows.append(row)
    stamp("tts_done")

    del model
    if cuda:
        torch.cuda.empty_cache()
    import librosa
    from nemo.collections.asr.models import ASRModel

    asr = ASRModel.from_pretrained(args.asr).to(args.device).eval()
    stamp("load_asr")
    ok = [r for r in rows if "wav" in r]
    audio16 = []
    for r in ok:
        x, s = sf.read(wav_dir / r["wav"], dtype="float32")
        audio16.append(librosa.resample(x, orig_sr=s, target_sr=16000))
    t = time.time()
    hyps = asr.transcribe(audio16, batch_size=16)
    asr_s = round(time.time() - t, 2)
    for r, h in zip(ok, hyps, strict=True):
        r["asr"] = h.text if hasattr(h, "text") else str(h)
        print("ASR", json.dumps({k: r[k] for k in ("tn", "voice", "line", "asr")}), flush=True)
    stamp("asr_done")

    with (args.out / "raw.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta = {
        "stamps": STAMPS,
        "first_tts_call_s": first_call,
        "asr_batch_s": asr_s,
        "voices": voices,
        "passes": [p[0] for p in passes],
        "tn_build_s": tn_build_s,
        "gpu": torch.cuda.get_device_name(0) if cuda else "cpu",
        "torch": torch.__version__,
        "sample_rate": sr,
        "peak_mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2) if cuda else None,
    }
    import nemo

    meta["nemo"] = nemo.__version__
    (args.out / "timings.json").write_text(json.dumps(meta, indent=1))
    print("META", json.dumps(meta), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
