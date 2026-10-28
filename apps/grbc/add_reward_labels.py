#!/usr/bin/env python
"""Add genuine `next.reward` / `next.done` labels to a LeRobot v3.0 dataset.

GR-BC (arXiv:2610.20504) requires frame-level sparse success rewards: positive
at the frame the task actually succeeded, zero elsewhere. Our recording
pipeline does not write reward columns, so this script copies a dataset and
labels the terminal frame of each success episode as reward 1.0.

Run from the so101-lab root (uses the lerobot fork via LEROBOT_DIR):

    PYTHONPATH=$LEROBOT_DIR/src uv run python apps/grbc/add_reward_labels.py \
        --src ~/robot/datasets/teamB_20261024_140811 \
        --dst ~/robot/datasets/teamB_grbc_v1 \
        --all-success

For rollout pools with mixed outcomes, pass a manifest instead:

    --manifest manifest.json
        {"0": true, "1": false, ...}          # episode_index -> success
        {"success": [0, 2], "failure": [1]}   # or explicit lists

or the sidecar written by infer_buttons rollout recording:

    --sidecar rollout_ds/grbc_manifest.jsonl

The source dataset is never modified. Gripper reminder: SO-101 recordings keep
gripper.pos in raw units (~0-52), so grbc-export needs
`--gripper-threshold` around the midpoint (see stats.json), not the 0.5 default.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


def load_success_manifest(path: Path, total_episodes: int) -> dict[int, bool]:
    data = json.loads(path.read_text())
    if "success" in data or "failure" in data:
        result = {ep: False for ep in range(total_episodes)}
        for ep in data.get("failure", []):
            result[int(ep)] = False
        for ep in data.get("success", []):
            result[int(ep)] = True
        return result
    return {int(ep): bool(success) for ep, success in data.items()}


def load_success_sidecar(path: Path, total_episodes: int) -> dict[int, bool]:
    """infer_buttons rollout recording sidecar; unlabeled/voided entries are fatal."""
    success: dict[int, bool] = {}
    voided: list[int] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        episode = int(record["episode_index"])
        if record.get("void"):
            voided.append(episode)
        else:
            success[episode] = bool(record["success"])
    if voided or len(success) != total_episodes:
        unlabeled = sorted(set(range(total_episodes)) - set(success) - set(voided))
        raise SystemExit(
            "dataset has episodes without a genuine outcome label "
            f"(voided: {voided}, unlabeled: {unlabeled}). Drop them first, e.g. "
            "`uv run python -m lerobot.scripts.lerobot_edit_dataset "
            "--operation.type delete_episodes --operation.episode_indices \"[...]\"`, "
            "then rerun with the sidecar."
        )
    return success


def episode_lengths_from_data(root: Path) -> dict[int, int]:
    lengths = {}
    for path in sorted((root / "data").glob("*/*.parquet")):
        table = pd.read_parquet(path, columns=["episode_index", "frame_index"])
        # v3.0 stores [1]-shaped features as per-row lists; reduce to plain scalars.
        episode = table["episode_index"].map(_scalar)
        frame = table["frame_index"].map(_scalar)
        for ep in sorted(episode.unique()):
            lengths[int(ep)] = max(lengths.get(int(ep), 0), int(frame[episode == ep].max()) + 1)
    return lengths


def _scalar(value) -> int:
    return int(value[0] if isinstance(value, (list, np.ndarray)) else value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, required=True, help="source LeRobot v3.0 dataset")
    parser.add_argument("--dst", type=Path, required=True, help="destination dataset (created fresh)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all-success", action="store_true", help="every episode succeeded (demo pool)")
    group.add_argument(
        "--manifest",
        type=Path,
        help="JSON mapping episode_index to success (see module docstring)",
    )
    group.add_argument(
        "--sidecar",
        type=Path,
        help="grbc_manifest.jsonl written by infer_buttons rollout recording",
    )
    args = parser.parse_args()

    from lerobot.datasets import LeRobotDataset
    from lerobot.datasets.dataset_tools import modify_features

    if args.dst.exists():
        raise SystemExit(f"destination {args.dst} already exists; choose a fresh directory")
    dataset = LeRobotDataset(repo_id=args.src.resolve().name, root=args.src)
    for column in ("next.reward", "next.done"):
        if column in dataset.meta.features:
            raise SystemExit(f"{args.src} already has '{column}'; refusing to relabel")

    lengths = episode_lengths_from_data(args.src)
    if set(lengths) != {ep for ep in range(dataset.meta.total_episodes)}:
        raise SystemExit("episode indices in data files do not cover 0..total_episodes-1")

    if args.all_success:
        success = {ep: True for ep in lengths}
    elif args.sidecar is not None:
        success = load_success_sidecar(args.sidecar, dataset.meta.total_episodes)
    else:
        success = load_success_manifest(args.manifest, dataset.meta.total_episodes)
        missing = set(lengths) - set(success)
        if missing:
            raise SystemExit(f"manifest does not cover episodes: {sorted(missing)}")

    def reward_value(_row, episode_index, frame_index):
        last = lengths[_scalar(episode_index)] - 1
        return 1.0 if success[_scalar(episode_index)] and _scalar(frame_index) == last else 0.0

    def done_value(_row, episode_index, frame_index):
        return 1.0 if _scalar(frame_index) == lengths[_scalar(episode_index)] - 1 else 0.0

    modify_features(
        dataset,
        add_features={
            "next.reward": (reward_value, {"dtype": "float32", "shape": [1], "names": None}),
            "next.done": (done_value, {"dtype": "float32", "shape": [1], "names": None}),
        },
        output_dir=args.dst,
        repo_id=args.dst.resolve().name,
    )

    labeled = sum(success.values())
    positives = 0
    for path in sorted((args.dst / "data").glob("*/*.parquet")):
        reward = pd.read_parquet(path, columns=["next.reward"])["next.reward"].map(_scalar)
        positives += int((reward > 0).sum())
    if positives != labeled:
        shutil.rmtree(args.dst)
        raise SystemExit(f"verification failed ({positives} positive frames, expected {labeled}); removed {args.dst}")
    print(
        json.dumps(
            {
                "dataset": str(args.dst),
                "episodes": len(lengths),
                "success_episodes": labeled,
                "positive_reward_frames": positives,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
