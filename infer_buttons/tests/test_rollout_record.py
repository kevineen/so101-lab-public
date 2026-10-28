"""RolloutRecorder unit tests: no robot hardware, real tiny LeRobot dataset."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from infer_buttons.rollout_record import NullRolloutRecorder, RolloutRecorder

try:
    import lerobot  # noqa: F401 — presence check only; tests need the fork on PYTHONPATH
except ImportError:
    lerobot = None


class FakeRobot:
    name = "so_follower"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    action_features = {"j1.pos": float, "gripper.pos": float}
    # 96x128 keeps the default SVT-AV1 encoder happy (its minimum frame size is 64x64).
    observation_features = {"j1.pos": float, "gripper.pos": float, "cam": (96, 128, 3)}

    def get_observation(self) -> dict:
        return {
            "j1.pos": 0.1,
            "gripper.pos": 0.5,
            "cam": np.zeros((96, 128, 3), dtype=np.uint8),
        }

    def send_action(self, action: dict) -> dict:
        self.sent.append(action)
        return action


@unittest.skipIf(lerobot is None, "lerobot fork not on PYTHONPATH")
class RolloutRecorderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_episode_saved_with_manifest(self):
        import pandas as pd

        robot = FakeRobot()
        recorder = RolloutRecorder(robot, "pick the sponge", 10, "unit_rollout", self.root / "unit_rollout", "m1")
        recorder.begin_episode({"trial": 1})
        robot.send_action({"j1.pos": 0.2, "gripper.pos": 1.0})  # tee captures this
        recorder.tick()
        recorder.tick()
        recorder.label_episode(success=True)
        recorder.close()

        dataset_dir = self.root / "unit_rollout"
        data = pd.concat(
            [pd.read_parquet(path) for path in sorted((dataset_dir / "data").rglob("*.parquet"))],
            ignore_index=True,
        )
        self.assertEqual(len(data), 2)
        for column in ("observation.state", "action", "timestamp"):
            self.assertIn(column, data)
        manifest = [json.loads(line) for line in (dataset_dir / "grbc_manifest.jsonl").read_text().splitlines()]
        self.assertEqual(manifest[-1]["episode_index"], 0)
        self.assertTrue(manifest[-1]["success"])
        self.assertEqual(manifest[-1]["trial"], 1)

    def test_no_action_no_frames_then_discard(self):
        robot = FakeRobot()
        recorder = RolloutRecorder(robot, "t", 10, "unit_discard", self.root / "unit_discard", "m1")
        recorder.begin_episode()
        recorder.tick()  # No action teed yet: must not add a frame.
        recorder.discard_episode()
        recorder.close()
        manifest_path = self.root / "unit_discard" / "grbc_manifest.jsonl"
        self.assertFalse(manifest_path.exists())

    def test_undo_voids_last_manifest_line(self):
        robot = FakeRobot()
        recorder = RolloutRecorder(robot, "t", 10, "unit_undo", self.root / "unit_undo", "m1")
        recorder.begin_episode()
        robot.send_action({"j1.pos": 0.0, "gripper.pos": 0.0})
        recorder.tick()
        recorder.label_episode(success=False, kind="no_grasp")
        recorder.close()
        recorder.undo_last_label()
        lines = (self.root / "unit_undo" / "grbc_manifest.jsonl").read_text().splitlines()
        record = json.loads(lines[-1])
        self.assertTrue(record["void"])
        self.assertEqual(record["failure_kind"], "no_grasp")

    def test_null_recorder_is_silent(self):
        recorder = NullRolloutRecorder()
        recorder.begin_episode()
        recorder.tick()
        recorder.label_episode(success=True)
        recorder.discard_episode()
        recorder.undo_last_label()
        recorder.close()

    def test_disabled_by_default(self):
        import os

        robot = FakeRobot()
        enabled = dict(os.environ)
        enabled.pop("SO101_INFER_RECORD", None)
        try:
            os.environ.clear()
            os.environ.update(enabled)
            recorder = RolloutRecorder.create_if_enabled(robot, "t", 30, "m")
            self.assertIsInstance(recorder, NullRolloutRecorder)
        finally:
            os.environ.clear()
            os.environ.update(enabled)


if __name__ == "__main__":
    unittest.main()
