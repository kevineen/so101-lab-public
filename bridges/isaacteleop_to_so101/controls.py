"""YAML-driven Quest controller mapping (clutch / gripper / motion).

Axis names match ``ControllerInputIndex`` members in lowercase, e.g.
``primary_click``, ``trigger_value``, ``thumbstick_y``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from .contract import ArmResolve, DEFAULT_ARM_RESOLVE

# Pi カメラサーバの既定 URL。SO101_PI_BASE_URL（configs/lab.local.env）で設定する。
# 正本は configs/quest_teleop.yaml の cameras.pi_base_url。未設定時は localhost。
DEFAULT_PI_BASE_URL = os.environ.get("SO101_PI_BASE_URL", "http://127.0.0.1:8765")
from .safety import SoftLimits, parse_soft_limits

# Default next to repo configs/
_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "quest_teleop.yaml"

_PHYSICAL_ARMS = frozenset({"follower", "leader"})

AXIS_ALIASES = {
    "primary_click": "PRIMARY_CLICK",
    "secondary_click": "SECONDARY_CLICK",
    "squeeze_value": "SQUEEZE_VALUE",
    "trigger_value": "TRIGGER_VALUE",
    "thumbstick_x": "THUMBSTICK_X",
    "thumbstick_y": "THUMBSTICK_Y",
    "thumbstick_click": "THUMBSTICK_CLICK",
    "menu_click": "MENU_CLICK",
}


@dataclass
class CameraStreamCfg:
    name: str
    enabled: bool = True


@dataclass
class CameraPlacement:
    distance_m: float = 1.5
    yaw_deg: float = 0.0
    pitch_deg: float = -5.0
    x_m: float = 0.0


@dataclass
class TeleopControlsConfig:
    """Resolved quest teleop settings."""

    arms: list[str] = field(default_factory=lambda: ["left", "right"])
    clutch_axis: str = "primary_click"
    clutch_threshold: float = 0.5
    gripper_axis: str = "trigger_value"
    gripper_deadzone: float = 0.05
    gripper_invert: bool = False
    motion_mode: str = "approx"  # approx | relative_ee
    pos_scale: float = 1.0
    max_step_deg: float = 3.0
    m_to_deg: dict[str, float] = field(
        default_factory=lambda: {"x": 120.0, "y": 140.0, "z": 160.0}
    )
    axis_map: dict[str, str] = field(
        default_factory=lambda: {"x": "x", "y": "y", "z": "z"}
    )
    # Controller side (left/right) → physical port (follower/leader)
    arm_resolve: ArmResolve = field(default_factory=lambda: ArmResolve())
    soft_limits: SoftLimits = field(default_factory=lambda: SoftLimits(enabled=False))
    use_hello_joints: bool = True
    joint_offsets_deg: dict[str, dict[str, float]] = field(default_factory=dict)
    cameras_enabled: bool = True
    cameras_pi_base_url: str = DEFAULT_PI_BASE_URL
    camera_streams: list[CameraStreamCfg] = field(default_factory=list)
    camera_placements: dict[str, CameraPlacement] = field(default_factory=dict)
    source_path: Path | None = None

    def clutch_index_name(self) -> str:
        return resolve_axis_name(self.clutch_axis)

    def gripper_index_name(self) -> str:
        return resolve_axis_name(self.gripper_axis)


def parse_arm_resolve(raw: Mapping[str, Any] | None) -> ArmResolve:
    """Parse yaml ``arm_resolve`` (controller side → follower|leader)."""
    if not raw:
        return ArmResolve(
            left=DEFAULT_ARM_RESOLVE.left,
            right=DEFAULT_ARM_RESOLVE.right,
            single=DEFAULT_ARM_RESOLVE.single,
        )
    left = str(raw.get("left", DEFAULT_ARM_RESOLVE.left)).strip().lower()
    right = str(raw.get("right", DEFAULT_ARM_RESOLVE.right)).strip().lower()
    single = str(raw.get("single", DEFAULT_ARM_RESOLVE.single)).strip().lower()
    for name, val in (("left", left), ("right", right), ("single", single)):
        if val not in _PHYSICAL_ARMS:
            raise ValueError(
                f"arm_resolve.{name} must be follower|leader, got {val!r}"
            )
    return ArmResolve(left=left, right=right, single=single)


def resolve_axis_name(axis: str) -> str:
    """Map yaml axis string → ControllerInputIndex member name."""
    key = str(axis).strip().lower()
    if key not in AXIS_ALIASES:
        raise ValueError(
            f"unknown control axis {axis!r}; choose one of {sorted(AXIS_ALIASES)}"
        )
    return AXIS_ALIASES[key]


def axis_value(controller_group: Any, axis: str) -> float:
    """Read one float axis from a ControllerInput tensor group / sequence."""
    from isaaccapture.retargeting_engine.tensor_types import ControllerInputIndex

    member = resolve_axis_name(axis)
    idx = getattr(ControllerInputIndex, member)
    return float(controller_group[idx])


def clutch_engaged(value: float, *, threshold: float) -> bool:
    """Digital or analog clutch: engaged when value >= threshold."""
    return float(value) >= float(threshold)


def gripper_axis_is_bipolar(axis: str) -> bool:
    """Thumbsticks are ``[-1, 1]``; triggers/clicks/squeeze are ``[0, 1]``."""
    return str(axis).strip().lower().startswith("thumbstick")


def gripper_axis_to_contract(
    value: float,
    *,
    deadzone: float = 0.05,
    invert: bool = False,
    bipolar: bool = False,
) -> float:
    """Map a controller axis to contract gripper ``[0, 1]`` (0=open, 1=closed).

    Unipolar (trigger / squeeze): already ``[0, 1]``.
    Bipolar (thumbstick): ``[-1, 1]`` → ``[0, 1]`` (+ closes unless inverted).
    """
    v = float(value)
    if invert:
        v = -v
    if bipolar:
        v = (max(-1.0, min(1.0, v)) + 1.0) / 2.0
    else:
        v = max(0.0, min(1.0, v))
    if v < deadzone:
        return 0.0
    span = max(1e-6, 1.0 - deadzone)
    return max(0.0, min(1.0, (v - deadzone) / span))


def scale_pose_delta(
    pose7: list[float] | tuple[float, ...],
    anchor: tuple[float, float, float] | None,
    *,
    pos_scale: float,
) -> list[float]:
    """Scale position relative to an anchor (identity if no anchor yet).

    Orientation is passed through unchanged. Used so ``pos_scale`` softens
    OpenXR meters before ApproxIk on the Pi.
    """
    out = [float(x) for x in pose7]
    if anchor is None or abs(pos_scale - 1.0) < 1e-9:
        return out
    ax, ay, az = anchor
    out[0] = ax + (out[0] - ax) * pos_scale
    out[1] = ay + (out[1] - ay) * pos_scale
    out[2] = az + (out[2] - az) * pos_scale
    return out


def overrides_path_for(config_path: Path) -> Path:
    """Sibling overrides file edited by the Quest settings UI."""
    return config_path.with_name("quest_teleop.local.overrides.yaml")


def deep_merge_dict(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay onto base (dict values only)."""
    out: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, Mapping)
        ):
            out[key] = deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def load_raw_teleop_dict(path: str | Path | None = None) -> tuple[dict[str, Any], Path, Path]:
    """Load base yaml + optional local overrides. Returns (data, base_path, overrides_path)."""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    data: dict[str, Any] = {}
    if cfg_path.is_file():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{cfg_path}: root must be a mapping")
        data = loaded
    ov_path = overrides_path_for(cfg_path)
    if ov_path.is_file():
        overlay = yaml.safe_load(ov_path.read_text(encoding="utf-8")) or {}
        if isinstance(overlay, dict):
            data = deep_merge_dict(data, overlay)
    return data, cfg_path, ov_path


