"""Phase C mapping tests (no Quest / isaaccapture)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridges.isaacteleop_to_so101.contract import parse_command
from bridges.isaacteleop_to_so101.from_retarget import (
    command_from_retarget,
    isaac_gripper_to_contract,
    pose7_is_tracked,
    summarize_jsonl,
)


class FromRetargetTests(unittest.TestCase):
    def test_gripper_polarity(self) -> None:
        # Isaac: -1 closed, +1 open → contract 1 closed, 0 open
        self.assertAlmostEqual(isaac_gripper_to_contract(-1.0), 1.0)
        self.assertAlmostEqual(isaac_gripper_to_contract(1.0), 0.0)
        self.assertAlmostEqual(isaac_gripper_to_contract(0.0), 0.5)

    def test_origin_not_tracked(self) -> None:
        self.assertFalse(pose7_is_tracked([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))
        self.assertTrue(pose7_is_tracked([0.14, 1.08, -0.26, 0.5, -0.4, 0.0, 0.7]))

    def test_command_roundtrip(self) -> None:
        pose = [0.14, 1.088, -0.264, 0.54, -0.48, -0.08, 0.69]
        cmd = command_from_retarget(
            arm="right",
            pose7=pose,
            isaac_gripper=-1.0,
            timestamp_ns=123,
        )
        self.assertEqual(cmd.frame_id, "teleop_right")
        self.assertAlmostEqual(cmd.gripper, 1.0)
        self.assertTrue(cmd.valid)
        parsed = parse_command(cmd.to_json())
        self.assertEqual(parsed.arm, "right")
        assert parsed.ee_pose is not None
        self.assertAlmostEqual(parsed.ee_pose.position_m[1], 1.088)

    def test_untracked_valid_false(self) -> None:
        cmd = command_from_retarget(
            arm="right",
            pose7=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            isaac_gripper=1.0,
            timestamp_ns=1,
        )
        self.assertFalse(cmd.valid)
        # Still parseable
        parse_command(cmd.to_dict())

    def test_summarize_jsonl(self) -> None:
        lines = []
        for i, g_isaac in enumerate([1.0, -1.0, 1.0]):
            cmd = command_from_retarget(
                arm="right",
                pose7=[0.1, 1.0, -0.2, 0.0, 0.0, 0.0, 1.0],
                isaac_gripper=g_isaac,
                timestamp_ns=1_000_000_000 * i,
            )
            lines.append(cmd.to_json())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            stats = summarize_jsonl(str(path))
        self.assertEqual(stats["frames"], 3)
        self.assertEqual(stats["valid_frames"], 3)
        self.assertAlmostEqual(stats["approx_hz"], 1.0)
        self.assertAlmostEqual(stats["gripper_min"], 0.0)
        self.assertAlmostEqual(stats["gripper_max"], 1.0)


if __name__ == "__main__":
    unittest.main()
