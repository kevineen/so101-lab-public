"""so101_common.joints の正本テーブル検証。"""

from __future__ import annotations

from so101_common.joints import (
    DEFAULT_JOINTS,
    JOINT_KEYS,
    JOINT_LIMITS_DEG,
    JOINT_ORDER,
    clamp_joints,
    default_joints,
)


def test_joint_order_matches_sim2rl_control_order():
    assert JOINT_ORDER == (
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    )
    assert JOINT_KEYS == JOINT_ORDER


def test_limits_cover_all_joints():
    assert set(JOINT_LIMITS_DEG) == set(JOINT_ORDER)
    lo, hi = JOINT_LIMITS_DEG["gripper"]
    assert (lo, hi) == (0.0, 100.0)


def test_clamp_joints_clamps_and_ignores_unknown():
    out = clamp_joints(
        {
            "shoulder_pan.pos": 250.0,  # .pos suffix stripped
            "wrist_roll": -999.0,
            "gripper": 50.0,
            "unknown_joint": 1.0,  # ignored
        }
    )
    assert out == {"shoulder_pan": 100.0, "wrist_roll": -180.0, "gripper": 50.0}


def test_default_joints_returns_copy():
    a = default_joints()
    a["gripper"] = 0.0
    assert DEFAULT_JOINTS["gripper"] == 50.0
