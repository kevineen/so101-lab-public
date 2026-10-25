"""Thread-safe session wrapping one or two SO-101 arms + camera frames."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Protocol

import cv2
import numpy as np

from lerobot.motors.motors_bus import MotorCalibration
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

from .calibration import CalibrationMixin
from .center_watch import CENTER_CAMERA, CenterWatch
from .config import (
    ARM_FOLLOWER,
    ARM_LEADER,
    JOINT_KEYS,
    MODE_BROWSER,
    MODE_LEADER_FOLLOW,
    WebRemoteConfig,
    clamp_joints,
)
from .depth_viz import depth_stream_name, read_colorized_depth
from .drive_profile import DriveProfile, apply_body_acceleration
from .home_pose import (
    DEFAULT_HOME_PATH,
    default_joints,
    joints_for_arm,
    load_home_file,
    near_home,
    save_home_file,
)
from .jev_router import JevRouter
from .rate_router import RateRouter, classify_command, targets_near_edge

logger = logging.getLogger(__name__)


class _FrameCamera(Protocol):
    """Camera object that can return one RGB frame."""

    def async_read(self, timeout_ms: int = 200) -> np.ndarray | None: ...

    def read(self) -> np.ndarray | None: ...


def _camera_names_with_depth(cameras: dict[str, Any]) -> list[str]:
    """List color stream names plus ``*_depth`` twins when ``use_depth`` is on."""
    names: list[str] = []
    for name, cam in cameras.items():
        names.append(name)
        if getattr(cam, "use_depth", False):
            names.append(depth_stream_name(name))
    return names


def _store_camera_frames(
    frames: dict[str, np.ndarray],
    name: str,
    cam: Any,
    *,
    read_color,
) -> None:
    """Update ``frames`` with color and optional colorized depth for one camera."""
    frame = read_color(name, cam)
    if frame is not None:
        frames[name] = frame
    depth_rgb = read_colorized_depth(cam)
    if depth_rgb is not None:
        frames[depth_stream_name(name)] = depth_rgb


class RobotSession(CalibrationMixin):
    """Owns arm connections, joint targets per arm, and camera frames."""

    cameras_only = False

    def __init__(self, config: WebRemoteConfig, *, control_hz: float = 40.0) -> None:
        self.config = config
        self.control_hz = control_hz
        self.robots: dict[str, SO101Follower] = {}
        self._lock = threading.RLock()
        self._estop = threading.Event()
        self._stop_control = threading.Event()
        self._control_thread: threading.Thread | None = None
        self._camera_thread: threading.Thread | None = None
        self._watch_thread: threading.Thread | None = None
        # Cruise uses the startup rate (default 40 Hz). Approach is the careful 20 Hz expert.
        self._router = RateRouter(cruise_hz=float(control_hz), jev=JevRouter())
        self._watch = CenterWatch()
        self._cmd_prev: dict[str, dict[str, float]] | None = None
        self._cmd_prev_t: float | None = None
        self._client_token: str | None = None
        self._targets: dict[str, dict[str, float]] = {
            name: {k: 0.0 for k in JOINT_KEYS} for name in config.arms
        }
        self._frames: dict[str, np.ndarray] = {}
        self._connected = False
        # Browser teleop: torque + commands only for ``_teleop_arm`` (others soft).
        self._teleop_enabled = True
        self._teleop_arm: str | None = ARM_FOLLOWER if ARM_FOLLOWER in config.arms else next(iter(config.arms), None)
        # browser = slider drive; leader_follow = physical leader → follower.
        self._control_mode: str = MODE_BROWSER
        self._leader_hand: SO101Leader | None = None
        # Saved follower-drive config for leader port (restored when leaving hand mode).
        self._leader_drive_cfg: SO101FollowerConfig | None = config.arms.get(ARM_LEADER)
        # Browser-driven per-motor calibration (torque off by default, draft JSON).
        self._calib_mode = False
        self._calib_arm: str | None = None
        self._calib_draft: dict[str, dict[str, int]] = {}
        self._calib_backup: dict[str, MotorCalibration] = {}
        self._calib_recording: set[str] = set()
        self._calib_mins: dict[str, int] = {}
        self._calib_maxes: dict[str, int] = {}
        self._calib_raw: dict[str, int] = {}
        # Powered jog during calib: hold pose via Goal_Position (limits opened).
        self._calib_drive = False
        self._calib_goals: dict[str, int] = {}
        # Homing: drive one or more arms toward saved nest poses (bypasses single-arm teleop).
        self._homing_arms: set[str] = set()
        self._home_path = DEFAULT_HOME_PATH

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def arm_names(self) -> list[str]:
        return list(self.robots.keys()) if self.robots else list(self.config.arms.keys())

    @property
    def camera_names(self) -> list[str]:
        host = self.robots.get(self.config.camera_host_arm) or next(iter(self.robots.values()), None)
        if host is None:
            return _camera_names_with_depth(self.config.cameras)
        return _camera_names_with_depth(host.cameras)

    def _try_connect_robot(self, config: SO101FollowerConfig) -> SO101Follower:
        """Instantiate and connect a follower; force-release bus/cams on failure."""
        robot = SO101Follower(config)
        try:
            robot.connect(calibrate=False)
        except Exception:
            try:
                if getattr(robot.bus, "is_connected", False):
                    robot.bus.disconnect()
            except Exception:
                logger.debug("Bus cleanup after failed connect raised", exc_info=True)
            for cam in getattr(robot, "cameras", {}).values():
                try:
                    if getattr(cam, "is_connected", False):
                        cam.disconnect()
                except Exception:
                    logger.debug("Camera cleanup after failed connect raised", exc_info=True)
            raise
        return robot

    def _seed_target(self, arm: str, robot: SO101Follower) -> None:
        obs = robot.get_observation()
        for key in JOINT_KEYS:
            pos_key = f"{key}.pos"
            if pos_key in obs and isinstance(obs[pos_key], (int, float)):
                self._targets[arm][key] = float(obs[pos_key])

    def drive_profile(self, arm: str) -> DriveProfile:
        """Resolved motion profile for one arm (defaults to full-rate)."""
        from .drive_profile import DRIVE_PROFILES

        return self.config.drive_profiles.get(arm) or DRIVE_PROFILES["full"]

    def _drive_profile(self, arm: str) -> DriveProfile:
        """Alias kept for internal call sites."""
        return self.drive_profile(arm)

    def _step_for_arm(self, arm: str, router_step: float, *, homing: bool = False) -> float:
        """Rate-router step scaled/capped by the arm's drive_profile."""
        return self._drive_profile(arm).effective_step(router_step, homing=homing)

    def _apply_drive_profile(self, arm: str, robot: SO101Follower) -> None:
        """Apply Feetech acceleration from drive_profile (body joints only)."""
        profile = self._drive_profile(arm)
        try:
            updated = apply_body_acceleration(robot, profile)
        except Exception:
            logger.exception("Failed to apply drive_profile %r on arm %r", profile.name, arm)
            return
        if updated:
            logger.info(
                "Arm %r drive_profile=%s body_acceleration=%s motors=%s",
                arm,
                profile.name,
                profile.body_acceleration,
                ",".join(updated),
            )
        else:
            logger.info("Arm %r drive_profile=%s (stock acceleration)", arm, profile.name)

    def connect(self) -> None:
        """Connect each arm; attach cameras to the host arm; start control loop."""
        with self._lock:
            if self._connected:
                return

            connected: dict[str, SO101Follower] = {}
            try:
                for arm_name, arm_cfg in self.config.arms.items():
                    logger.info("Connecting arm %r on %s ...", arm_name, arm_cfg.port)
                    robot = self._try_connect_robot(arm_cfg)
                    if not robot.calibration:
                        raise RuntimeError(
                            f"No calibration for arm {arm_name!r}. Run once, then restart Web Remote:\n"
                            f"  lerobot-calibrate --robot.type=so101_follower "
                            f"--robot.port={arm_cfg.port} --robot.id={arm_cfg.id or arm_name}"
                        )
                    connected[arm_name] = robot
                    self._targets[arm_name] = {k: 0.0 for k in JOINT_KEYS}
                    self._seed_target(arm_name, robot)
                    self._apply_drive_profile(arm_name, robot)
                    logger.info("Arm %r connected (id=%s)", arm_name, arm_cfg.id)

                # Cameras attach to the designated host arm (usually follower).
                host_name = self.config.camera_host_arm
                if host_name not in connected:
                    host_name = next(iter(connected))
                host = connected[host_name]
                if self.config.cameras:
                    from lerobot.cameras.utils import make_cameras_from_configs

                    for name, cam in make_cameras_from_configs(self.config.cameras).items():
                        try:
                            cam.connect()
                            host.cameras[name] = cam
                            logger.info("Camera %r connected on arm %r", name, host_name)
                        except Exception as exc:
                            logger.warning("Skipping camera %r: %s", name, exc)

            except Exception:
                for robot in connected.values():
                    try:
                        if getattr(robot.bus, "is_connected", False):
                            robot.bus.disconnect()
                    except Exception:
                        logger.debug("Rollback disconnect failed", exc_info=True)
                raise

            self.robots = connected
            self._connected = True
            self._estop.clear()
            self._stop_control.clear()
            # Default: teleop only the primary arm; release torque on the other.
            if self._teleop_arm not in self.robots:
                self._teleop_arm = next(iter(self.robots), None)
            self._apply_teleop_torque_unlocked()
            self._control_thread = threading.Thread(target=self._control_loop, name="web-remote-ctrl", daemon=True)
            self._camera_thread = threading.Thread(target=self._camera_loop, name="web-remote-cams", daemon=True)
            self._watch_thread = threading.Thread(target=self._watch_loop, name="web-remote-watch", daemon=True)
            self._control_thread.start()
            self._camera_thread.start()
            self._watch_thread.start()
            logger.info("Web Remote ready. Arms=%s cameras=%s", self.arm_names, self.camera_names)

    def disconnect(self) -> None:
        """Stop control loop and disconnect all arms / cameras."""
        self._stop_control.set()
        for thread, timeout in (
            (self._control_thread, 3.0),
            (self._camera_thread, 2.0),
            (self._watch_thread, 2.0),
        ):
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
        with self._lock:
            self._disconnect_leader_hand_unlocked()
            for name, robot in list(self.robots.items()):
                try:
                    # Prefer full disconnect when fully connected; else release bus/cams.
                    if robot.is_connected:
                        robot.disconnect()
                    else:
                        if getattr(robot.bus, "is_connected", False):
                            robot.bus.disconnect()
                        for cam in robot.cameras.values():
                            if getattr(cam, "is_connected", False):
                                cam.disconnect()
                except Exception:
                    logger.exception("Error disconnecting arm %r", name)
            self.robots.clear()
            self._control_mode = MODE_BROWSER
            self._connected = False
            self._frames.clear()
            self._client_token = None

    def claim_client(self, token: str) -> bool:
        """Allow only one controlling browser client at a time."""
        with self._lock:
            if self._client_token is None or self._client_token == token:
                self._client_token = token
                return True
            return False

    def release_client(self, token: str) -> None:
        with self._lock:
            if self._client_token == token:
                self._client_token = None

    def set_action(self, joints: dict[str, float], *, arm: str, token: str) -> dict[str, Any]:
        """Update joint targets for one arm after clamp / client checks.

        Targets may update as fast as the client sends; the control loop paces
        motor writes at the active rate (40 Hz cruise, 20 Hz near objects).
        Rejecting mid-flight updates would rewind the client's predicted pose
        and make teleop feel sluggish.
        """
        if self._estop.is_set():
            return {"ok": False, "error": "estop_active"}
        if self._control_mode == MODE_LEADER_FOLLOW:
            return {"ok": False, "error": "leader_follow_active"}
        if self._calib_mode:
            return {"ok": False, "error": "calib_mode_active"}
        if self._homing_arms:
            return {"ok": False, "error": "homing_active", "homing": sorted(self._homing_arms)}
        if not self._teleop_enabled:
            return {"ok": False, "error": "teleop_disabled"}
        if not self.claim_client(token):
            return {"ok": False, "error": "another_client_connected"}
        if arm not in self._targets:
            return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self._targets)}
        if arm != self._teleop_arm:
            return {
                "ok": False,
                "error": "teleop_other_arm",
                "teleop_arm": self._teleop_arm,
                "arms": list(self._targets),
            }

        with self._lock:
            clamped = clamp_joints(joints)
            if not clamped:
                return {"ok": False, "error": "no_valid_joints"}
            self._targets[arm].update(clamped)
            return {"ok": True, "arm": arm, "target": dict(self._targets[arm])}

    def _apply_teleop_torque_unlocked(self) -> None:
        """Enable torque only on the teleop arm; disable torque on all others."""
        for name, robot in self.robots.items():
            if not getattr(robot.bus, "is_connected", False):
                continue
            active = self._teleop_enabled and name == self._teleop_arm
            try:
                if active:
                    robot.bus.enable_torque()
                    self._seed_target(name, robot)
                else:
                    robot.bus.disable_torque()
            except Exception:
                logger.exception("Failed to set teleop torque on arm %r (active=%s)", name, active)
                raise

    def set_teleop(self, enabled: bool, token: str, *, arm: str | None = None) -> dict[str, Any]:
        """Enable or disable browser teleop for one arm.

        ON: torque + commands only for ``arm`` (default: current teleop arm / follower).
        Other arms stay torque-off. OFF: all arms torque-off.
        """
        if self._estop.is_set():
            return {"ok": False, "error": "estop_active", "teleop": False, "teleop_arm": None}
        if self._calib_mode:
            return {"ok": False, "error": "calib_mode_active", "teleop": False, "teleop_arm": None}
        if not self.claim_client(token):
            return {
                "ok": False,
                "error": "another_client_connected",
                "teleop": self._teleop_enabled,
                "teleop_arm": self._teleop_arm,
            }
        with self._lock:
            # Hand mode: teleop ON/OFF only gates follower follow (leader stays soft).
            if self._control_mode == MODE_LEADER_FOLLOW:
                follower = self.robots.get(ARM_FOLLOWER)
                if follower is None:
                    return {"ok": False, "error": "follower_not_connected"}
                try:
                    if enabled:
                        follower.bus.enable_torque()
                        self._seed_target(ARM_FOLLOWER, follower)
                        self._teleop_enabled = True
                        self._teleop_arm = ARM_FOLLOWER
                        logger.info("Leader-follow: follower tracking ON")
                    else:
                        follower.bus.disable_torque()
                        self._teleop_enabled = False
                        self._teleop_arm = None
                        logger.info("Leader-follow: follower tracking OFF")
                except Exception as exc:
                    return {"ok": False, "error": f"leader_follow_torque_failed:{exc}"}
                return {
                    "ok": True,
                    "teleop": self._teleop_enabled,
                    "teleop_arm": self._teleop_arm,
                    "control_mode": self._control_mode,
                    "targets": {a: dict(t) for a, t in self._targets.items()},
                }

            if enabled:
                target = arm or self._teleop_arm or next(iter(self.robots), None)
                if target not in self.robots:
                    return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self.robots)}
                self._homing_arms.clear()
                self._teleop_arm = target
                self._teleop_enabled = True
                try:
                    self._apply_teleop_torque_unlocked()
                except Exception as exc:
                    self._teleop_enabled = False
                    return {"ok": False, "error": f"teleop_enable_failed:{exc}"}
                logger.info("Browser teleop enabled on arm %r (others soft)", target)
            else:
                self._teleop_enabled = False
                self._teleop_arm = None
                try:
                    self._apply_teleop_torque_unlocked()
                except Exception as exc:
                    return {"ok": False, "error": f"teleop_disable_failed:{exc}"}
                logger.info("Browser teleop disabled (all arms soft)")
            return {
                "ok": True,
                "teleop": self._teleop_enabled,
                "teleop_arm": self._teleop_arm,
                "control_mode": self._control_mode,
                "targets": {a: dict(t) for a, t in self._targets.items()},
            }

    @property
    def control_mode(self) -> str:
        """``browser`` or ``leader_follow``."""
        return self._control_mode

    @property
    def hand_teleop_available(self) -> bool:
        """True when yaml has a leader serial port for so101_leader hand mode."""
        return bool(self.config.leader_hand_port)

    def _disconnect_leader_hand_unlocked(self) -> None:
        """Drop the so101_leader device if connected. Caller holds ``self._lock``."""
        hand = self._leader_hand
        self._leader_hand = None
        if hand is None:
            return
        try:
            if getattr(hand, "is_connected", False):
                hand.disconnect()
            elif getattr(getattr(hand, "bus", None), "is_connected", False):
                hand.bus.disconnect()
        except Exception:
            logger.exception("Failed to disconnect so101_leader hand device")

    def _connect_leader_hand_unlocked(self) -> None:
        """Open so101_leader on the hand-teleop port. Caller holds ``self._lock``."""
        port = self.config.leader_hand_port
        hand_id = self.config.leader_hand_id or "my_leader"
        if not port:
            raise RuntimeError("leader_hand_port is not configured")
        cfg = SO101LeaderConfig(port=port, id=hand_id)
        hand = SO101Leader(cfg)
        try:
            hand.connect(calibrate=False)
        except Exception:
            try:
                if getattr(hand.bus, "is_connected", False):
                    hand.bus.disconnect()
            except Exception:
                logger.debug("Leader-hand bus cleanup failed", exc_info=True)
            raise
        if not hand.calibration:
            try:
                hand.disconnect()
            except Exception:
                logger.debug("Leader-hand disconnect after missing calib failed", exc_info=True)
            raise RuntimeError(
                f"No so101_leader calibration for id={hand_id!r}. Run once:\n"
                f"  lerobot-calibrate --teleop.type=so101_leader "
                f"--teleop.port={port} --teleop.id={hand_id}"
            )
        try:
            hand.disable_torque()
        except Exception:
            logger.exception("Failed to disable torque on so101_leader")
            try:
                hand.disconnect()
            except Exception:
                pass
            raise
        self._leader_hand = hand
        logger.info("so101_leader hand connected (id=%s port=%s)", hand_id, port)

    def _detach_leader_drive_unlocked(self) -> SO101Follower | None:
        """Remove browser-driven leader arm from ``robots`` (keeps cameras on follower)."""
        robot = self.robots.pop(ARM_LEADER, None)
        if robot is None:
            return None
        try:
            if getattr(robot.bus, "is_connected", False):
                robot.bus.disable_torque()
        except Exception:
            logger.debug("Leader-drive disable_torque failed", exc_info=True)
        try:
            if getattr(robot.bus, "is_connected", False):
                robot.bus.disconnect()
        except Exception:
            logger.exception("Failed disconnecting browser-driven leader arm")
        self._targets.pop(ARM_LEADER, None)
        return robot

    def _reattach_leader_drive_unlocked(self) -> None:
        """Reconnect leader port as so101_follower for browser drive."""
        cfg = self._leader_drive_cfg or self.config.arms.get(ARM_LEADER)
        if cfg is None:
            return
        if ARM_LEADER in self.robots:
            return
        robot = self._try_connect_robot(cfg)
        if not robot.calibration:
            try:
                robot.bus.disconnect()
            except Exception:
                pass
            raise RuntimeError(
                f"No calibration for arm {ARM_LEADER!r}. "
                f"lerobot-calibrate --robot.type=so101_follower "
                f"--robot.port={cfg.port} --robot.id={cfg.id or ARM_LEADER}"
            )
        self.robots[ARM_LEADER] = robot
        self._targets[ARM_LEADER] = {k: 0.0 for k in JOINT_KEYS}
        self._seed_target(ARM_LEADER, robot)
        self._apply_drive_profile(ARM_LEADER, robot)
        logger.info("Browser-driven leader arm reconnected (id=%s)", robot.id)

    def set_control_mode(self, mode: str, token: str) -> dict[str, Any]:
        """Switch between browser drive and classic leader→follower hand teleop.

        ``leader_follow`` detaches the browser-driven leader (if any), opens
        ``so101_leader`` on the same port, and streams its pose to the follower.
        """
        mode = str(mode or "").strip().lower()
        if mode not in {MODE_BROWSER, MODE_LEADER_FOLLOW}:
            return {"ok": False, "error": f"unknown_mode:{mode}"}
        if self._estop.is_set():
            return {"ok": False, "error": "estop_active", "control_mode": self._control_mode}
        if self._calib_mode:
            return {"ok": False, "error": "calib_mode_active", "control_mode": self._control_mode}
        if not self.claim_client(token):
            return {
                "ok": False,
                "error": "another_client_connected",
                "control_mode": self._control_mode,
            }
        with self._lock:
            if mode == self._control_mode:
                return self._control_mode_snapshot_unlocked(ok=True)
            if mode == MODE_LEADER_FOLLOW:
                if not self.config.leader_hand_port:
                    return {"ok": False, "error": "leader_hand_port_missing"}
                if ARM_FOLLOWER not in self.robots:
                    return {"ok": False, "error": "follower_not_connected"}
                self._homing_arms.clear()
                self._teleop_enabled = False
                self._teleop_arm = None
                try:
                    self._apply_teleop_torque_unlocked()
                except Exception as exc:
                    return {"ok": False, "error": f"torque_off_failed:{exc}"}
                self._detach_leader_drive_unlocked()
                try:
                    self._connect_leader_hand_unlocked()
                except Exception as exc:
                    # Best-effort restore browser leader drive.
                    try:
                        self._reattach_leader_drive_unlocked()
                    except Exception:
                        logger.exception("Failed restoring leader drive after hand connect error")
                    return {"ok": False, "error": f"leader_hand_connect_failed:{exc}"}
                follower = self.robots[ARM_FOLLOWER]
                try:
                    follower.bus.enable_torque()
                    self._seed_target(ARM_FOLLOWER, follower)
                except Exception as exc:
                    self._disconnect_leader_hand_unlocked()
                    try:
                        self._reattach_leader_drive_unlocked()
                    except Exception:
                        logger.exception("Failed restoring leader drive after follower torque error")
                    return {"ok": False, "error": f"follower_torque_failed:{exc}"}
                self._teleop_enabled = True
                self._teleop_arm = ARM_FOLLOWER
                self._control_mode = MODE_LEADER_FOLLOW
                logger.info("Control mode → leader_follow (hand teleop)")
                return self._control_mode_snapshot_unlocked(ok=True)

            # → browser
            self._teleop_enabled = False
            self._teleop_arm = None
            try:
                follower = self.robots.get(ARM_FOLLOWER)
                if follower is not None and getattr(follower.bus, "is_connected", False):
                    follower.bus.disable_torque()
            except Exception as exc:
                return {"ok": False, "error": f"follower_torque_off_failed:{exc}"}
            self._disconnect_leader_hand_unlocked()
            try:
                self._reattach_leader_drive_unlocked()
            except Exception as exc:
                return {"ok": False, "error": f"leader_drive_reconnect_failed:{exc}"}
            self._control_mode = MODE_BROWSER
            self._teleop_arm = ARM_FOLLOWER if ARM_FOLLOWER in self.robots else next(iter(self.robots), None)
            # Leave teleop OFF until the user presses arm ON (safer after mode swap).
            try:
                self._apply_teleop_torque_unlocked()
            except Exception as exc:
                return {"ok": False, "error": f"browser_torque_failed:{exc}"}
            logger.info("Control mode → browser")
            return self._control_mode_snapshot_unlocked(ok=True)

    def _control_mode_snapshot_unlocked(self, *, ok: bool) -> dict[str, Any]:
        """Shared response fields for mode switches."""
        return {
            "ok": ok,
            "control_mode": self._control_mode,
            "hand_teleop_available": self.hand_teleop_available,
            "teleop": self._teleop_enabled,
            "teleop_arm": self._teleop_arm,
            "arms": list(self.robots.keys()),
            "targets": {a: dict(t) for a, t in self._targets.items()},
        }

    @staticmethod
    def _release_bus_port(bus: Any) -> None:
        """Clear scservo ``is_using`` so the next TX is not stuck on COMM_PORT_BUSY.

        The Feetech SDK sets ``port_handler.is_using`` for the duration of a
        packet. If a prior sync_read/write is interrupted or overlaps, the flag
        stays True and every later ``writeTxRx`` returns ``Port is in use!``
        until something clears it — same recovery ``MotorsBus.disconnect`` uses.
        """
        port = getattr(bus, "port_handler", None)
        if port is None:
            return
        try:
            port.is_using = False
            if getattr(port, "is_open", False):
                port.clearPort()
        except Exception:
            logger.debug("bus port release failed", exc_info=True)

    def _disable_all_torque_unlocked(self) -> str | None:
        """Drop torque on every connected arm. Caller holds ``self._lock``.

        Retries after releasing a stuck ``is_using`` flag (see
        :meth:`_release_bus_port`). Returns a failure string, or None on success.
        """
        failed: list[str] = []
        for name, robot in self.robots.items():
            if not getattr(robot.bus, "is_connected", False):
                continue
            last_exc: Exception | None = None
            for _attempt in range(5):
                self._release_bus_port(robot.bus)
                try:
                    robot.bus.disable_torque(num_retry=2)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    self._release_bus_port(robot.bus)
                    time.sleep(0.08)
            if last_exc is not None:
                logger.error(
                    "disable_torque failed on arm %r",
                    name,
                    exc_info=last_exc,
                )
                failed.append(name)
        if failed:
            return "disable_torque_failed:" + ",".join(failed)
        return None

    def save_home(self, *, arm: str | None = None, token: str) -> dict[str, Any]:
        """Capture measured joints as the nest pose for one arm or all arms."""
        if self._estop.is_set():
            return {"ok": False, "error": "estop_active"}
        if self._calib_mode:
            return {"ok": False, "error": "calib_mode_active"}
        if not self.claim_client(token):
            return {"ok": False, "error": "another_client_connected"}

        names = [arm] if arm else list(self.robots)
        if arm and arm not in self.robots:
            return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self.robots)}

        captured: dict[str, dict[str, float]] = {}
        with self._lock:
            for name in names:
                robot = self.robots.get(name)
                if robot is None or not getattr(robot.bus, "is_connected", False):
                    return {"ok": False, "error": f"arm_not_connected:{name}"}
                try:
                    positions = robot.bus.sync_read("Present_Position", list(JOINT_KEYS))
                except Exception as exc:
                    logger.exception("save_home read failed for %r", name)
                    return {"ok": False, "error": f"read_failed:{name}:{exc}"}
                joints = {
                    key: float(positions[key])
                    for key in JOINT_KEYS
                    if key in positions and isinstance(positions[key], (int, float))
                }
                clamped = clamp_joints(joints)
                if len(clamped) < len(JOINT_KEYS):
                    return {"ok": False, "error": f"incomplete_joints:{name}"}
                captured[name] = clamped

        result = save_home_file(captured, path=self._home_path, merge=True)
        result["saved_arms"] = sorted(captured)
        return result

    def go_home(self, *, arm: str | None = None, token: str) -> dict[str, Any]:
        """Move one or all arms to the saved nest pose (gradual via max_relative_target).

        Enables torque on the homing arms and lets the control loop approach the
        targets. Falls back to 0° / gripper 50 when no file exists for an arm.
        """
        if self._estop.is_set():
            return {"ok": False, "error": "estop_active"}
        if self._control_mode == MODE_LEADER_FOLLOW:
            return {"ok": False, "error": "leader_follow_active"}
        if self._calib_mode:
            return {"ok": False, "error": "calib_mode_active"}
        if not self.claim_client(token):
            return {"ok": False, "error": "another_client_connected"}

        names = [arm] if arm else list(self.robots)
        if arm and arm not in self.robots:
            return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self.robots)}

        targets: dict[str, dict[str, float]] = {}
        sources: dict[str, str] = {}
        for name in names:
            joints, from_file = joints_for_arm(name, path=self._home_path)
            targets[name] = joints
            sources[name] = "file" if from_file else "default"

        with self._lock:
            self._teleop_enabled = False
            self._teleop_arm = None
            self._homing_arms = set(names)
            for name in names:
                robot = self.robots.get(name)
                if robot is None or not getattr(robot.bus, "is_connected", False):
                    self._homing_arms.discard(name)
                    continue
                try:
                    robot.bus.enable_torque()
                except Exception:
                    logger.exception("go_home enable_torque failed for %r", name)
                    self._homing_arms.discard(name)
                    continue
                self._targets[name] = dict(targets[name])

            if not self._homing_arms:
                return {"ok": False, "error": "no_arms_homing", "sources": sources}

            return {
                "ok": True,
                "homing": sorted(self._homing_arms),
                "targets": {n: dict(targets[n]) for n in self._homing_arms},
                "sources": sources,
                "path": str(self._home_path),
            }

    def get_home(self) -> dict[str, Any]:
        """Return saved nest poses and which configured arms have a file entry."""
        data = load_home_file(self._home_path)
        configured = list(self.config.arms)
        arms_file = data.get("arms") or {}
        return {
            "ok": True,
            "path": data.get("path"),
            "updated_at": data.get("updated_at"),
            "arms": arms_file,
            "configured": configured,
            "has_home": {name: name in arms_file for name in configured},
            "default": default_joints(),
            "homing": sorted(self._homing_arms),
        }

    def trigger_estop(self) -> dict[str, Any]:
        """Freeze targets and disable motor torque on all arms.

        ESTOP flag is always set (control loop stops writing). Torque disable is
        best-effort; failures are returned as ``warning`` so the UI still shows
        ESTOP active and can offer resume.
        """
        self._estop.set()
        with self._lock:
            # ESTOP implies teleop off until cleared and the operator turns it on again.
            self._teleop_enabled = False
            self._teleop_arm = None
            self._homing_arms.clear()
            err = self._disable_all_torque_unlocked()
            hand_err = self._disable_leader_hand_torque_unlocked()
            warning = ", ".join(x for x in (err, hand_err) if x)
            result: dict[str, Any] = {
                "ok": True,
                "estop": True,
                "teleop": False,
                "teleop_arm": None,
                "control_mode": self._control_mode,
                "arms": list(self.robots),
            }
            if warning:
                result["warning"] = warning
                logger.warning("ESTOP set; torque disable incomplete: %s", warning)
            return result

    def clear_estop(self) -> dict[str, Any]:
        """Clear ESTOP so the operator can resume (teleop stays off until ON).

        Torque disable is best-effort. We always clear the ESTOP flag — leaving
        it stuck on when a flaky arm bus fails ``disable_torque`` blocked resume
        (UI Clear / 再開 returned 409 forever).
        """
        with self._lock:
            self._teleop_enabled = False
            self._teleop_arm = None
            err = self._disable_all_torque_unlocked()
            hand_err = self._disable_leader_hand_torque_unlocked()
            self._estop.clear()
            warning = ", ".join(x for x in (err, hand_err) if x)
            result: dict[str, Any] = {
                "ok": True,
                "estop": False,
                "teleop": False,
                "teleop_arm": None,
                "control_mode": self._control_mode,
                "targets": {a: dict(t) for a, t in self._targets.items()},
            }
            if warning:
                result["warning"] = warning
                logger.warning("ESTOP cleared; torque disable incomplete: %s", warning)
            return result

    def _disable_leader_hand_torque_unlocked(self) -> str | None:
        """Best-effort torque off for so101_leader. Caller holds lock."""
        hand = self._leader_hand
        if hand is None or not getattr(hand, "is_connected", False):
            return None
        try:
            hand.disable_torque()
            return None
        except Exception as exc:
            self._release_bus_port(hand.bus)
            try:
                hand.disable_torque()
                return None
            except Exception as exc2:
                return f"leader_hand:{exc2 or exc}"

    def get_state(self) -> dict[str, Any]:
        """JSON-serializable snapshot for the UI."""
        with self._lock:
            joints_by_arm: dict[str, dict[str, float]] = {}
            if not self._estop.is_set():
                for name, robot in self.robots.items():
                    arm_joints: dict[str, float] = {}
                    try:
                        bus = robot.bus
                        if getattr(bus, "is_connected", False):
                            # Joints only — get_observation also pulls cameras and
                            # would hold this lock (and the serial bus) too long.
                            positions = bus.sync_read("Present_Position", list(JOINT_KEYS))
                            for key in JOINT_KEYS:
                                if key in positions and isinstance(positions[key], (int, float)):
                                    arm_joints[key] = float(positions[key])
                    except Exception:
                        logger.debug("joint sync_read failed for %r", name, exc_info=True)
                        self._release_bus_port(robot.bus)
                    joints_by_arm[name] = arm_joints
                # Hand-teleop leader pose (so101_leader), shown as "leader" in the UI.
                hand = self._leader_hand
                if hand is not None and getattr(hand, "is_connected", False):
                    try:
                        raw = hand.get_action()
                        hand_joints: dict[str, float] = {}
                        for key in JOINT_KEYS:
                            val = raw.get(f"{key}.pos")
                            if isinstance(val, (int, float)):
                                hand_joints[key] = float(val)
                        joints_by_arm[ARM_LEADER] = hand_joints
                    except Exception:
                        logger.debug("leader hand joint read failed", exc_info=True)
                        self._release_bus_port(hand.bus)
            home_meta = load_home_file(self._home_path)
            home_arms = home_meta.get("arms") or {}
            arm_names = list(self.robots) if self.robots else list(self.config.arms)
            if self._control_mode == MODE_LEADER_FOLLOW and ARM_LEADER not in arm_names:
                arm_names = [*arm_names, ARM_LEADER]
            profiles = {name: self.drive_profile(name).to_public_dict() for name in arm_names if name in self.robots}
            return {
                "ok": True,
                "connected": self._connected,
                "estop": self._estop.is_set(),
                "teleop": self._teleop_enabled,
                "teleop_arm": self._teleop_arm,
                "control_mode": self._control_mode,
                "hand_teleop_available": self.hand_teleop_available,
                "calib_mode": self._calib_mode,
                "calib_arm": self._calib_arm,
                "arms": arm_names,
                "cameras": self.camera_names,
                "targets": {a: dict(t) for a, t in self._targets.items()},
                "joints": joints_by_arm,
                # Convenience: active defaults for single-arm UI clients.
                "target": dict(self._targets.get(ARM_FOLLOWER, next(iter(self._targets.values()), {}))),
                "client_locked": self._client_token is not None,
                "homing": sorted(self._homing_arms),
                "has_home": {name: name in home_arms for name in self.robots},
                "home_path": str(self._home_path),
                "drive_profiles": profiles,
                **self._rate_fields(),
            }

    def get_jpeg(self, cam_name: str, *, quality: int = 70) -> bytes | None:
        """Encode the latest frame for a camera as JPEG bytes."""
        with self._lock:
            frame = self._frames.get(cam_name)
            if frame is None:
                return None
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if not ok:
                return None
            return buf.tobytes()

    def _rate_fields(self) -> dict[str, object]:
        """Active expert, live period, and the last center-camera scene."""
        snap = self._router.snapshot()
        # Hand teleop bypasses RateRouter step/hz caps (matches lerobot-teleoperate feel).
        if self._control_mode == MODE_LEADER_FOLLOW:
            return {
                "rate_mode": "leader_follow",
                "control_hz": self._router.cruise_hz,
                "step_limit": None,
                "rate_reason": "hand_teleop_uncapped",
                "scene": snap["scene"],
            }
        return {
            "rate_mode": snap["rate_mode"],
            "control_hz": snap["control_hz"],
            "step_limit": snap["step_limit"],
            "rate_reason": snap["reason"],
            "scene": snap["scene"],
        }

    def _motor_period(self) -> float:
        """Calibration / leader-follow stay on cruise Hz. Browser teleop follows the router."""
        with self._lock:
            calib = self._calib_mode
            hand = self._control_mode == MODE_LEADER_FOLLOW
        if calib or hand:
            return 1.0 / self._router.cruise_hz
        return self._router.current_period()

    def _control_loop(self) -> None:
        """Send motor targets. Camera reads and the rate router run on other threads."""
        while not self._stop_control.is_set():
            t0 = time.monotonic()
            try:
                self._tick_motors()
            except Exception:
                logger.exception("Control loop tick failed")
            elapsed = time.monotonic() - t0
            self._stop_control.wait(max(0.0, self._motor_period() - elapsed))

    def _camera_loop(self) -> None:
        """Refresh MJPEG buffers without stretching the motor period."""
        period = 1.0 / 20.0
        while not self._stop_control.is_set():
            t0 = time.monotonic()
            try:
                self._read_cameras()
            except Exception:
                logger.exception("Camera loop failed")
            elapsed = time.monotonic() - t0
            self._stop_control.wait(max(0.0, period - elapsed))

    def _watch_loop(self) -> None:
        """Look at the center camera at about 5 Hz and update the rate router."""
        period = 1.0 / 5.0
        while not self._stop_control.is_set():
            t0 = time.monotonic()
            try:
                self._watch_once(t0)
            except Exception:
                logger.exception("Center watch failed")
            elapsed = time.monotonic() - t0
            self._stop_control.wait(max(0.0, period - elapsed))

    def _command_motion(self, targets: dict[str, dict[str, float]], now: float) -> str:
        """How fast joint targets are changing since the previous look."""
        previous = self._cmd_prev
        previous_t = self._cmd_prev_t
        self._cmd_prev = {arm: dict(joints) for arm, joints in targets.items()}
        self._cmd_prev_t = now
        if previous is None or previous_t is None:
            return "still"
        max_delta = 0.0
        for arm, joints in targets.items():
            before = previous.get(arm, {})
            for key, value in joints.items():
                max_delta = max(max_delta, abs(float(value) - float(before.get(key, value))))
        return classify_command(max_delta, now - previous_t)

    def _watch_once(self, now: float) -> None:
        with self._lock:
            frame = self._frames.get(CENTER_CAMERA)
            frame_copy = None if frame is None else frame.copy()
            targets = {arm: dict(joints) for arm, joints in self._targets.items()}
        command = self._command_motion(targets, now)
        scene = self._watch.observe(frame_copy, command_motion=command)
        before = str(self._router.snapshot()["rate_mode"])
        self._router.update(
            scene,
            command_motion=command,
            joint_near_edge=targets_near_edge(targets),
        )
        after = self._router.snapshot()
        if after["rate_mode"] != before:
            logger.info(
                "Rate mode %s hz=%s step=%s reason=%s",
                after["rate_mode"],
                after["control_hz"],
                after["step_limit"],
                after["reason"],
            )

    def _tick_motors(self) -> None:
        """Write joint targets. The bus stays inside the session lock so ESTOP can cut torque."""
        step = self._router.step_limit()
        with self._lock:
            if self._calib_mode:
                self._tick_calibration()
                return
            if self._estop.is_set():
                return
            if self._homing_arms:
                self._tick_homing_unlocked(step)
                return
            if self._control_mode == MODE_LEADER_FOLLOW:
                self._tick_leader_follow_unlocked(step)
                return
            if not self._teleop_enabled or not self._teleop_arm:
                return
            name = self._teleop_arm
            robot = self.robots.get(name)
            if robot is None or not getattr(robot.bus, "is_connected", False):
                return
            action = {f"{k}.pos": float(v) for k, v in self._targets[name].items()}
            robot.config.max_relative_target = self._step_for_arm(name, step)
            try:
                robot.send_action(action)
            except Exception:
                logger.debug("send_action failed for %r", name, exc_info=True)

    def _tick_leader_follow_unlocked(self, step: float) -> None:
        """Copy so101_leader pose onto the follower target and send_action."""
        hand = self._leader_hand
        robot = self.robots.get(ARM_FOLLOWER)
        if hand is None or robot is None:
            return
        if not getattr(hand, "is_connected", False):
            return
        if not getattr(robot.bus, "is_connected", False):
            return
        if not self._teleop_enabled:
            return
        try:
            raw = hand.get_action()
        except Exception:
            logger.debug("so101_leader get_action failed", exc_info=True)
            self._release_bus_port(hand.bus)
            return
        clamped: dict[str, float] = {}
        for key in JOINT_KEYS:
            val = raw.get(f"{key}.pos")
            if isinstance(val, (int, float)):
                clamped[key] = float(val)
        if not clamped:
            return
        clamped = clamp_joints(clamped)
        self._targets[ARM_FOLLOWER].update(clamped)
        action = {f"{k}.pos": float(v) for k, v in self._targets[ARM_FOLLOWER].items()}
        robot.config.max_relative_target = self._step_for_arm(ARM_FOLLOWER, step)
        try:
            robot.send_action(action)
        except Exception:
            logger.debug("leader_follow send_action failed", exc_info=True)
            self._release_bus_port(robot.bus)

    def _tick_homing_unlocked(self, step: float) -> None:
        """Drive every arm in ``_homing_arms`` toward its nest target; clear when close."""
        done: list[str] = []
        for name in list(self._homing_arms):
            robot = self.robots.get(name)
            if robot is None or not getattr(robot.bus, "is_connected", False):
                done.append(name)
                continue
            target = self._targets.get(name) or {}
            action = {f"{k}.pos": float(v) for k, v in target.items()}
            robot.config.max_relative_target = self._step_for_arm(name, step, homing=True)
            try:
                robot.send_action(action)
            except Exception:
                logger.debug("homing send_action failed for %r", name, exc_info=True)
                continue
            try:
                positions = robot.bus.sync_read("Present_Position", list(JOINT_KEYS))
                current = {
                    key: float(positions[key])
                    for key in JOINT_KEYS
                    if key in positions and isinstance(positions[key], (int, float))
                }
                if near_home(current, target, tol_deg=2.5):
                    done.append(name)
            except Exception:
                logger.debug("homing proximity read failed for %r", name, exc_info=True)
        for name in done:
            self._homing_arms.discard(name)
            logger.info("Homing complete for arm %r (holding nest pose)", name)

    def _read_cameras(self) -> None:
        """Store the latest frame from each camera on the host arm."""
        with self._lock:
            host = self.robots.get(self.config.camera_host_arm) or next(iter(self.robots.values()), None)
            if host is None:
                return
            cameras = list(host.cameras.items())
        updates: dict[str, np.ndarray] = {}
        for name, cam in cameras:
            _store_camera_frames(updates, name, cam, read_color=self._read_one_camera)
        if not updates:
            return
        with self._lock:
            self._frames.update(updates)

    @staticmethod
    def _read_one_camera(name: str, cam: _FrameCamera) -> np.ndarray | None:
        # Color-only path; depth is handled separately via read_colorized_depth.
        if getattr(cam, "use_rgb", True) is False:
            return None
        try:
            frame = cam.async_read(timeout_ms=200)
            if frame is not None:
                return frame
        except Exception:
            try:
                frame = cam.read()
                if frame is not None:
                    return frame
            except Exception:
                logger.debug("Camera %s read failed", name, exc_info=True)
        return None


