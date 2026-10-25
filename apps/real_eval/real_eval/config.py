"""real_eval の設定（YAML 1 ファイル + CLI 上書き）。

既定値はラボの片腕 IL 構成（docs/14・17）に合わせている。``joint_map`` は
LeRobot のキャリブ出力（度）を sim2rl の URDF ラジアンへ写すアフィン変換 —
零点・向きが実機ごとにずれるため ``--probe`` / ``--calibrate-offsets`` で
実測から求める（docs/18_real_eval.md）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from so101_common.joints import JOINT_ORDER  #: sim2rl の制御順（正本は so101_common）

DEG2RAD = 3.141592653589793 / 180.0


@dataclass
class JointMap:
    """LeRobot キャリブ値 → URDF ラジアンの 1 次写像: ``urdf = scale * lerobot + offset``。

    5 つの回転関節は ``scale=DEG2RAD``（向きが逆の機体は負にする）。
    gripper は LeRobot が 0..100（%）・URDF が m なので、全開閉を全範囲に
    写す既定を ``Kinematics`` が上限/下限から埋める。
    """

    scale: float = DEG2RAD
    offset: float = 0.0

    def to_urdf(self, lerobot_value: float) -> float:
        return self.scale * lerobot_value + self.offset

    def to_lerobot(self, urdf_value: float) -> float:
        return (urdf_value - self.offset) / self.scale


@dataclass
class RealEvalConfig:
    sim2rl_root: Path = Path.home() / "robot" / "sim2rl"
    run_dir: Path | None = None  # 必須: ~/robot/sim2rl/runs/<ts>_<name>
    checkpoint: str = "best"  # export_onnx --checkpoint と対応（説明用にCSVへ記録）
    policy_onnx: Path | None = None  # 既定: <run_dir>/policy.onnx

    # 実機。port は configs/lab.local.env の SO101_FOLLOWER_PORT と同じ値を
    # real_eval.local.yaml に書く（機体ごとに by-id パスが違うため既定値は空）
    port: str = ""
    robot_id: str = "my_follower"
    max_relative_target: float = 5.0  # deg/cycle。docs/17 推論クライアントと同じ

    # 評価プロトコル
    goal_m: tuple[float, float, float] | None = None  # 必須: URDF base_link 系での目標
    episodes: int = 10
    steps_per_episode: int = 150  # sim2rl reach と同じ 150 step
    rate_hz: float = 20.0  # >=20Hz（ウォッチドッグ契約の推奨レート）
    cmd_timeout_s: float = 0.5  # これを超えたら現在姿勢へ固定
    success_threshold_m: float = 0.03  # reach の既定（config.yaml 側が正）

    # 座標合わせ
    joint_map: dict[str, JointMap] = field(default_factory=dict)

    operator: str = field(
        default_factory=lambda: os.environ.get("SO101_OPERATOR", "") or "operator"
    )
    out_csv: Path | None = None  # 既定: <run_dir>/real_eval.csv
    notes: str = ""

    def resolve(self) -> RealEvalConfig:
        """パスの既定値を埋め、必須項目を検証する（破壊的に更新して返す）。"""
        if self.run_dir is None:
            raise ValueError("run_dir is required (~/robot/sim2rl/runs/<ts>_<name>)")
        if self.goal_m is None:
            raise ValueError("goal_m is required (URDF base_link frame, meters)")
        if len(self.goal_m) != 3:
            raise ValueError("goal_m must be [x, y, z] in meters")
        if self.policy_onnx is None:
            self.policy_onnx = self.run_dir / "policy.onnx"
        if not self.port:
            raise ValueError(
                "port is required — set SO101_FOLLOWER_PORT (configs/lab.local.env)"
                " or `port:` in real_eval.local.yaml"
            )
        if self.out_csv is None:
            self.out_csv = self.run_dir / "real_eval.csv"
        if self.episodes < 1 or self.steps_per_episode < 1:
            raise ValueError("episodes and steps_per_episode must be >= 1")
        if self.rate_hz < 10.0:
            raise ValueError("rate_hz >= 10 required (watchdog contract recommends >= 20)")
        for joint in self.joint_map:
            if joint not in JOINT_ORDER:
                raise ValueError(f"unknown joint {joint!r} in joint_map (not in {JOINT_ORDER})")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> RealEvalConfig:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        joint_map_raw = raw.pop("joint_map", {}) or {}
        raw["joint_map"] = {
            name: JointMap(**vals) for name, vals in joint_map_raw.items()
        }
        for key in ("sim2rl_root", "run_dir", "policy_onnx", "out_csv"):
            if isinstance(raw.get(key), str):
                raw[key] = Path(raw[key]).expanduser()
        if isinstance(raw.get("goal_m"), list):
            raw["goal_m"] = tuple(float(v) for v in raw["goal_m"])
        cfg = cls(**raw)
        return cfg.resolve()
