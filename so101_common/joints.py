"""SO-101 関節の正本テーブル（順序・リミット・既定ホーム姿勢）。

同一の値がかつて web_remote/config.py・bridges/contract.py・apps/real_eval/config.py
に重複定義されていた。値を変える場合はここだけを変えること。

- 関節順序は sim2rl（``configs/robot/so101.yaml`` の joint_order）と同一。
- リミットは体幹 4 関節が ±100°、wrist_roll は連続回転のため 1 回転 ≈ ±180°、
  gripper は 0–100（%）。
"""

from __future__ import annotations

#: 制御順の関節名（sim2rl configs/robot/so101.yaml と同一）。
JOINT_ORDER: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)

#: JOINT_ORDER の別名（契約チェック等でキー集合として使う）。
JOINT_KEYS: tuple[str, ...] = JOINT_ORDER

#: 関節ごとのクランプ範囲（度数。gripper のみ 0–100）。
JOINT_LIMITS_DEG: dict[str, tuple[float, float]] = {
    "shoulder_pan": (-100.0, 100.0),
    "shoulder_lift": (-100.0, 100.0),
    "elbow_flex": (-100.0, 100.0),
    "wrist_flex": (-100.0, 100.0),
    "wrist_roll": (-180.0, 180.0),
    "gripper": (0.0, 100.0),
}

#: ホーム姿勢ファイルが無い場合のフォールバック（旧 Web Remote の H キーと同じ）。
DEFAULT_JOINTS: dict[str, float] = {
    "shoulder_pan": 0.0,
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 50.0,
}


def default_joints() -> dict[str, float]:
    """DEFAULT_JOINTS のコピーを返す。"""
    return dict(DEFAULT_JOINTS)


def clamp_joints(joints: dict[str, float]) -> dict[str, float]:
    """関節値を JOINT_LIMITS_DEG にクランプ。未知のキーは無視する。"""
    out: dict[str, float] = {}
    for key, value in joints.items():
        motor = key.removesuffix(".pos")
        if motor not in JOINT_LIMITS_DEG:
            continue
        lo, hi = JOINT_LIMITS_DEG[motor]
        out[motor] = max(lo, min(hi, float(value)))
    return out
