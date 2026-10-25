"""Unit tests for Quest control mapping (no hardware)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridges.isaacteleop_to_so101.controls import (
    ClutchState,
    clutch_engaged,
    gripper_axis_to_contract,
    load_teleop_config,
    resolve_axis_name,
)


class ControlsTests(unittest.TestCase):
    def test_resolve_axes(self) -> None:
        self.assertEqual(resolve_axis_name("primary_click"), "PRIMARY_CLICK")
        self.assertEqual(resolve_axis_name("thumbstick_y"), "THUMBSTICK_Y")
        with self.assertRaises(ValueError):
            resolve_axis_name("not_a_button")

    def test_clutch_threshold(self) -> None:
        self.assertFalse(clutch_engaged(0.4, threshold=0.5))
        self.assertTrue(clutch_engaged(0.5, threshold=0.5))
        self.assertTrue(clutch_engaged(1.0, threshold=0.5))

    def test_gripper_trigger(self) -> None:
        self.assertAlmostEqual(gripper_axis_to_contract(0.0), 0.0)
        self.assertGreater(gripper_axis_to_contract(1.0), 0.9)
        self.assertAlmostEqual(gripper_axis_to_contract(0.02, deadzone=0.05), 0.0)

    def test_gripper_thumbstick(self) -> None:
        # bipolar [-1,1] → [0,1]
        self.assertAlmostEqual(
            gripper_axis_to_contract(-1.0, deadzone=0.0, bipolar=True), 0.0
        )
        self.assertAlmostEqual(
            gripper_axis_to_contract(1.0, deadzone=0.0, bipolar=True), 1.0
        )
        self.assertAlmostEqual(
            gripper_axis_to_contract(0.0, deadzone=0.0, bipolar=True), 0.5
        )

    def test_clutch_rising_edge(self) -> None:
        st = ClutchState()
        eng, rise = st.update("right", False)
        self.assertFalse(eng)
        self.assertFalse(rise)
        eng, rise = st.update("right", True)
        self.assertTrue(eng)
        self.assertTrue(rise)
        eng, rise = st.update("right", True)
        self.assertTrue(eng)
        self.assertFalse(rise)

    def test_scale_pose(self) -> None:
        st = ClutchState()
        pose = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0]
        out = st.scaled_pose("right", pose, pos_scale=0.5, rising=True)
        self.assertEqual(out[:3], [1.0, 2.0, 3.0])  # anchor frame
        moved = [1.2, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0]
        out2 = st.scaled_pose("right", moved, pos_scale=0.5, rising=False)
        self.assertAlmostEqual(out2[0], 1.1)  # 1 + 0.2*0.5

    def test_load_yaml(self) -> None:
        raw = """
arms: [right]
controls:
  clutch: secondary_click
  gripper: thumbstick_y
motion:
  mode: relative_ee
  pos_scale: 0.5
  axis_map:
    x: x
    y: -y
    z: z
arm_resolve:
  left: leader
  right: follower
cameras:
  enabled: false
  streams: []
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.yaml"
            path.write_text(raw, encoding="utf-8")
            cfg = load_teleop_config(path)
        self.assertEqual(cfg.arms, ["right"])
        self.assertEqual(cfg.clutch_axis, "secondary_click")
        self.assertEqual(cfg.gripper_axis, "thumbstick_y")
        self.assertEqual(cfg.motion_mode, "relative_ee")
        self.assertAlmostEqual(cfg.pos_scale, 0.5)
        self.assertEqual(cfg.axis_map["y"], "-y")
        self.assertEqual(cfg.arm_resolve.right, "follower")
        self.assertEqual(cfg.arm_resolve.left, "leader")
        self.assertFalse(cfg.cameras_enabled)


if __name__ == "__main__":
    unittest.main()
