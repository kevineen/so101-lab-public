"""Schema 1.0 teleop command contract (docs/09_bridge_contract.md).

Optional transitional fields (still schema_version \"1.0\"):
- ``joints``: absolute joint targets in degrees (gripper 0–100). When present,
  the receiver prefers them over EE→IK so dual-arm can be verified before
  Quest / placo IK is tuned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"

from so101_common.joints import JOINT_KEYS, JOINT_LIMITS_DEG  # noqa: F401 (canonical joint tables)

ARM_VALUES = frozenset({"left", "right", "single"})


class ContractError(ValueError):
    """Raised when a payload fails schema validation."""


@dataclass(frozen=True)
class EePose:
    """End-effector pose in meters / unit quaternion (xyzw)."""

    position_m: tuple[float, float, float]
    quat_xyzw: tuple[float, float, float, float]


@dataclass(frozen=True)
class TeleopCommand:
    """One validated teleop frame for a single logical arm."""

    schema_version: str
    timestamp_ns: int
    frame_id: str
    arm: str
    ee_pose: EePose | None
    gripper: float
    valid: bool
    joints: dict[str, float] | None = None
    mode: str = "absolute"  # absolute | delta (reserved; receiver uses absolute)

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to the wire JSON shape."""
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "timestamp_ns": self.timestamp_ns,
            "frame_id": self.frame_id,
            "arm": self.arm,
            "gripper": self.gripper,
            "valid": self.valid,
        }
        if self.ee_pose is not None:
            out["ee_pose"] = {
                "position_m": list(self.ee_pose.position_m),
                "quat_xyzw": list(self.ee_pose.quat_xyzw),
            }
        if self.joints is not None:
            out["joints"] = dict(self.joints)
        if self.mode != "absolute":
            out["mode"] = self.mode
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


def _as_float_triple(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ContractError(f"{name} must be a length-3 array")
    return float(value[0]), float(value[1]), float(value[2])


def _as_float_quat(value: Any, name: str) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ContractError(f"{name} must be a length-4 array")
    return float(value[0]), float(value[1]), float(value[2]), float(value[3])


def clamp_joints(joints: Mapping[str, float]) -> dict[str, float]:
    """Clamp known joint keys; drop unknown names."""
    out: dict[str, float] = {}
    for key, value in joints.items():
        motor = str(key).removesuffix(".pos")
        if motor not in JOINT_LIMITS_DEG:
            continue
        lo, hi = JOINT_LIMITS_DEG[motor]
        out[motor] = max(lo, min(hi, float(value)))
    return out


def gripper_unit_to_percent(gripper: float) -> float:
    """Map contract gripper [0,1] → LeRobot degrees-mode gripper [0,100]."""
    return max(0.0, min(100.0, float(gripper) * 100.0))


def parse_command(payload: str | bytes | Mapping[str, Any]) -> TeleopCommand:
    """Parse and validate a teleop command from JSON text or a mapping."""
    if isinstance(payload, (str, bytes)):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSON: {exc}") from exc
    else:
        data = dict(payload)

    if not isinstance(data, dict):
        raise ContractError("payload must be a JSON object")

    version = str(data.get("schema_version", ""))
    if version != SCHEMA_VERSION:
        raise ContractError(f"unsupported schema_version {version!r}; want {SCHEMA_VERSION!r}")

    arm = str(data.get("arm", ""))
    if arm not in ARM_VALUES:
        raise ContractError(f"arm must be one of {sorted(ARM_VALUES)}; got {arm!r}")

    try:
        timestamp_ns = int(data["timestamp_ns"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("timestamp_ns must be an int") from exc

    frame_id = str(data.get("frame_id", ""))
    if not frame_id:
        raise ContractError("frame_id must be a non-empty string")

    valid = bool(data.get("valid", False))

    try:
        gripper = float(data.get("gripper", 0.0))
    except (TypeError, ValueError) as exc:
        raise ContractError("gripper must be a float") from exc
    if not 0.0 <= gripper <= 1.0:
        raise ContractError("gripper must be in [0.0, 1.0]")

    mode = str(data.get("mode", "absolute"))
    if mode not in {"absolute", "delta"}:
        raise ContractError("mode must be 'absolute' or 'delta'")

    ee_pose: EePose | None = None
    raw_ee = data.get("ee_pose")
    if raw_ee is not None:
        if not isinstance(raw_ee, dict):
            raise ContractError("ee_pose must be an object")
        ee_pose = EePose(
            position_m=_as_float_triple(raw_ee.get("position_m"), "ee_pose.position_m"),
            quat_xyzw=_as_float_quat(raw_ee.get("quat_xyzw"), "ee_pose.quat_xyzw"),
        )

    joints: dict[str, float] | None = None
    raw_joints = data.get("joints")
    if raw_joints is not None:
        if not isinstance(raw_joints, dict):
            raise ContractError("joints must be an object")
        joints = clamp_joints({str(k): float(v) for k, v in raw_joints.items()})
        if not joints:
            raise ContractError("joints contained no recognized motor keys")

    if valid and ee_pose is None and joints is None:
        raise ContractError("valid command needs ee_pose and/or joints")

    return TeleopCommand(
        schema_version=version,
        timestamp_ns=timestamp_ns,
        frame_id=frame_id,
        arm=arm,
        ee_pose=ee_pose,
        gripper=gripper,
        valid=valid,
        joints=joints,
        mode=mode,
    )


@dataclass
class ArmResolve:
    """Maps logical arm labels onto physical ports (follower / leader)."""

    left: str = "follower"
    right: str = "leader"
    single: str = "follower"

    def physical(self, logical: str) -> str:
        if logical == "left":
            return self.left
        if logical == "right":
            return self.right
        if logical == "single":
            return self.single
        raise ContractError(f"unknown logical arm {logical!r}")


# Default lab mapping: follower = left tip cam side, leader_drive = right.
DEFAULT_ARM_RESOLVE = ArmResolve()
