"""Soft limit parsing and clamping (software, not motor EEPROM)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridges.isaacteleop_to_so101.controls import load_teleop_config
from bridges.isaacteleop_to_so101.safety import parse_soft_limits


class SoftLimitsTests(unittest.TestCase):
    def test_joint_clamp_inside_hw(self) -> None:
        lim = parse_soft_limits(
            {
                "enabled": True,
                "soft_joint_limits_deg": {
                    "*": {"shoulder_pan": [-30.0, 30.0]},
                },
            }
        )
        out = lim.clamp_joints("follower", {"shoulder_pan": 80.0, "gripper": 50.0})
        self.assertAlmostEqual(out["shoulder_pan"], 30.0)
        self.assertAlmostEqual(out["gripper"], 50.0)

    def test_per_arm_override(self) -> None:
        lim = parse_soft_limits(
            {
                "enabled": True,
                "soft_joint_limits_deg": {
                    "*": {"shoulder_pan": [-50.0, 50.0]},
                    "follower": {"shoulder_pan": [-20.0, 10.0]},
                },
            }
        )
        f = lim.clamp_joints("follower", {"shoulder_pan": 40.0})
        l = lim.clamp_joints("leader", {"shoulder_pan": 40.0})
        self.assertAlmostEqual(f["shoulder_pan"], 10.0)
        self.assertAlmostEqual(l["shoulder_pan"], 40.0)

    def test_tip_bounds(self) -> None:
        lim = parse_soft_limits(
            {
                "enabled": True,
                "tip_bounds_m": {"*": {"z": [0.05, 0.30], "x": [0.0, 0.25]}},
            }
        )
        x, y, z = lim.clamp_tip("leader", (0.5, 0.0, 0.01))
        self.assertAlmostEqual(x, 0.25)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(z, 0.05)

    def test_tip_anchored_holds_nest_outside_box(self) -> None:
        """Nest FK outside tip_bounds must not yank on delta=0 (depth/down bug)."""
        lim = parse_soft_limits(
            {
                "enabled": True,
                "tip_bounds_m": {"*": {"x": [0.02, 0.32], "z": [0.04, 0.38]}},
            }
        )
        tip0 = (-0.10, 0.0, 0.50)  # outside on x and z
        # Hold: no phantom motion toward the box.
        hx, hy, hz = lim.clamp_tip_anchored("follower", tip0, tip0)
        self.assertAlmostEqual(hx, -0.10)
        self.assertAlmostEqual(hz, 0.50)
        # Depth Δ still applies; further outside is blocked at tip0.
        dx, _, _ = lim.clamp_tip_anchored("follower", tip0, (-0.05, 0.0, 0.50))
        self.assertAlmostEqual(dx, -0.05)
        worse_x, _, _ = lim.clamp_tip_anchored("follower", tip0, (-0.20, 0.0, 0.50))
        self.assertAlmostEqual(worse_x, -0.10)
        # Toward box / down from high nest is allowed.
        _, _, dz = lim.clamp_tip_anchored("follower", tip0, (-0.10, 0.0, 0.45))
        self.assertAlmostEqual(dz, 0.45)

    def test_disabled(self) -> None:
        lim = parse_soft_limits(
            {
                "enabled": False,
                "soft_joint_limits_deg": {"*": {"shoulder_pan": [-1.0, 1.0]}},
            }
        )
        out = lim.clamp_joints("follower", {"shoulder_pan": 50.0})
        self.assertAlmostEqual(out["shoulder_pan"], 50.0)

    def test_yaml_load(self) -> None:
        raw = """
arms: [right]
safety:
  enabled: true
  soft_joint_limits_deg:
    follower:
      shoulder_pan: [-15, 15]
  tip_bounds_m:
    follower:
      z: [0.1, 0.2]
cameras:
  enabled: false
  streams: []
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.yaml"
            path.write_text(raw, encoding="utf-8")
            cfg = load_teleop_config(path)
        self.assertTrue(cfg.soft_limits.enabled)
        out = cfg.soft_limits.clamp_joints("follower", {"shoulder_pan": 90.0})
        self.assertAlmostEqual(out["shoulder_pan"], 15.0)


if __name__ == "__main__":
    unittest.main()
