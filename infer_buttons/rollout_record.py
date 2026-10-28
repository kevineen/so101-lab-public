"""Record policy rollout episodes as a LeRobot v3.0 dataset during infer_buttons.

GR-BC (arXiv:2610.20504) post-training needs a data pool of demos plus policy
rollouts — successes, failures and (later) interventions — with genuine
outcome labels. The lab's phone-driven eval already produces the rollouts;
this module captures them as datasets without touching vendor code:

- ``robot.send_action`` is wrapped to tee the action dict actually commanded
  (the same value lerobot-record would save).
- Each control tick in the ``running`` phase adds one frame built from a fresh
  ``robot.get_observation()`` plus the latest commanded action, mirroring the
  lerobot-record feature pipeline (``build_dataset_frame``).
- The episode is saved only when the operator presses a result button; the
  outcome goes to a sidecar manifest (``grbc_manifest.jsonl``) next to the
  dataset. Unlabeled episodes are discarded — labels are never invented.
- Success/failure labels are applied later by ``apps/grbc/add_reward_labels.py``
  (``--sidecar``), which writes ``next.reward`` into a pool copy.

Opt-in: set ``SO101_INFER_RECORD=1``. Everything is a no-op otherwise, so the
default eval workflow is unchanged. Designed for the Pi (robot_client host);
offload the dataset to the GPU PC afterwards like record_buttons data.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("infer_buttons")

ENV_ENABLE = "SO101_INFER_RECORD"
ENV_REPO = "SO101_INFER_RECORD_REPO"
ENV_ROOT = "SO101_INFER_RECORD_ROOT"


class NullRolloutRecorder:
    """No-op stand-in so call sites never check for None."""

    def begin_episode(self, meta: dict | None = None) -> None: ...
    def tick(self) -> None: ...
    def label_episode(self, *, success: bool, kind: str | None = None) -> None: ...
    def discard_episode(self) -> None: ...
    def undo_last_label(self) -> None: ...
    def close(self) -> None: ...


class RolloutRecorder:
    """Records one dataset per session; one episode per phone-scored trial."""

    def __init__(self, robot, task: str, fps: int, repo_id: str, root: Path, model: str):
        from lerobot.datasets import (
            LeRobotDataset,
            aggregate_pipeline_dataset_features,
            create_initial_features,
        )
        from lerobot.processor.factory import make_default_processors
        from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts

        self._robot = robot
        self._task = task
        self._model = model
        self._build_dataset_frame = build_dataset_frame
        self._action_lock = threading.Lock()
        self._last_action: dict | None = None
        self._active = False
        self._episode_meta: dict = {}
        self._started_at = 0.0

        # Mirror lerobot-record's feature pipeline: hw feature types through the
        # default identity processors into dataset feature specs.
        _, robot_action_processor, robot_observation_processor = make_default_processors()
        features = combine_feature_dicts(
            aggregate_pipeline_dataset_features(
                pipeline=robot_action_processor,
                initial_features=create_initial_features(action=robot.action_features),
                use_videos=True,
            ),
            aggregate_pipeline_dataset_features(
                pipeline=robot_observation_processor,
                initial_features=create_initial_features(observation=robot.observation_features),
                use_videos=True,
            ),
        )
        self._dataset = LeRobotDataset.create(
            repo_id=repo_id,
            fps=fps,
            features=features,
            root=root,
            robot_type=getattr(robot, "name", None),
            use_videos=True,
        )
        self._manifest_path = self._dataset.root / "grbc_manifest.jsonl"

        original_send_action = robot.send_action

        def send_action_tee(action_dict):
            with self._action_lock:
                self._last_action = dict(action_dict)
            return original_send_action(action_dict)

        robot.send_action = send_action_tee
        print(
            f"ロールアウト録画 ON: {self._dataset.root}（結果ボタンでエピソード確定）",
            flush=True,
        )

    @classmethod
    def create_if_enabled(cls, robot, task: str, fps: int, model: str):
        if os.environ.get(ENV_ENABLE, "") != "1":
            return NullRolloutRecorder()
        repo_id = os.environ.get(
            ENV_REPO, f"rollout_{model or 'policy'}_{time.strftime('%Y%m%d_%H%M%S')}"
        ).replace("/", "_")
        root = Path(os.environ.get(ENV_ROOT, "")) if os.environ.get(ENV_ROOT) else None
        return cls(robot, task, fps, repo_id, root, model)

    def begin_episode(self, meta: dict | None = None) -> None:
        self._active = True
        self._episode_meta = dict(meta or {})
        self._started_at = time.time()

    def tick(self) -> None:
        if not self._active:
            return
        try:
            with self._action_lock:
                action = self._last_action
            if action is None:
                return  # No commanded action yet this session; skip pre-action frames.
            obs = self._robot.get_observation()
            frame = {
                **self._build_dataset_frame(self._dataset.features, obs, prefix="observation"),
                **self._build_dataset_frame(self._dataset.features, action, prefix="action"),
                "task": self._task,
            }
            self._dataset.add_frame(frame)
        except Exception as exc:  # Recording must never kill the control loop.
            logger.warning("rollout record tick failed: %s", exc)

    def label_episode(self, *, success: bool, kind: str | None = None) -> None:
        if not self._active:
            return
        self._active = False
        try:
            self._dataset.save_episode()
            record = {
                "episode_index": self._dataset.meta.total_episodes - 1,
                "success": bool(success),
                "failure_kind": kind,
                "model": self._model,
                "task": self._task,
                "duration_s": round(time.time() - self._started_at, 2),
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                **self._episode_meta,
            }
            with self._manifest_path.open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            print(f"ロールアウト録画: ep{record['episode_index']} 保存 (success={success})", flush=True)
        except Exception as exc:
            logger.exception("rollout record save failed")
            print(f"ロールアウト録画の保存に失敗: {exc}", flush=True)

    def discard_episode(self) -> None:
        if not self._active:
            return
        self._active = False
        try:
            self._dataset.clear_episode_buffer()
            print("ロールアウト録画: 未採点エピソードを破棄", flush=True)
        except Exception as exc:
            logger.warning("rollout record discard failed: %s", exc)

    def undo_last_label(self) -> None:
        """Void the most recent manifest line (paired with the phone's undo)."""
        if not self._manifest_path.exists():
            return
        try:
            lines = self._manifest_path.read_text().splitlines()
            for pos in range(len(lines) - 1, -1, -1):
                record = json.loads(lines[pos])
                if not record.get("void"):
                    record["void"] = True
                    lines[pos] = json.dumps(record)
                    self._manifest_path.write_text("\n".join(lines) + "\n")
                    print(f"ロールアウト録画: ep{record['episode_index']} のラベルを無効化", flush=True)
                    return
        except Exception as exc:
            logger.warning("rollout record undo failed: %s", exc)

    def close(self) -> None:
        self.discard_episode()
        try:
            # Parquet footers are only written on finalize; until then the dataset
            # directory is mid-session state and unreadable.
            self._dataset.finalize()
            print(f"ロールアウト録画: データセット確定 ({self._dataset.root})", flush=True)
        except Exception as exc:
            logger.exception("rollout record finalize failed")