class CameraOnlySession:
    """Cameras + MJPEG only — no USB serial / SO-101 (for Quest bridge teleop)."""

    cameras_only = True

    def __init__(self, config: WebRemoteConfig) -> None:
        self.config = config
        self.robots: dict[str, Any] = {}
        self._cameras: dict[str, Any] = {}
        self._frames: dict[str, np.ndarray] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._camera_thread: threading.Thread | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def arm_names(self) -> list[str]:
        return []

    @property
    def camera_names(self) -> list[str]:
        cams = self._cameras or self.config.cameras
        return _camera_names_with_depth(cams)

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            if not self.config.cameras:
                raise RuntimeError("No cameras configured in yaml")
            from lerobot.cameras.utils import make_cameras_from_configs

            for name, cam in make_cameras_from_configs(self.config.cameras).items():
                try:
                    cam.connect()
                    self._cameras[name] = cam
                    logger.info("Camera-only: connected %r", name)
                except Exception as exc:
                    logger.warning("Camera-only: skipping %r: %s", name, exc)
            if not self._cameras:
                raise RuntimeError("No cameras could be opened")
            self._connected = True
            self._stop.clear()
            self._camera_thread = threading.Thread(
                target=self._camera_loop, name="cameras-only", daemon=True
            )
            self._camera_thread.start()
            logger.info("Camera-only ready: %s", self.camera_names)

    def disconnect(self) -> None:
        self._stop.set()
        if self._camera_thread and self._camera_thread.is_alive():
            self._camera_thread.join(timeout=2.0)
        with self._lock:
            for name, cam in list(self._cameras.items()):
                try:
                    if hasattr(cam, "disconnect"):
                        cam.disconnect()
                except Exception:
                    logger.debug("camera disconnect %s failed", name, exc_info=True)
            self._cameras.clear()
            self._frames.clear()
            self._connected = False

    def get_jpeg(self, cam_name: str, *, quality: int = 70) -> bytes | None:
        with self._lock:
            frame = self._frames.get(cam_name)
            if frame is None:
                return None
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if not ok:
                return None
            return buf.tobytes()

    def get_state(self) -> dict[str, Any]:
        return {
            "ok": True,
            "connected": self._connected,
            "cameras_only": True,
            "arms": [],
            "cameras": self.camera_names,
            "estop": False,
            "teleop": False,
        }

    def _camera_loop(self) -> None:
        period = 1.0 / 20.0
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                with self._lock:
                    items = list(self._cameras.items())
                updates: dict[str, np.ndarray] = {}
                for name, cam in items:
                    _store_camera_frames(
                        updates, name, cam, read_color=RobotSession._read_one_camera
                    )
                if updates:
                    with self._lock:
                        self._frames.update(updates)
            except Exception:
                logger.exception("Camera-only loop failed")
            elapsed = time.monotonic() - t0
            self._stop.wait(max(0.0, period - elapsed))
