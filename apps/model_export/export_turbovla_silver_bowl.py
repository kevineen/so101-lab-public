#!/usr/bin/env python
"""Export silver-bowl TurboVLA EMA into a self-contained lerobot pretrained_model."""

from __future__ import annotations

from pathlib import Path

from lerobot.configs import FeatureType
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.turbovla import TurboVLAConfig, TurboVLAPolicy, make_turbovla_pre_post_processors
from lerobot.utils.feature_utils import dataset_to_policy_features

REPO_ID = "local/so101_singlearm_pickup_cobra_rgb_20261020_225627"
ROOT = Path.home() / ".cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_rgb_20261020_225627"
EMA = (
    Path.home()
    / "robot/TurboVLA/results/Checkpoints/turbovla_so101_cobra_silver_bowl/checkpoints"
    / "steps_7000_ema_pytorch_model.pt"
)
OUT = Path("outputs/eval/turbovla_cobra_silver_bowl_ema7000/pretrained_model")


def main() -> None:
    if not EMA.is_file():
        raise SystemExit(f"missing EMA: {EMA}")

    ds = LeRobotDataset(repo_id=REPO_ID, root=ROOT)
    features = dataset_to_policy_features(ds.meta.features)

    cfg = TurboVLAConfig()
    cfg.device = "cpu"
    cfg.output_features = {k: ft for k, ft in features.items() if ft.type is FeatureType.ACTION}
    cfg.input_features = {k: ft for k, ft in features.items() if k not in cfg.output_features}
    cfg.init_checkpoint = str(EMA)
    cfg.bert_path = str(Path.home() / "models/bert-base-uncased")
    cfg.dinov3_path = str(Path.home() / "models/dinov3-vitb16")

    policy = TurboVLAPolicy(cfg)
    policy.eval()
    policy.config.init_checkpoint = None

    preprocessor, postprocessor = make_turbovla_pre_post_processors(cfg, dataset_stats=ds.meta.stats)

    OUT.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(OUT)
    preprocessor.save_pretrained(OUT)
    postprocessor.save_pretrained(OUT)
    print(f"[ok] wrote {OUT}")
    print("input_features:", sorted(cfg.input_features))
    print("image shapes:", {k: v.shape for k, v in cfg.input_features.items() if "images" in k})


if __name__ == "__main__":
    main()