def save_teleop_overrides(
    overlay: Mapping[str, Any],
    *,
    config_path: str | Path | None = None,
) -> Path:
    """Write/merge Quest UI overrides (does not rewrite the main yaml)."""
    cfg_path = Path(config_path) if config_path else _DEFAULT_CONFIG
    ov_path = overrides_path_for(cfg_path)
    existing: dict[str, Any] = {}
    if ov_path.is_file():
        loaded = yaml.safe_load(ov_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            existing = loaded
    merged = deep_merge_dict(existing, dict(overlay))
    ov_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Auto-written by Quest teleop settings UI. Merged over quest_teleop.yaml.\n"
        "# Safe to delete; gitignored as *.local.overrides.yaml\n"
    )
    ov_path.write_text(
        header + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return ov_path


def load_teleop_config(path: str | Path | None = None) -> TeleopControlsConfig:
    """Load ``quest_teleop.yaml`` (+ local overrides if present)."""
    data, cfg_path, _ov_path = load_raw_teleop_dict(path)

    controls = data.get("controls") or {}
    motion = data.get("motion") or {}
    home = data.get("home") or {}
    cameras = data.get("cameras") or {}

    arms_raw = data.get("arms") or ["left", "right"]
    arms = [str(a) for a in arms_raw]
    for a in arms:
        if a not in {"left", "right", "single"}:
            raise ValueError(f"invalid arm {a!r}")

    m_to_deg = {"x": 120.0, "y": 140.0, "z": 160.0}
    raw_m = motion.get("m_to_deg") or {}
    if isinstance(raw_m, Mapping):
        for k in ("x", "y", "z"):
            if k in raw_m:
                m_to_deg[k] = float(raw_m[k])

    from .ik import normalize_axis_map

    motion_mode = str(motion.get("mode", "approx")).strip().lower()
    if motion_mode not in {"approx", "relative_ee"}:
        raise ValueError(f"motion.mode must be approx|relative_ee, got {motion_mode!r}")
    axis_map = normalize_axis_map(
        motion.get("axis_map") if isinstance(motion.get("axis_map"), Mapping) else None
    )

    streams: list[CameraStreamCfg] = []
    for entry in cameras.get("streams") or []:
        if isinstance(entry, str):
            streams.append(CameraStreamCfg(name=entry, enabled=True))
        elif isinstance(entry, Mapping):
            streams.append(
                CameraStreamCfg(
                    name=str(entry["name"]),
                    enabled=bool(entry.get("enabled", True)),
                )
            )

    placements: dict[str, CameraPlacement] = {}
    for name, raw in (cameras.get("placements") or {}).items():
        if not isinstance(raw, Mapping):
            continue
        placements[str(name)] = CameraPlacement(
            distance_m=float(raw.get("distance_m", 1.5)),
            yaw_deg=float(raw.get("yaw_deg", 0.0)),
            pitch_deg=float(raw.get("pitch_deg", -5.0)),
            x_m=float(raw.get("x_m", 0.0)),
        )

    offsets: dict[str, dict[str, float]] = {}
    raw_off = home.get("joint_offsets_deg") or {}
    if isinstance(raw_off, Mapping):
        for arm, joints in raw_off.items():
            if isinstance(joints, Mapping):
                offsets[str(arm)] = {str(k): float(v) for k, v in joints.items()}

    clutch = str(controls.get("clutch", "primary_click"))
    gripper = str(controls.get("gripper", "trigger_value"))
    # Validate axes early
    resolve_axis_name(clutch)
    resolve_axis_name(gripper)

    arm_resolve_raw = data.get("arm_resolve")
    if arm_resolve_raw is not None and not isinstance(arm_resolve_raw, Mapping):
        raise ValueError("arm_resolve must be a mapping")
    arm_resolve = parse_arm_resolve(
        arm_resolve_raw if isinstance(arm_resolve_raw, Mapping) else None
    )
    safety_raw = data.get("safety")
    if safety_raw is not None and not isinstance(safety_raw, Mapping):
        raise ValueError("safety must be a mapping")
    soft_limits = parse_soft_limits(
        safety_raw if isinstance(safety_raw, Mapping) else None
    )

    return TeleopControlsConfig(
        arms=arms,
        clutch_axis=clutch,
        clutch_threshold=float(controls.get("clutch_threshold", 0.5)),
        gripper_axis=gripper,
        gripper_deadzone=float(controls.get("gripper_deadzone", 0.05)),
        gripper_invert=bool(controls.get("gripper_invert", False)),
        motion_mode=motion_mode,
        pos_scale=float(motion.get("pos_scale", 1.0)),
        max_step_deg=float(motion.get("max_step_deg", 3.0)),
        m_to_deg=m_to_deg,
        axis_map=axis_map,
        arm_resolve=arm_resolve,
        soft_limits=soft_limits,
        use_hello_joints=bool(home.get("use_hello_joints", True)),
        joint_offsets_deg=offsets,
        cameras_enabled=bool(cameras.get("enabled", True)),
        cameras_pi_base_url=str(cameras.get("pi_base_url") or DEFAULT_PI_BASE_URL),
        camera_streams=streams,
        camera_placements=placements,
        source_path=cfg_path if cfg_path.is_file() else None,
    )


class ClutchState:
    """Per-arm clutch edge detector + pose scaling anchor."""

    def __init__(self) -> None:
        self.engaged: dict[str, bool] = {}
        self.scale_anchor: dict[str, tuple[float, float, float]] = {}

    def update(self, arm: str, engaged: bool) -> tuple[bool, bool]:
        """Return ``(engaged, rising_edge)``."""
        prev = self.engaged.get(arm, False)
        rising = engaged and not prev
        if not engaged:
            self.scale_anchor.pop(arm, None)
        self.engaged[arm] = engaged
        return engaged, rising

    def scaled_pose(
        self,
        arm: str,
        pose7: list[float] | tuple[float, ...],
        *,
        pos_scale: float,
        rising: bool,
    ) -> list[float]:
        if rising or arm not in self.scale_anchor:
            self.scale_anchor[arm] = (float(pose7[0]), float(pose7[1]), float(pose7[2]))
        return scale_pose_delta(pose7, self.scale_anchor[arm], pos_scale=pos_scale)
