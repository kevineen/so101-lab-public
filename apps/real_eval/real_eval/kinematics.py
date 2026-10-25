"""URDF（sim2rl assets）を MuJoCo で読み、関節限界と FK を提供する。

モデル構築は sim2rl の MuJoCo バックエンドと同じ経路
（``mujoco.MjSpec.from_file(urdf)`` + EE サイト付与）なので、FK の幾何と
アクション正規化の限界が学習時と一致する。物理（actuator・接触）は使わない —
ここは純粋に運動学の参照実装。

EE は URDF の ``gripper_frame_joint``（``gripper_link`` → ダミーリンク
``gripper_frame_link``、固定オフセット）で定義される仮想フレーム。
sim2rl と同じく **親リンク（gripper_link）に EE オフセットのサイトを付ける**
（MuJoCo の URDF 取り込みは質量 0 のリンクを統合するため）。
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import mujoco
import numpy as np

from .config import JOINT_ORDER, JointMap

#: FK 用に付与する EE サイト名（sim2rl backends/mujoco.py の ``_add_ee_site`` と同じ）。
EE_SITE_NAME = "ee_site"
#: URDF 上の EE ダミーリンク（sim2rl robot 設定の ``ee_link``）。
EE_LINK = "gripper_frame_link"


def _ee_origin(urdf_path: Path) -> tuple[str, tuple[float, float, float]]:
    """EE を定義する fixed ジョイントから (親リンク, オフセット) を返す。

    EE 位置の計算には平行移動だけで足りる（回転はサイト位置に影響しない）。
    """
    root = ElementTree.parse(urdf_path).getroot()
    for joint in root.findall("joint"):
        child = joint.find("child")
        if child is not None and child.get("link") == EE_LINK:
            parent = joint.find("parent")
            if parent is None:
                raise ValueError(f"joint {joint.get('name')!r} has no parent link")
            origin = joint.find("origin")
            xyz = (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()
            return parent.get("link"), tuple(float(v) for v in xyz)  # type: ignore[return-value]
    raise ValueError(f"no fixed joint attaches {EE_LINK} in {urdf_path}")


class Kinematics:
    """6 関節の FK・限界・[-1,1] 正規化の写像。

    ``lower`` / ``upper`` は URDF の ``<limit>``（回転関節は rad、gripper は m）。
    ``denormalize`` は sim2rl ``backend.denormalize_action`` と同じ式
    ``mid + action * half_span``。``joint_map`` で LeRobot のキャリブ値
    （度 / gripper %）をこの URDF 値へ写す。
    """

    def __init__(self, urdf_path: Path, joint_map: dict[str, JointMap]) -> None:
        parent_link, offset = _ee_origin(urdf_path)
        spec = mujoco.MjSpec.from_file(str(urdf_path))
        spec.body(parent_link).add_site(name=EE_SITE_NAME, pos=list(offset))
        self.model = spec.compile()
        self.data = mujoco.MjData(self.model)

        self._qposadr: dict[str, int] = {}
        limits: list[tuple[float, float]] = []
        for joint in JOINT_ORDER:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint)
            if jid < 0:
                raise ValueError(f"joint {joint!r} not found in {urdf_path}")
            self._qposadr[joint] = int(self.model.jnt_qposadr[jid])
            limits.append((float(self.model.jnt_range[jid][0]), float(self.model.jnt_range[jid][1])))
        self.lower = np.array([lo for lo, _ in limits])
        self.upper = np.array([hi for _, hi in limits])
        self.mid = 0.5 * (self.lower + self.upper)
        self.half_span = 0.5 * (self.upper - self.lower)

        self._site_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, EE_SITE_NAME)
        if self._site_id < 0:
            raise ValueError("ee site was not added correctly")

        # 既定写像: 回転関節は度→rad、gripper は LeRobot 0..100（%）→ URDF 全範囲。
        # 実機ごとの零点ずれは --calibrate-offsets で上書きする
        self.joint_map = dict(joint_map)
        for joint in JOINT_ORDER[:-1]:
            self.joint_map.setdefault(joint, JointMap())
        if "gripper" not in self.joint_map:
            span = float(self.upper[-1] - self.lower[-1])
            self.joint_map["gripper"] = JointMap(scale=span / 100.0, offset=float(self.lower[-1]))

    # --- 座標変換（LeRobot ⇄ URDF）---------------------------------------------

    def to_urdf_qpos(self, lerobot_values: np.ndarray) -> np.ndarray:
        return np.array(
            [
                self.joint_map[j].to_urdf(float(v))
                for j, v in zip(JOINT_ORDER, lerobot_values, strict=True)
            ]
        )

    def to_lerobot_action(self, urdf_target: np.ndarray) -> np.ndarray:
        return np.array(
            [
                self.joint_map[j].to_lerobot(float(v))
                for j, v in zip(JOINT_ORDER, urdf_target, strict=True)
            ]
        )

    # --- 契約（sim2rl backend と同一の式）--------------------------------------

    def denormalize(self, action: np.ndarray) -> np.ndarray:
        """[-1,1]^6 を URDF 関節目標へ（クリップ付き）。"""
        action = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        return self.mid + action * self.half_span

    def normalize(self, qpos: np.ndarray) -> np.ndarray:
        return np.clip((np.asarray(qpos, dtype=np.float64) - self.mid) / self.half_span, -1.0, 1.0)

    # --- FK -------------------------------------------------------------------

    def ee_pos(self, qpos_urdf: np.ndarray) -> np.ndarray:
        """URDF 関節値（rad/m）→ EE 位置 [m]（base_link 系）。"""
        self.data.qpos[:] = 0.0
        for joint, value in zip(JOINT_ORDER, qpos_urdf, strict=True):
            self.data.qpos[self._qposadr[joint]] = value
        mujoco.mj_forward(self.model, self.data)
        return self.data.site(self._site_id).xpos.copy()
