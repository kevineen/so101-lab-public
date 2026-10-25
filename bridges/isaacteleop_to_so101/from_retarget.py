"""Map Isaac Capture / Teleop retarget outputs → schema 1.0 TeleopCommand.

Phase C: no WebSocket, no Pi — pure conversion for JSONL recording and tests.

Gripper polarity (measured against GripperRetargeter):
- Isaac: ``-1.0`` = closed, ``+1.0`` = open
- Contract (docs/09): ``0.0`` = open, ``1.0`` = closed
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from .contract import SCHEMA_VERSION, EePose, TeleopCommand

# Isaac SE3 abs often parks at origin + identity when tracking is absent.
_ORIGIN_EPS_M = 1e-3


def isaac_gripper_to_contract(value: float) -> float:
    """Convert Isaac gripper command to contract ``[0, 1]`` (0=open, 1=closed)."""
    v = max(-1.0, min(1.0, float(value)))
    return (1.0 - v) / 2.0


def pose7_is_tracked(pose7: Sequence[float], *, eps_m: float = _ORIGIN_EPS_M) -> bool:
    """True when absolute EE pose is not the zero/identity parking state."""
    if len(pose7) < 3:
        return False
    x, y, z = float(pose7[0]), float(pose7[1]), float(pose7[2])
    return (x * x + y * y + z * z) ** 0.5 > eps_m


def ee_pose_from_se3(pose7: Sequence[float]) -> EePose:
    """Build ``EePose`` from SE3 abs output ``[x,y,z,qx,qy,qz,qw]``."""
    if len(pose7) < 7:
        raise ValueError(f"ee pose needs 7 floats, got {len(pose7)}")
    return EePose(
        position_m=(float(pose7[0]), float(pose7[1]), float(pose7[2])),
        quat_xyzw=(float(pose7[3]), float(pose7[4]), float(pose7[5]), float(pose7[6])),
    )


def command_from_retarget(
    *,
    arm: str,
    pose7: Sequence[float],
    isaac_gripper: float | None = None,
    contract_gripper: float | None = None,
    timestamp_ns: int | None = None,
    frame_id: str | None = None,
    force_valid: bool | None = None,
) -> TeleopCommand:
    """One logical-arm command from SE3 abs pose + gripper.

    Pass either ``isaac_gripper`` (Isaac -1/+1) or ``contract_gripper`` ([0, 1]).
    """
    if arm not in {"left", "right", "single"}:
        raise ValueError(f"arm must be left|right|single, got {arm!r}")
    if contract_gripper is None and isaac_gripper is None:
        raise ValueError("need isaac_gripper or contract_gripper")
    if contract_gripper is not None:
        grip = max(0.0, min(1.0, float(contract_gripper)))
    else:
        grip = isaac_gripper_to_contract(float(isaac_gripper))
    tracked = pose7_is_tracked(pose7)
    valid = tracked if force_valid is None else bool(force_valid)
    return TeleopCommand(
        schema_version=SCHEMA_VERSION,
        timestamp_ns=int(time.time_ns() if timestamp_ns is None else timestamp_ns),
        frame_id=frame_id or f"teleop_{arm}",
        arm=arm,
        ee_pose=ee_pose_from_se3(pose7),
        gripper=grip,
        valid=valid,
        joints=None,
        mode="absolute",
    )


def summarize_jsonl(path: str) -> dict[str, Any]:
    """Load a recorded JSONL and return simple Phase-C stats (hz, gripper range)."""
    import json
    from pathlib import Path

    stamps: list[int] = []
    grips: list[float] = []
    valid_n = 0
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        n += 1
        stamps.append(int(obj["timestamp_ns"]))
        grips.append(float(obj["gripper"]))
        if obj.get("valid"):
            valid_n += 1
    hz = 0.0
    if len(stamps) >= 2:
        dt_s = (stamps[-1] - stamps[0]) / 1e9
        if dt_s > 0:
            hz = (len(stamps) - 1) / dt_s
    return {
        "frames": n,
        "valid_frames": valid_n,
        "approx_hz": round(hz, 2),
        "gripper_min": min(grips) if grips else None,
        "gripper_max": max(grips) if grips else None,
        "timestamp_clock": "wall time.time_ns()",
        "frame_id_note": "teleop_<arm>; Quest OpenXR / CloudXR device frame (not SO-101 base yet)",
    }
