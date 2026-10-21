"""LoRA SFT of Nemotron 3 Nano 4B on the advice examples, then merge (runs in the GPU job).

  python train.py --data /work/data/train/advice-se.jsonl --out /work/merged [--max-steps 10]

Prompt-completion pairs: the prompt is the chat template applied to system + user with
thinking off (as the eval serves it), the completion is the teacher's JSON and the end of
turn, so the loss falls on the reply only. LoRA leaves the Mamba out_proj alone: the fused
kernel reads that weight directly and vLLM cannot serve LoRA on it, so the adapter is
merged into the weights before serving (NVIDIA's own Nano 4B PEFT recipe does the same).
"""

from __future__ import annotations

import argparse
import json
import time

import torch
from datasets import Dataset
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE = "nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16"
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "in_proj"]


def pairs(path: str, tok) -> Dataset:
    rows = []
    for line in open(path):
        msgs = json.loads(line)["messages"]
        prompt = tok.apply_chat_template(
            msgs[:2], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        rows.append({"prompt": prompt, "completion": msgs[2]["content"] + "<|im_end|>\n"})
    return Dataset.from_list(rows)


def save_merged(peft_model, tok, out: str) -> None:
    merged = peft_model.merge_and_unload()
    # the base ships top_p 0.95 without do_sample, which transformers 5 refuses to save;
    # keep its sampling defaults (vLLM reads them) and make the pair valid
    merged.generation_config.do_sample = True
    merged.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--max-steps", type=int, default=-1, help="a smoke run stops early")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--adapter-out", default="/work/out/adapter", help="copied off the job")
    ap.add_argument("--merge-only", help="an adapter from a preempted job: merge, no training")
    args = ap.parse_args()

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    print(f"TRAIN loaded {BASE} in {time.time() - t0:.0f}s", flush=True)
    if args.merge_only:
        save_merged(PeftModel.from_pretrained(model, args.merge_only), tok, args.out)
        print(
            f"TRAIN merged {args.merge_only} to {args.out} at {time.time() - t0:.0f}s", flush=True
        )
        return
    present = {n.rsplit(".", 1)[-1] for n, _ in model.named_modules()}
    targets = [t for t in TARGETS if t in present]
    print(f"TRAIN lora targets {targets}", flush=True)
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.rank,
            lora_alpha=2 * args.rank,
            lora_dropout=0.05,
            target_modules=targets,
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()
    data = pairs(args.data, tok)
    print(f"TRAIN examples {len(data)}", flush=True)
    cfg = SFTConfig(
        output_dir="/work/ckpt",
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        # batch 1: without the mamba-ssm kernels the reference scan's memory grows with the
        # padded batch (a batch of 4 tried to allocate 77 GB); same effective batch of 8
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=5,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        completion_only_loss=True,
        max_length=4096,
    )
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=data, processing_class=tok)
    out = trainer.train()
    print(f"TRAIN done loss={out.training_loss:.4f} in {time.time() - t0:.0f}s", flush=True)
    trainer.model.save_pretrained(args.adapter_out)  # small: copied off before the merge
    print(f"TRAIN adapter saved to {args.adapter_out}", flush=True)
    save_merged(trainer.model, tok, args.out)
    print(f"TRAIN merged to {args.out} at {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
