"""kinematics: URDF 読み込み・限界・正規化写像・FK（sim2rl の so101 URDF が必要）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from real_eval.config import JOINT_ORDER, JointMap

URDF = Path.home() / "robot" / "sim2rl" / "assets" / "robots" / "so101" / "so101.urdf"

pytestmark = pytest.mark.skipif(
    not URDF.exists(), reason="sim2rl so101 URDF not available on this host"
)


@pytest.fixture()
def kin():
    from real_eval.kinematics import Kinematics

    return Kinematics(URDF, {})


def test_limits_and_denormalize_roundtrip(kin):
    assert kin.lower.shape == (6,) and np.all(kin.lower < kin.upper)
    action = np.array([0.5, -0.5, 1.0, -1.0, 0.0, 0.25])
    target = kin.denormalize(action)
    np.testing.assert_allclose(kin.normalize(target), action, atol=1e-12)
    # sim2rl と同一の中点式: 0 行動 = 可動域中央
    np.testing.assert_allclose(kin.denormalize(np.zeros(6)), kin.mid)


def test_fk_moves_with_joints_and_uses_urdf_frame(kin):
    q0 = np.zeros(6)
    ee0 = kin.ee_pos(q0)
    assert ee0.shape == (3,)
    # 全関節零でも EE は base から離れている（アームの形状分）
    assert np.linalg.norm(ee0) > 0.05
    q1 = q0.copy()
    q1[0] = 0.5  # shoulder_pan
    ee1 = kin.ee_pos(q1)
    assert not np.allclose(ee0, ee1)
    # shoulder_pan は base の z 軸周り: 高さは変わらない（mujoco解算の分解能内で）
    assert ee0[2] == pytest.approx(ee1[2], abs=1e-5)


def test_joint_map_affine_both_directions(kin):
    jmap = JointMap(scale=0.02, offset=0.1)
    kin.joint_map["shoulder_lift"] = jmap
    values = np.array([30.0] * 6)
    urdf = kin.to_urdf_qpos(values)
    assert urdf[1] == pytest.approx(0.02 * 30.0 + 0.1)
    back = kin.to_lerobot_action(urdf)
    np.testing.assert_allclose(back, values, atol=1e-12)


def test_gripper_default_maps_full_range(kin):
    span = kin.upper[-1] - kin.lower[-1]
    lo = kin.joint_map["gripper"].to_urdf(0.0)
    hi = kin.joint_map["gripper"].to_urdf(100.0)
    assert lo == pytest.approx(float(kin.lower[-1]))
    assert hi == pytest.approx(float(kin.upper[-1]))
    assert span > 0
