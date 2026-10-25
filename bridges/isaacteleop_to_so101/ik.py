"""EE pose → joint targets.

Solvers:
- ``approx`` (default): latch first pose, map Δxyz into shoulder/elbow degrees.
  Good enough for low-speed dual-arm smoke tests without placo/URDF.
- ``placo``: absolute EE → joints via ``lerobot.model.RobotKinematics`` (optional).
  Falls back to approx with a warning on solve failure.
- ``relative``: clutch-relative tip tracking — FK tip0 at first valid frame, then
  ``tip_des = tip0 + axis_map(quest_delta) * pos_scale`` → IK. Requires URDF+placo
  at construction time (no silent approx fallback).
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .contract import JOINT_KEYS, EePose, TeleopCommand, clamp_joints, gripper_unit_to_percent
from .safety import SoftLimits

logger = logging.getLogger(__name__)

# Arm DoF used by URDF FK/IK (exclude gripper jaw).
ARM_JOINT_KEYS = tuple(k for k in JOINT_KEYS if k != "gripper")

DEFAULT_URDF_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "robots" / "so101" / "so101.urdf"
)

# Rough SO-101 workspace scales (m → deg). Tunable via ApproxIk constructor.
_DEFAULT_M_TO_DEG = {
    "x": 120.0,  # forward → shoulder_lift / elbow mix
    "y": 140.0,  # lateral → shoulder_pan
    "z": 160.0,  # up → shoulder_lift
}

_DEFAULT_AXIS_MAP = {"x": "x", "y": "y", "z": "z"}


class IkSolver(Protocol):
    """Convert a teleop command into absolute joint targets (degrees)."""

    def reset(self, arm: str) -> None: ...

    def solve(
        self,
        arm: str,
        cmd: TeleopCommand,
        seed_joints: Mapping[str, float],
    ) -> dict[str, float] | None: ...


def parse_axis_token(token: str) -> tuple[float, str]:
    """Parse ``x`` / ``-y`` / ``+z`` into ``(sign, axis)``."""
    s = str(token).strip().lower()
    if not s:
        raise ValueError("empty axis_map token")
    sign = 1.0
    if s[0] in "+-":
        sign = -1.0 if s[0] == "-" else 1.0
        s = s[1:].strip()
    if s not in {"x", "y", "z"}:
        raise ValueError(f"axis_map token must be ±x|y|z, got {token!r}")
    return sign, s


def normalize_axis_map(raw: Mapping[str, str] | None) -> dict[str, str]:
    """Validate and return robot_axis → quest token map."""
    src = dict(_DEFAULT_AXIS_MAP)
    if raw:
        for k in ("x", "y", "z"):
            if k in raw:
                parse_axis_token(str(raw[k]))  # validate early
                src[k] = str(raw[k]).strip()
    return src


def map_quest_delta(
    dx: float,
    dy: float,
    dz: float,
    axis_map: Mapping[str, str],
) -> tuple[float, float, float]:
    """Map Quest-frame Δxyz into robot-base Δxyz via signed axis permute."""
    quest = {"x": float(dx), "y": float(dy), "z": float(dz)}
    out: list[float] = []
    for robot_axis in ("x", "y", "z"):
        sign, q_axis = parse_axis_token(axis_map[robot_axis])
        out.append(sign * quest[q_axis])
    return out[0], out[1], out[2]


class ApproxIk:
    """Relative EE deltas → small joint nudges; gripper from contract [0,1]."""

    def __init__(self, *, m_to_deg: Mapping[str, float] | None = None, max_step_deg: float = 3.0) -> None:
        self._m_to_deg = dict(m_to_deg or _DEFAULT_M_TO_DEG)
        self._max_step = float(max_step_deg)
        self._anchor: dict[str, tuple[float, float, float]] = {}
        self._seed: dict[str, dict[str, float]] = {}

    def reset(self, arm: str) -> None:
        self._anchor.pop(arm, None)
        self._seed.pop(arm, None)

    def solve(
        self,
        arm: str,
        cmd: TeleopCommand,
        seed_joints: Mapping[str, float],
    ) -> dict[str, float] | None:
        if cmd.joints is not None:
            out = clamp_joints(cmd.joints)
            # Allow gripper override from contract unit field when joints omit it.
            if "gripper" not in out:
                out["gripper"] = gripper_unit_to_percent(cmd.gripper)
            return out

        if cmd.ee_pose is None:
            return None

        if arm not in self._anchor:
            self._anchor[arm] = cmd.ee_pose.position_m
            self._seed[arm] = {k: float(seed_joints.get(k, 0.0)) for k in JOINT_KEYS}
            self._seed[arm]["gripper"] = gripper_unit_to_percent(cmd.gripper)
            return dict(self._seed[arm])

        ax, ay, az = self._anchor[arm]
        x, y, z = cmd.ee_pose.position_m
        dx, dy, dz = x - ax, y - ay, z - az

        q = dict(self._seed[arm])
        # OpenXR-ish: +y lateral, +z up, +x forward after rotate_x_90 on sender.
        q["shoulder_pan"] = q["shoulder_pan"] + self._clip(dy * self._m_to_deg["y"])
        q["shoulder_lift"] = q["shoulder_lift"] + self._clip(
            (-dx * 0.4 + dz) * self._m_to_deg["z"] * 0.5
        )
        q["elbow_flex"] = q["elbow_flex"] + self._clip(-dx * self._m_to_deg["x"] * 0.5)
        # Soft orientation: yaw from quat → wrist_roll
        q["wrist_roll"] = q["wrist_roll"] + self._clip(_yaw_deg(cmd.ee_pose) * 0.15)
        q["gripper"] = gripper_unit_to_percent(cmd.gripper)

        # Advance seed so subsequent deltas accumulate smoothly.
        self._seed[arm] = clamp_joints(q)
        self._anchor[arm] = cmd.ee_pose.position_m
        return dict(self._seed[arm])

    def _clip(self, delta: float) -> float:
        return max(-self._max_step, min(self._max_step, float(delta)))


def _yaw_deg(pose: EePose) -> float:
    """Extract yaw (Z) from xyzw quaternion, degrees."""
    x, y, z, w = pose.quat_xyzw
    # yaw from quaternion (Z-up)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def _load_robot_kinematics(urdf_path: str, *, target_frame: str = "gripper_frame_link"):
    """Construct lerobot RobotKinematics or raise clearly."""
    path = Path(urdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"URDF not found: {path}")
    try:
        from lerobot.model import RobotKinematics  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "lerobot.model.RobotKinematics required for --ik relative|placo "
            "(install lerobot with placo on the Pi)"
        ) from exc
    joint_names = list(ARM_JOINT_KEYS)
    try:
        return RobotKinematics(
            str(path),
            target_frame,
            joint_names=joint_names,
        )
    except TypeError:
        # Older signature without joint_names kw
        return RobotKinematics(str(path), target_frame)


class PlacoIk:
    """Thin wrapper around lerobot ``RobotKinematics`` (optional dependency)."""

    def __init__(self, urdf_path: str, *, target_frame: str = "gripper_frame_link") -> None:
        self._kin = _load_robot_kinematics(urdf_path, target_frame=target_frame)
        self._q_guess: dict[str, list[float]] = {}
        self._fallback = ApproxIk()

    def reset(self, arm: str) -> None:
        self._q_guess.pop(arm, None)
        self._fallback.reset(arm)

    def solve(
        self,
        arm: str,
        cmd: TeleopCommand,
        seed_joints: Mapping[str, float],
    ) -> dict[str, float] | None:
        if cmd.joints is not None:
            return self._fallback.solve(arm, cmd, seed_joints)
        if cmd.ee_pose is None:
            return None

        try:
            from lerobot.utils.rotation import Rotation  # type: ignore[import-untyped]
            import numpy as np
        except ImportError:
            logger.warning("placo IK unavailable; using approx")
            return self._fallback.solve(arm, cmd, seed_joints)

        q0 = [float(seed_joints.get(k, 0.0)) for k in ARM_JOINT_KEYS]
        if arm in self._q_guess:
            q0 = self._q_guess[arm]

        t_des = np.eye(4, dtype=float)
        t_des[:3, 3] = list(cmd.ee_pose.position_m)
        # Contract stores xyzw; scipy/lerobot Rotation often wants xyzw as well.
        t_des[:3, :3] = Rotation.from_quat(list(cmd.ee_pose.quat_xyzw)).as_matrix()

        try:
            q_target = self._kin.inverse_kinematics(
                np.asarray(q0, dtype=float),
                t_des,
                orientation_weight=0.0,  # position-first for 5-DoF SO-101
            )
        except Exception as exc:  # noqa: BLE001 — keep teleop alive
            logger.warning("placo IK failed (%s); approx fallback", exc)
            return self._fallback.solve(arm, cmd, seed_joints)

        self._q_guess[arm] = [float(v) for v in q_target[: len(ARM_JOINT_KEYS)]]
        out = {name: float(q_target[i]) for i, name in enumerate(ARM_JOINT_KEYS)}
        out["gripper"] = gripper_unit_to_percent(cmd.gripper)
        return clamp_joints(out)


class RelativeEeIk:
    """Clutch-relative gripper-tip tracking via FK anchor + mapped Quest Δ + IK.

    First valid frame after ``reset`` latches controller pose and FK tip.
    Subsequent frames move the tip by ``pos_scale * axis_map(Δquest)``.
    Orientation at engage is held (position-first IK). Construction fails hard
    if URDF/placo cannot load — no silent ApproxIk fallback.
    """

    def __init__(
        self,
        urdf_path: str,
        *,
        target_frame: str = "gripper_frame_link",
        pos_scale: float = 1.0,
        axis_map: Mapping[str, str] | None = None,
        soft_limits: SoftLimits | None = None,
        kinematics: object | None = None,
    ) -> None:
        self._pos_scale = float(pos_scale)
        self._axis_map = normalize_axis_map(axis_map)
        self._soft = soft_limits or SoftLimits(enabled=False)
        self._kin = kinematics if kinematics is not None else _load_robot_kinematics(
            urdf_path, target_frame=target_frame
        )
        self._ctrl0: dict[str, tuple[float, float, float]] = {}
        self._tip0: dict[str, Sequence[float]] = {}
        self._tip_rot0: dict[str, object] = {}
        self._q_guess: dict[str, list[float]] = {}

    def reset(self, arm: str) -> None:
        self._ctrl0.pop(arm, None)
        self._tip0.pop(arm, None)
        self._tip_rot0.pop(arm, None)
        self._q_guess.pop(arm, None)

    def update_runtime(
        self,
        *,
        pos_scale: float | None = None,
        axis_map: Mapping[str, str] | None = None,
        soft_limits: SoftLimits | None = None,
    ) -> None:
        """Hot-reload motion/safety knobs without dropping clutch anchors."""
        if pos_scale is not None:
            self._pos_scale = float(pos_scale)
        if axis_map is not None:
            self._axis_map = normalize_axis_map(axis_map)
        if soft_limits is not None:
            self._soft = soft_limits

    def solve(
        self,
        arm: str,
        cmd: TeleopCommand,
        seed_joints: Mapping[str, float],
    ) -> dict[str, float] | None:
        if cmd.joints is not None:
            out = clamp_joints(cmd.joints)
            if "gripper" not in out:
                out["gripper"] = gripper_unit_to_percent(cmd.gripper)
            return out
        if cmd.ee_pose is None:
            return None

        import numpy as np

        q_seed = [float(seed_joints.get(k, 0.0)) for k in ARM_JOINT_KEYS]

        if arm not in self._ctrl0:
            self._ctrl0[arm] = cmd.ee_pose.position_m
            t0 = np.asarray(self._kin.forward_kinematics(np.asarray(q_seed, dtype=float)), dtype=float)
            self._tip0[arm] = [float(v) for v in t0[:3, 3]]
            self._tip_rot0[arm] = np.array(t0[:3, :3], dtype=float, copy=True)
            self._q_guess[arm] = list(q_seed)
            out = {k: float(seed_joints.get(k, 0.0)) for k in JOINT_KEYS}
            out["gripper"] = gripper_unit_to_percent(cmd.gripper)
            return clamp_joints(out)

        cx, cy, cz = self._ctrl0[arm]
        px, py, pz = cmd.ee_pose.position_m
        mx, my, mz = map_quest_delta(px - cx, py - cy, pz - cz, self._axis_map)
        scale = self._pos_scale
        tip0 = (
            float(self._tip0[arm][0]),
            float(self._tip0[arm][1]),
            float(self._tip0[arm][2]),
        )
        tip_raw = (
            tip0[0] + mx * scale,
            tip0[1] + my * scale,
            tip0[2] + mz * scale,
        )
        # Include tip0 in the soft box so nest-outside-bounds does not kill
        # depth or yank the arm down/up on clutch engage.
        tip_des = self._soft.clamp_tip_anchored(arm, tip0, tip_raw)

        t_des = np.eye(4, dtype=float)
        t_des[:3, :3] = self._tip_rot0[arm]
        t_des[:3, 3] = tip_des

        q0 = self._q_guess.get(arm, q_seed)
        try:
            q_target = self._kin.inverse_kinematics(
                np.asarray(q0, dtype=float),
                t_des,
                orientation_weight=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("relative EE IK failed for %s: %s", arm, exc)
            return None

        self._q_guess[arm] = [float(v) for v in q_target[: len(ARM_JOINT_KEYS)]]
        out = {name: float(q_target[i]) for i, name in enumerate(ARM_JOINT_KEYS)}
        out["gripper"] = gripper_unit_to_percent(cmd.gripper)
        return self._soft.clamp_joints(arm, out)


def build_ik(
    kind: str,
    *,
    urdf: str | None = None,
    max_step_deg: float = 3.0,
    m_to_deg: Mapping[str, float] | None = None,
    pos_scale: float = 1.0,
    axis_map: Mapping[str, str] | None = None,
    soft_limits: SoftLimits | None = None,
) -> IkSolver:
    """Factory for CLI ``--ik``."""
    kind = kind.lower().strip()
    if kind == "approx":
        return ApproxIk(m_to_deg=m_to_deg, max_step_deg=max_step_deg)
    if kind == "placo":
        path = urdf or str(DEFAULT_URDF_PATH)
        return PlacoIk(path)
    if kind == "relative":
        path = urdf or str(DEFAULT_URDF_PATH)
        return RelativeEeIk(
            path,
            pos_scale=pos_scale,
            axis_map=axis_map,
            soft_limits=soft_limits,
        )
    if kind == "none":
        return ApproxIk(m_to_deg=m_to_deg, max_step_deg=max_step_deg)
    raise ValueError(f"unknown ik kind {kind!r}; use approx|placo|relative|none")
