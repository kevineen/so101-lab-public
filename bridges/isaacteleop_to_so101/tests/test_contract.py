"""Unit tests for schema 1.0 + dual-arm mapping (no hardware)."""

from __future__ import annotations

import json
import unittest

from bridges.isaacteleop_to_so101.contract import (
    DEFAULT_ARM_RESOLVE,
    ContractError,
    parse_command,
)
from bridges.isaacteleop_to_so101.ik import ApproxIk
from bridges.isaacteleop_to_so101.sender import make_joint_cmd


class ContractTests(unittest.TestCase):
    def test_parse_ee_pose(self) -> None:
        raw = {
            "schema_version": "1.0",
            "timestamp_ns": 1,
            "frame_id": "teleop_right",
            "arm": "right",
            "ee_pose": {
                "position_m": [0.25, 0.02, 0.18],
                "quat_xyzw": [0.0, 0.0, 0.0, 1.0],
            },
            "gripper": 0.0,
            "valid": True,
        }
        cmd = parse_command(raw)
        self.assertEqual(cmd.arm, "right")
        assert cmd.ee_pose is not None
        self.assertAlmostEqual(cmd.ee_pose.position_m[0], 0.25)

    def test_parse_joints_bimanual(self) -> None:
        left = make_joint_cmd(
            "left",
            {
                "shoulder_pan": 10.0,
                "shoulder_lift": 0.0,
                "elbow_flex": 0.0,
                "wrist_flex": 0.0,
                "wrist_roll": 0.0,
                "gripper": 40.0,
            },
        )
        right = make_joint_cmd(
            "right",
            {
                "shoulder_pan": -10.0,
                "shoulder_lift": 0.0,
                "elbow_flex": 0.0,
                "wrist_flex": 0.0,
                "wrist_roll": 0.0,
                "gripper": 40.0,
            },
        )
        self.assertEqual(DEFAULT_ARM_RESOLVE.physical(left.arm), "follower")
        self.assertEqual(DEFAULT_ARM_RESOLVE.physical(right.arm), "leader")
        roundtrip = parse_command(left.to_json())
        self.assertEqual(roundtrip.joints["shoulder_pan"], 10.0)
        self.assertAlmostEqual(roundtrip.gripper, 0.4)

    def test_reject_bad_schema(self) -> None:
        with self.assertRaises(ContractError):
            parse_command({"schema_version": "9.9", "timestamp_ns": 1, "frame_id": "x", "arm": "left"})

    def test_reject_valid_without_pose_or_joints(self) -> None:
        with self.assertRaises(ContractError):
            parse_command(
                {
                    "schema_version": "1.0",
                    "timestamp_ns": 1,
                    "frame_id": "x",
                    "arm": "single",
                    "gripper": 0.0,
                    "valid": True,
                }
            )

    def test_approx_ik_latches_then_moves(self) -> None:
        ik = ApproxIk(max_step_deg=5.0)
        seed = {k: 0.0 for k in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")}
        cmd0 = parse_command(
            {
                "schema_version": "1.0",
                "timestamp_ns": 1,
                "frame_id": "teleop_left",
                "arm": "left",
                "ee_pose": {"position_m": [0.25, 0.0, 0.15], "quat_xyzw": [0, 0, 0, 1]},
                "gripper": 0.2,
                "valid": True,
            }
        )
        q0 = ik.solve("follower", cmd0, seed)
        assert q0 is not None
        self.assertAlmostEqual(q0["gripper"], 20.0)

        cmd1 = parse_command(
            {
                "schema_version": "1.0",
                "timestamp_ns": 2,
                "frame_id": "teleop_left",
                "arm": "left",
                "ee_pose": {"position_m": [0.25, 0.02, 0.15], "quat_xyzw": [0, 0, 0, 1]},
                "gripper": 0.5,
                "valid": True,
            }
        )
        q1 = ik.solve("follower", cmd1, q0)
        assert q1 is not None
        self.assertNotEqual(q1["shoulder_pan"], q0["shoulder_pan"])
        self.assertAlmostEqual(q1["gripper"], 50.0)

    def test_docs_example_json(self) -> None:
        example = """
        {
          "schema_version": "1.0",
          "timestamp_ns": 1710000000123456789,
          "frame_id": "teleop_right",
          "arm": "single",
          "ee_pose": {
            "position_m": [0.25, 0.02, 0.18],
            "quat_xyzw": [0.0, 0.0, 0.0, 1.0]
          },
          "gripper": 0.0,
          "valid": true
        }
        """
        cmd = parse_command(json.loads(example))
        self.assertEqual(cmd.arm, "single")


if __name__ == "__main__":
    unittest.main()
