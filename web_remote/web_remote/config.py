"""Load SO-101 arm + camera settings from so101_dual_cam.yaml (or similar)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.robots.so_follower import SO101FollowerConfig

from so101_common.env import (
    apply_lab_overrides,
    lab_env_setup_hint,
    load_lab_env,
    missing_device_keys,
)
from so101_common.joints import JOINT_KEYS, JOINT_LIMITS_DEG, clamp_joints  # noqa: F401 (re-export)
from so101_common.paths import DEFAULT_CONFIG_PATH  # noqa: F401 (re-export)

from .drive_profile import DriveProfile, resolve_drive_profile

# Joint clamps live in so101_common.joints (canonical). JOINT_LIMITS is kept as a
# module-level alias for existing imports/tests.
JOINT_LIMITS = JOINT_LIMITS_DEG

# Web Remote drives both ports as position-controlled followers.
# The yaml "leader_arm" is the second arm (historically the teleop leader).
ARM_FOLLOWER = "follower"
ARM_LEADER = "leader"

# Logical stream name used by center_watch / Quest Televiz / datasets.
CENTER_STREAM = "center"

# Short names → yaml keys under cameras:.
CENTER_SOURCE_ALIASES: dict[str, str] = {
    "xiao": "center_xiao",
    "esp32": "center_xiao",
    "esp32cam": "center_xiao",
    "d435": "center_d435",
    "realsense": "center_d435",
    "hand": "center_d435",
}


# Control modes for RobotSession (browser drive vs classic leader→follower).
MODE_BROWSER = "browser"
MODE_LEADER_FOLLOW = "leader_follow"


@dataclass
class WebRemoteConfig:
    """Parsed startup config for one or two arms + cameras."""

    arms: dict[str, SO101FollowerConfig] = field(default_factory=dict)
    # Per logical arm name → motion profile (full vs gentle_7v4, …).
    drive_profiles: dict[str, DriveProfile] = field(default_factory=dict)
    cameras: dict[str, Any] = field(default_factory=dict)
    # Cameras attach to this arm's robot object (frames live on that instance).
    camera_host_arm: str = ARM_FOLLOWER
    # Resolved center source key (e.g. center_xiao) when center_source is used.
    center_source: str | None = None
    # Physical leader port for hand teleop (so101_leader), even if not browser-driven.
    leader_hand_port: str | None = None
    # Calibration id for so101_leader (≠ my_leader_drive).
    leader_hand_id: str = "my_leader"


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML config file into a dict."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def resolve_center_source(data: dict[str, Any] | None = None) -> str | None:
    """Pick active center candidate: env CENTER_SOURCE, else yaml center_source.

    Returns a cameras: key (e.g. ``center_d435``), or None for legacy yaml that
    already defines ``center`` directly.
    """
    env = os.environ.get("CENTER_SOURCE", "").strip().lower()
    raw = env or str((data or {}).get("center_source", "")).strip().lower()
    if not raw:
        return None
    if raw == CENTER_STREAM:
        return CENTER_STREAM
    return CENTER_SOURCE_ALIASES.get(raw, raw)


def _opencv_index_or_path(cam: dict[str, Any]) -> int | Path | str:
    """Resolve OpenCV source: device index, /dev/videoX, or HTTP MJPEG URL (ESP32-CAM)."""
    if "url" in cam or "stream_url" in cam:
        return str(cam.get("url") or cam.get("stream_url"))
    raw = cam.get("index_or_path", cam.get("index", cam.get("device", 0)))
    if isinstance(raw, int):
        return raw
    text = str(raw)
    if text.isdigit():
        return int(text)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return Path(text)


def _camera_from_dict(name: str, cam: dict[str, Any]) -> Any:
    """Build one LeRobot CameraConfig from a yaml camera entry."""
    cls_name = str(cam.get("class", cam.get("type", ""))).lower()
    fps = int(cam.get("fps", 30))
    width = int(cam.get("width", 640))
    height = int(cam.get("height", 480))

    if cls_name in {"opencvcamera", "opencv", "esp32cam", "mjpeg"}:
        index_or_path = _opencv_index_or_path(cam)
        is_url = isinstance(index_or_path, str) and index_or_path.startswith("http")
        cam_kwargs: dict[str, Any] = {"index_or_path": index_or_path}
        if not is_url:
            cam_kwargs.update(fps=fps, width=width, height=height)
        if cam.get("fourcc"):
            cam_kwargs["fourcc"] = cam["fourcc"]
        return OpenCVCameraConfig(**cam_kwargs)
    if cls_name in {"realsensecamera", "intelrealsense", "realsense"}:
        serial = str(cam.get("serial_number", cam.get("serial_number_or_name", "")))
        if not serial:
            raise ValueError(f"Camera {name!r}: RealSense needs serial_number")
        return RealSenseCameraConfig(
            serial_number_or_name=serial,
            fps=fps,
            width=width,
            height=height,
            use_depth=bool(cam.get("use_depth", False)),
        )
    raise ValueError(f"Unsupported camera class for {name!r}: {cls_name}")


def _is_center_candidate(name: str) -> bool:
    """True for keys that compete for the logical ``center`` stream."""
    return name == CENTER_STREAM or name.startswith("center_")


def _preview_stream_name(yaml_key: str) -> str:
    """Stream name when a center_* candidate is opened as a side preview."""
    # center_d435 → d435 (keeps UI short; depth twin becomes d435_depth).
    if yaml_key.startswith("center_"):
        return yaml_key[len("center_") :]
    return yaml_key


def _build_cameras(
    raw: dict[str, Any] | None,
    *,
    center_source: str | None = None,
) -> dict[str, Any]:
    """Map yaml camera entries to LeRobot CameraConfig objects.

    When ``center_source`` names a candidate (e.g. ``center_d435``), that entry
    is published as stream ``center``. Other ``center_*`` candidates are skipped
    unless ``preview: true`` (opened under a short name, e.g. ``d435``) so the
    operator can check placement without switching the logical center feed.
    """
    if not raw:
        return {}

    selected = center_source
    if selected and selected != CENTER_STREAM and selected not in raw:
        raise ValueError(
            f"center_source {selected!r} not found under cameras: "
            f"(known: {', '.join(sorted(raw))})"
        )

    cameras: dict[str, Any] = {}
    for name, cam in raw.items():
        if not isinstance(cam, dict):
            continue
        if cam.get("enabled", True) is False:
            continue

        # With center_source set, only the chosen candidate is opened as "center".
        if selected and _is_center_candidate(name):
            if name != selected:
                # Optional side preview (e.g. D435 RGB+depth while center is Xiao).
                if cam.get("preview", False) is True:
                    cameras[_preview_stream_name(name)] = _camera_from_dict(name, cam)
                continue
            cameras[CENTER_STREAM] = _camera_from_dict(name, cam)
            continue

        cameras[name] = _camera_from_dict(name, cam)

    if selected and CENTER_STREAM not in cameras:
        raise ValueError(f"center_source {selected!r} is disabled or missing")

    return cameras


def _arm_cfg(port: str, robot_id: str, *, max_relative_target: float = 30.0) -> SO101FollowerConfig:
    """Build a torque-controlled follower config (used for both physical arms)."""
    return SO101FollowerConfig(
        port=str(port),
        id=robot_id,
        cameras={},
        # Ceiling; the control loop overwrites from RateRouter × drive_profile each tick.
        max_relative_target=float(max_relative_target),
        use_degrees=True,
    )


def _profile_for_arm_yaml(arm_yaml: dict[str, Any], *, arm: str) -> DriveProfile:
    """Read ``drive_profile`` from one arm block (default depends on arm name)."""
    return resolve_drive_profile(arm_yaml.get("drive_profile"), arm=arm)


def build_web_remote_config(
    path: Path,
    *,
    follower_id: str = "my_follower",
    leader_id: str = "my_leader_drive",
    enable_leader: bool = True,
) -> WebRemoteConfig:
    """Build configs for follower (+ optional leader port driven as a second follower)."""
    data = load_yaml(path)
    # 実機の IP・シリアルは gitignored configs/lab.local.env から流し込む
    # （テンプレート: configs/lab.local.env.example）。
    load_lab_env()
    apply_lab_overrides(data)
    missing = missing_device_keys(data, section="all")
    if missing:
        raise ValueError(lab_env_setup_hint(missing))
    robot = data.get("robot") or {}
    follower = robot.get("follower_arm") or {}
    leader = robot.get("leader_arm") or {}

    follower_port = follower.get("port") or robot.get("port")
    if not follower_port:
        raise ValueError(
            f"Missing robot.follower_arm.port in {path} — "
            "set SO101_FOLLOWER_PORT in configs/lab.local.env"
        )

    follower_profile = _profile_for_arm_yaml(follower if isinstance(follower, dict) else {}, arm=ARM_FOLLOWER)
    arms: dict[str, SO101FollowerConfig] = {
        ARM_FOLLOWER: _arm_cfg(
            str(follower_port),
            follower_id,
            max_relative_target=follower_profile.effective_step(30.0),
        ),
    }
    drive_profiles: dict[str, DriveProfile] = {ARM_FOLLOWER: follower_profile}

    leader_port = leader.get("port")
    # CLI --no-leader (enable_leader=False) must win over yaml enabled: true
    leader_enabled = bool(leader.get("enabled", True)) and enable_leader
    if leader_port and leader_enabled:
        leader_yaml = leader if isinstance(leader, dict) else {}
        leader_profile = _profile_for_arm_yaml(leader_yaml, arm=ARM_LEADER)
        arms[ARM_LEADER] = _arm_cfg(
            str(leader_port),
            leader_id,
            max_relative_target=leader_profile.effective_step(30.0),
        )
        drive_profiles[ARM_LEADER] = leader_profile

    # Hand-teleop id: yaml teleop_id / hand_teleop_id, else classic my_leader.
    hand_id = str(
        leader.get("teleop_id")
        or leader.get("hand_teleop_id")
        or "my_leader"
    ).strip() or "my_leader"

    center_source = resolve_center_source(data)
    return WebRemoteConfig(
        arms=arms,
        drive_profiles=drive_profiles,
        cameras=_build_cameras(data.get("cameras"), center_source=center_source),
        camera_host_arm=ARM_FOLLOWER,
        center_source=center_source,
        leader_hand_port=str(leader_port) if leader_port else None,
        leader_hand_id=hand_id,
    )


def build_follower_config(path: Path, *, robot_id: str = "my_follower") -> SO101FollowerConfig:
    """Backward-compatible single-arm builder (follower only + cameras on config)."""
    bundle = build_web_remote_config(path, follower_id=robot_id, enable_leader=False)
    cfg = bundle.arms[ARM_FOLLOWER]
    cfg.cameras = bundle.cameras
    return cfg


