"""Unit tests for relative EE tip tracking (mocked FK/IK, no placo)."""

from __future__ import annotations

import unittest

import numpy as np

from bridges.isaacteleop_to_so101.contract import SCHEMA_VERSION, EePose, TeleopCommand
from bridges.isaacteleop_to_so101.ik import (
    RelativeEeIk,
    map_quest_delta,
    normalize_axis_map,
    parse_axis_token,
)
from bridges.isaacteleop_to_so101.safety import parse_soft_limits


class FakeKinematics:
    """Identity FK at origin tip; IK returns seed shifted by tip xyz*100 deg."""

    def __init__(self) -> None:
        self.last_t_des: np.ndarray | None = None

    def forward_kinematics(self, joint_pos_deg: np.ndarray) -> np.ndarray:
        t = np.eye(4, dtype=float)
        # Tip near [0.2, 0, 0.15] regardless of joints (enough for delta tests).
        t[:3, 3] = (0.20, 0.0, 0.15)
        return t

    def inverse_kinematics(
        self,
        current_joint_pos: np.ndarray,
        desired_ee_pose: np.ndarray,
        position_weight: float = 1.0,
        orientation_weight: float = 0.01,
    ) -> np.ndarray:
        self.last_t_des = np.array(desired_ee_pose, dtype=float, copy=True)
        q = np.asarray(current_joint_pos, dtype=float).copy()
        # Encode tip x into shoulder_pan for assertion convenience.
        q[0] = float(desired_ee_pose[0, 3]) * 100.0
        q[1] = float(desired_ee_pose[1, 3]) * 100.0
        q[2] = float(desired_ee_pose[2, 3]) * 100.0
        return q


def _cmd(arm: str, pos: tuple[float, float, float], *, valid: bool = True) -> TeleopCommand:
    return TeleopCommand(
        schema_version=SCHEMA_VERSION,
        timestamp_ns=1,
        frame_id=f"teleop_{arm}",
        arm=arm,
        ee_pose=EePose(position_m=pos, quat_xyzw=(0.0, 0.0, 0.0, 1.0)),
        gripper=0.0,
        valid=valid,
        joints=None,
        mode="absolute",
    )


class AxisMapTests(unittest.TestCase):
    def test_parse_token(self) -> None:
        self.assertEqual(parse_axis_token("-y"), (-1.0, "y"))
        self.assertEqual(parse_axis_token("+x"), (1.0, "x"))

    def test_map_flip_y(self) -> None:
        am = normalize_axis_map({"x": "x", "y": "-y", "z": "z"})
        mx, my, mz = map_quest_delta(0.1, 0.2, 0.3, am)
        self.assertAlmostEqual(mx, 0.1)
        self.assertAlmostEqual(my, -0.2)
        self.assertAlmostEqual(mz, 0.3)


class RelativeEeIkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kin = FakeKinematics()
        self.ik = RelativeEeIk(
            urdf_path="/dev/null",
            pos_scale=1.0,
            axis_map={"x": "x", "y": "y", "z": "z"},
            kinematics=self.kin,
        )
        self.seed = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 0.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 0.0,
        }

    def test_first_frame_holds_seed(self) -> None:
        out = self.ik.solve("right", _cmd("right", (1.0, 2.0, 3.0)), self.seed)
        assert out is not None
        self.assertAlmostEqual(out["shoulder_pan"], 0.0)
        self.assertIsNone(self.kin.last_t_des)

    def test_delta_moves_tip(self) -> None:
        self.ik.solve("right", _cmd("right", (1.0, 2.0, 3.0)), self.seed)
        out = self.ik.solve("right", _cmd("right", (1.05, 2.0, 3.0)), self.seed)
        assert out is not None
        assert self.kin.last_t_des is not None
        # tip0=(0.20,0,0.15) + Δquest=(0.05,0,0)
        self.assertAlmostEqual(float(self.kin.last_t_des[0, 3]), 0.25, places=5)
        self.assertAlmostEqual(out["shoulder_pan"], 25.0, places=4)

    def test_axis_map_sign(self) -> None:
        ik = RelativeEeIk(
            urdf_path="/dev/null",
            pos_scale=1.0,
            axis_map={"x": "-x", "y": "y", "z": "z"},
            kinematics=self.kin,
        )
        ik.solve("left", _cmd("left", (0.0, 0.0, 0.0)), self.seed)
        ik.solve("left", _cmd("left", (0.1, 0.0, 0.0)), self.seed)
        assert self.kin.last_t_des is not None
        # tip0.x + (-0.1) = 0.10
        self.assertAlmostEqual(float(self.kin.last_t_des[0, 3]), 0.10, places=5)

    def test_pos_scale(self) -> None:
        ik = RelativeEeIk(
            urdf_path="/dev/null",
            pos_scale=0.5,
            axis_map={"x": "x", "y": "y", "z": "z"},
            kinematics=self.kin,
        )
        ik.solve("right", _cmd("right", (0.0, 0.0, 0.0)), self.seed)
        ik.solve("right", _cmd("right", (0.2, 0.0, 0.0)), self.seed)
        assert self.kin.last_t_des is not None
        self.assertAlmostEqual(float(self.kin.last_t_des[0, 3]), 0.30, places=5)  # 0.2 + 0.1

    def test_reset_reanchors(self) -> None:
        self.ik.solve("right", _cmd("right", (1.0, 0.0, 0.0)), self.seed)
        self.ik.solve("right", _cmd("right", (1.1, 0.0, 0.0)), self.seed)
        self.ik.reset("right")
        out = self.ik.solve("right", _cmd("right", (5.0, 0.0, 0.0)), self.seed)
        assert out is not None
        # New anchor frame → hold seed again
        self.assertAlmostEqual(out["shoulder_pan"], 0.0)
        self.ik.solve("right", _cmd("right", (5.0, 0.2, 0.0)), self.seed)
        assert self.kin.last_t_des is not None
        self.assertAlmostEqual(float(self.kin.last_t_des[1, 3]), 0.2, places=5)

    def test_soft_tip_outside_box_preserves_depth(self) -> None:
        """Hard tip clamp used to pin tip_des to the box edge → dead depth / down yank."""

        class OutsideTipKin(FakeKinematics):
            def forward_kinematics(self, joint_pos_deg: np.ndarray) -> np.ndarray:
                t = np.eye(4, dtype=float)
                t[:3, 3] = (-0.10, 0.0, 0.50)  # outside typical tip_bounds
                return t

        soft = parse_soft_limits(
            {
                "enabled": True,
                "tip_bounds_m": {"*": {"x": [0.02, 0.32], "z": [0.04, 0.38]}},
            }
        )
        kin = OutsideTipKin()
        ik = RelativeEeIk(
            urdf_path="/dev/null",
            pos_scale=1.0,
            axis_map={"x": "x", "y": "y", "z": "z"},
            soft_limits=soft,
            kinematics=kin,
        )
        ik.solve("right", _cmd("right", (0.0, 0.0, 0.0)), self.seed)
        # delta=0 must not yank tip toward the box
        ik.solve("right", _cmd("right", (0.0, 0.0, 0.0)), self.seed)
        assert kin.last_t_des is not None
        self.assertAlmostEqual(float(kin.last_t_des[0, 3]), -0.10, places=5)
        self.assertAlmostEqual(float(kin.last_t_des[2, 3]), 0.50, places=5)
        # depth Δx still moves tip
        ik.solve("right", _cmd("right", (0.05, 0.0, 0.0)), self.seed)
        assert kin.last_t_des is not None
        self.assertAlmostEqual(float(kin.last_t_des[0, 3]), -0.05, places=5)


if __name__ == "__main__":
    unittest.main()
