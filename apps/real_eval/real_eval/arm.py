"""実機 SO-101 follower への読み書きと、ウォッチドッグ付き安全な指令経路。

``ArmIO`` はテストが差し替え可能な最小界面。``LerobotArm`` が本番実装で
lerobot フォーク（``~/robot/lerobot``）の ``SO101Follower`` を遅延 import する（lerobot が無い
ホストでも単体テストが動くように）。

安全策（docs/18_real_eval.md の運用正本と対応）:

- ``max_relative_target``: 1 周期あたりの指令変化を度で制限
  （lerobot 側の同名機構と同じ考え方。本ツールでも独自にクランプする）
- 関節リミットガード: URDF 限界の内側にマージンを設けた ``soft_limits``
- ウォッチドッグ: 指令が ``cmd_timeout_s`` 以上途切れたら **その瞬間の測定姿勢に
  目標を固定**（sim2rl reproducibility.md の実機検証済み契約 — 毎ティック現在値を
 追いかけると剛性ゼロで沈降する）
"""

from __future__ import annotations

import time
from typing import Protocol

import numpy as np

from .config import JOINT_ORDER


class ArmIO(Protocol):
    """実機（またはモック）との最小契約。単位は LeRobot キャリブ系（度 / %）。"""

    def read_joints(self) -> np.ndarray:  # (6,) Lerobot 値
        ...

    def write_joints(self, target: np.ndarray) -> None:  # (6,) Lerobot 値
        ...

    def close(self) -> None: ...


class LerobotArm:
    """``SO101Follower`` アダプタ。カメラは使わない（RL 観測は固有姿勢のみ）。"""

    def __init__(self, port: str, robot_id: str, max_relative_target: float) -> None:
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

        config = SO101FollowerConfig(
            port=port,
            id=robot_id,
            use_degrees=True,
            max_relative_target=max_relative_target,
            disable_torque_on_disconnect=False,  # docs/17 と同じ: nest へ戻るまでトルク維持
        )
        self._robot = SO101Follower(config)
        self._robot.connect(calibrate=False)
        if not self._robot.calibration:
            self._robot.bus.disconnect()
            raise RuntimeError(
                f"No calibration for robot id {robot_id!r}. Run lerobot-calibrate first "
                "(docs/04_calibration.md)."
            )

    def read_joints(self) -> np.ndarray:
        obs = self._robot.get_observation()
        return np.array([float(obs[f"{joint}.pos"]) for joint in JOINT_ORDER])

    def write_joints(self, target: np.ndarray) -> None:
        self._robot.send_action({joint: float(v) for joint, v in zip(JOINT_ORDER, target, strict=True)})

    def close(self) -> None:
        if getattr(self._robot.bus, "is_connected", False):
            self._robot.bus.disconnect()


class SafetyGuards:
    """指令のクランプとホールド。単位は LeRobot 値（度 / %）。"""

    def __init__(
        self,
        lerobot_lower: np.ndarray,
        lerobot_upper: np.ndarray,
        *,
        max_step: float,
        margin: float = 2.0,
    ) -> None:
        self.lower = lerobot_lower + margin
        self.upper = lerobot_upper - margin
        self.max_step = max_step

    def clamp_target(self, current: np.ndarray, target: np.ndarray) -> np.ndarray:
        """現在値から 1 周期で動ける範囲＋ソフトリミット内へ丸める。"""
        target = np.clip(target, self.lower, self.upper)
        return np.clip(target, current - self.max_step, current + self.max_step)


class Watchdog:
    """指令途断の検出とホールド姿勢の固定。

    「最後に指令を書けた時刻」を基準に測る — 推論（onnxrun）が
    ``timeout_s`` 以上ブロックして次の書き込みが間に合わない状態を途断とみなす。
    いったん発火したホールドは **エピソード内で粘着**（勝手に再開しない。
    再開は ``reset()``＝次エピソード）。
    """

    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._last_write = time.monotonic()
        self._hold: np.ndarray | None = None

    def reset(self) -> None:
        self._last_write = time.monotonic()
        self._hold = None

    def note_write(self) -> None:
        self._last_write = time.monotonic()

    @property
    def stale(self) -> bool:
        return self._hold is not None or (time.monotonic() - self._last_write) > self.timeout_s

    def hold_target(self, measured: np.ndarray) -> np.ndarray:
        """途断時の目標: **発火した瞬間** の測定姿勢に固定し続ける。"""
        if self._hold is None:
            self._hold = measured.copy()
        return self._hold.copy()
