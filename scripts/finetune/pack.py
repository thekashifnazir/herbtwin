"""Pack the GPU job's inputs into one tarball, copied into the job over SSH.

  uv run --with pyarrow python scripts/finetune/pack.py --main "$MAIN" --out <file.tgz>

The payload unpacks to /work: the repo's source and eval script (no web assets), the two
eval sets, the question text of only the eval's held-out items (SE spaced sample and the
MIRAGE set), the training file and the job scripts. Nothing private: no .env, no keys.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from herbtwin.evals.finetune_data import held_out_ids  # noqa: E402
from herbtwin.evals.items import load_set  # noqa: E402

SE = Path("s3/se_diagnosis_herb.jsonl")
MIRAGE = Path("s5/MIRAGE/MMST_Contextual/test-0000-of-0001.parquet")
TRACKED = ["src", "scripts/eval_advice.py", "pyproject.toml", "README.md"]
SKIP_SUFFIXES = (".jpg", ".png", ".webp", ".woff2", ".woff", ".ico", ".svg", ".css", ".js")


def add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o755 if name.endswith(".sh") else 0o644
    tar.addfile(info, io.BytesIO(data))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--main", type=Path, required=True, help="the main checkout (external data)")
    ap.add_argument("--train", type=Path, default=ROOT / "data/train/advice-se.jsonl")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--adapter", type=Path, help="a trained adapter dir: the job merges it")
    args = ap.parse_args()
    import pyarrow.parquet as pq

    items = load_set(ROOT / "data/eval/sets/actions_se.jsonl")
    mirage_ids = {i.id for i in load_set(ROOT / "data/eval/sets/actions_mirage.jsonl")}
    held = held_out_ids(items, limit=150)
    se_lines = [
        line
        for line in (args.main / "data/external" / SE).read_text().splitlines()
        if line.strip() and f"actions_se/{json.loads(line)['id']}" in held
    ]
    table = pq.read_table(args.main / "data/external" / MIRAGE)
    keep = [f"actions_mirage/{i}" in mirage_ids for i in table.column("id").to_pylist()]
    import pyarrow as pa

    mirage = io.BytesIO()
    pq.write_table(
        table.filter(pa.array(keep)).drop_columns(
            [c for c in table.column_names if c not in ("id", "messages")]
        ),
        mirage,
    )

    buf = io.BytesIO()
    files = subprocess.run(
        ["git", "ls-files", *TRACKED], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for f in files:
            if not f.endswith(SKIP_SUFFIXES):
                add_bytes(tar, f"work/repo/{f}", (ROOT / f).read_bytes())
        for s in ("actions_se", "actions_mirage"):
            p = f"data/eval/sets/{s}.jsonl"
            add_bytes(tar, f"work/repo/{p}", (ROOT / p).read_bytes())
        add_bytes(tar, f"work/external/{SE}", ("\n".join(se_lines) + "\n").encode())
        add_bytes(tar, f"work/external/{MIRAGE}", mirage.getvalue())
        add_bytes(tar, "work/train/advice-se.jsonl", args.train.read_bytes())
        if args.adapter:
            for f in sorted(args.adapter.iterdir()):
                add_bytes(tar, f"work/adapter/{f.name}", f.read_bytes())
        for f in ("train.py", "run.sh", "boot.sh"):
            add_bytes(tar, f"work/{f}", (ROOT / "scripts/finetune" / f).read_bytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(buf.getvalue())
    print(
        f"{len(se_lines)} SE questions, {sum(keep)} MIRAGE rows, payload {len(buf.getvalue())} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
