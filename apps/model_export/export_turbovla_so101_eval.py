#!/usr/bin/env python
"""Export TurboVLA before/after checkpoints for the SO-101 cobra A/B eval.

before = GroundingDINO init only (no SO-101 action FT)
after  = route-A EMA 20k (cobra-trained)

Both reuse the curated-dataset normalizer stats from the 20-step smoke export
so the preprocessor/postprocessor stay identical across conditions.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from lerobot.policies.turbovla import TurboVLAConfig, TurboVLAPolicy

PROCESSOR_FILES = [
    "policy_preprocessor.json",
    "policy_preprocessor_step_3_normalizer_processor.safetensors",
    "policy_postprocessor.json",
    "policy_postprocessor_step_0_unnormalizer_processor.safetensors",
]


def _export(name: str, init_ckpt: Path, template: Path, out_root: Path, device: str) -> Path:
    dst = out_root / name / "pretrained_model"
    dst.mkdir(parents=True, exist_ok=True)

    cfg = TurboVLAConfig.from_pretrained(template)
    cfg.device = device
    cfg.init_checkpoint = str(init_ckpt)
    cfg.bert_path = str(Path.home() / "models/bert-base-uncased")
    cfg.dinov3_path = str(Path.home() / "models/dinov3-vitb16")

    # Build from config only (do not load the smoke safetensors).
    policy = TurboVLAPolicy(cfg)
    policy.eval()

    # Inference must not re-run init over the saved weights.
    policy.config.init_checkpoint = None
    policy.save_pretrained(dst)

    for name_ in PROCESSOR_FILES:
        shutil.copy2(template / name_, dst / name_)

    print(f"[ok] {name} -> {dst}")
    return dst


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("outputs/train/turbovla_so101_cobra_20261019/checkpoints/last/pretrained_model"),
        help="Smoke export that carries SO-101 feature shapes + normalizer stats",
    )
    parser.add_argument(
        "--gdino",
        type=Path,
        default=Path.home() / "models/groundingdino/groundingdino_swint_ogc.pth",
    )
    parser.add_argument(
        "--ema",
        type=Path,
        default=Path.home()
        / "robot/TurboVLA/results/Checkpoints/turbovla_so101_cobra/checkpoints/steps_20000_ema_pytorch_model.pt",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("outputs/eval/turbovla_cobra_ab"),
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--only", choices=("before", "after", "both"), default="both")
    args = parser.parse_args()

    if not args.template.is_dir():
        raise SystemExit(f"missing template: {args.template}")

    if args.only in ("before", "both"):
        if not args.gdino.is_file():
            raise SystemExit(f"missing GroundingDINO: {args.gdino}")
        _export("before_gdino_init", args.gdino, args.template, args.out_root, args.device)

    if args.only in ("after", "both"):
        if not args.ema.is_file():
            raise SystemExit(f"missing EMA: {args.ema}")
        _export("after_ema20k", args.ema, args.template, args.out_root, args.device)


if __name__ == "__main__":
    main()
