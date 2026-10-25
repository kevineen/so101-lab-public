"""Load dual SO-101 follower configs from so101_dual_cam.yaml (same ports as Web Remote)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .contract import ArmResolve, DEFAULT_ARM_RESOLVE

from so101_common.env import (
    apply_lab_overrides,
    lab_env_setup_hint,
    load_lab_env,
    missing_device_keys,
)
from so101_common.paths import DEFAULT_CONFIG_PATH  # noqa: F401 (canonical path resolution)


@dataclass
class PhysicalArm:
    """One position-controlled follower port."""

    name: str  # follower | leader
    port: str
    robot_id: str


@dataclass
class DualArmConfig:
    """Physical arms keyed by Web Remote names, plus logical→physical resolve."""

    arms: dict[str, PhysicalArm]
    resolve: ArmResolve = field(default_factory=lambda: ArmResolve())

    def physical_for(self, logical: str) -> PhysicalArm:
        key = self.resolve.physical(logical)
        if key not in self.arms:
            raise KeyError(
                f"logical arm {logical!r} maps to {key!r}, but only {sorted(self.arms)} are configured"
            )
        return self.arms[key]


def load_dual_arm_config(
    path: Path,
    *,
    follower_id: str = "my_follower",
    leader_id: str = "my_leader_drive",
    enable_leader: bool = True,
    resolve: ArmResolve | None = None,
) -> DualArmConfig:
    """Parse yaml robot.follower_arm / leader_arm ports."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")

    # 実機のシリアルは gitignored configs/lab.local.env から流し込む
    load_lab_env()
    apply_lab_overrides(data)
    missing = missing_device_keys(data, section="arms")
    if missing:
        raise ValueError(lab_env_setup_hint(missing))

    robot: dict[str, Any] = data.get("robot") or {}
    follower = robot.get("follower_arm") or {}
    leader = robot.get("leader_arm") or {}

    follower_port = follower.get("port") or robot.get("port")
    if not follower_port:
        raise ValueError(
            f"Missing robot.follower_arm.port in {path} — "
            "set SO101_FOLLOWER_PORT in configs/lab.local.env"
        )

    arms = {
        "follower": PhysicalArm(name="follower", port=str(follower_port), robot_id=follower_id),
    }

    leader_port = leader.get("port")
    # CLI --no-leader wins over yaml enabled: true
    leader_enabled = bool(enable_leader) and bool(leader.get("enabled", True))
    if leader_port and leader_enabled:
        arms["leader"] = PhysicalArm(name="leader", port=str(leader_port), robot_id=leader_id)

    return DualArmConfig(arms=arms, resolve=resolve or DEFAULT_ARM_RESOLVE)
