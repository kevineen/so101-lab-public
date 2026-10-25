"""Browser-driven per-motor calibration for RobotSession.

RobotSession のキャリブレーション機能（手動ジョグ・レンジ記録・ドラフト編集・
保存/取消）を :class:`CalibrationMixin` として分離したもの。状態
（``_calib_*``）は RobotSession.__init__ が持つ。

実行時の注意: キャリブ中はトルク制御が変わる。実機での動作確認を経て
本番運用に載せること（docs/03_web_remote.md）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from lerobot.motors.motors_bus import MotorCalibration
from lerobot.robots.so_follower import SO101Follower

from .config import JOINT_KEYS

logger = logging.getLogger(__name__)

# wrist_roll is continuous; official calibrate fixes encoder range to full 12-bit.
FULL_TURN_MOTORS = frozenset({"wrist_roll"})


class CalibrationMixin:
    """Calibration state machine methods mixed into RobotSession.

    Expects the host class to provide: ``_lock``, ``robots``, ``_estop``,
    ``claim_client``, ``_targets``, and the ``_calib_*`` attributes that
    RobotSession.__init__ initializes.
    """

    @staticmethod
    def _calibration_as_dict(calibration: dict[str, MotorCalibration]) -> dict[str, dict[str, int]]:
        """Serialize MotorCalibration objects for JSON / draft editing."""
        out: dict[str, dict[str, int]] = {}
        for name, cal in calibration.items():
            raw = asdict(cal)
            out[name] = {
                "id": int(raw["id"]),
                "drive_mode": int(raw["drive_mode"]),
                "homing_offset": int(raw["homing_offset"]),
                "range_min": int(raw["range_min"]),
                "range_max": int(raw["range_max"]),
            }
        return out

    @staticmethod
    def _dict_to_calibration(data: dict[str, dict[str, Any]]) -> dict[str, MotorCalibration]:
        """Build MotorCalibration map from JSON-like dicts."""
        return {
            name: MotorCalibration(
                id=int(vals["id"]),
                drive_mode=int(vals.get("drive_mode", 0)),
                homing_offset=int(vals["homing_offset"]),
                range_min=int(vals["range_min"]),
                range_max=int(vals["range_max"]),
            )
            for name, vals in data.items()
        }

    def _require_calib_client(self, token: str) -> dict[str, Any] | None:
        """Return an error dict if not in calib mode or token mismatch; else None."""
        if not self._calib_mode or self._calib_arm is None:
            return {"ok": False, "error": "not_in_calib_mode"}
        if not self.claim_client(token):
            return {"ok": False, "error": "another_client_connected"}
        return None

    def get_calibration(self, arm: str) -> dict[str, Any]:
        """Return saved (or draft) calibration plus live raw encoder positions."""
        with self._lock:
            if arm not in self.robots:
                return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self.robots)}
            robot = self.robots[arm]
            if self._calib_mode and self._calib_arm == arm and self._calib_draft:
                draft = {k: dict(v) for k, v in self._calib_draft.items()}
            else:
                draft = self._calibration_as_dict(robot.calibration or {})
            path = str(getattr(robot, "calibration_fpath", "")) or None
            return {
                "ok": True,
                "arm": arm,
                "robot_id": robot.id,
                "path": path,
                "motors": list(JOINT_KEYS),
                "full_turn_motors": sorted(FULL_TURN_MOTORS),
                "calibration": draft,
                "raw": dict(self._calib_raw) if self._calib_mode and self._calib_arm == arm else {},
                "recording": sorted(self._calib_recording),
                "recorded_mins": dict(self._calib_mins),
                "recorded_maxes": dict(self._calib_maxes),
                "calib_mode": self._calib_mode and self._calib_arm == arm,
                "drive": self._calib_drive if self._calib_mode and self._calib_arm == arm else False,
                "goals": dict(self._calib_goals) if self._calib_mode and self._calib_arm == arm else {},
            }

    def _calib_motor_max_res(self, robot: SO101Follower, motor: str) -> int:
        """Return encoder max (resolution-1) for a motor model."""
        model = robot.bus._get_motor_model(motor)
        return int(robot.bus.model_resolution_table[model] - 1)

    def _calib_open_position_limits(self, robot: SO101Follower, motors: list[str]) -> None:
        """Open Min/Max_Position_Limit so jog can explore beyond the saved range."""
        bus = robot.bus
        for motor in motors:
            if motor not in bus.motors:
                continue
            max_res = self._calib_motor_max_res(robot, motor)
            bus.write("Min_Position_Limit", motor, 0, normalize=False)
            bus.write("Max_Position_Limit", motor, max_res, normalize=False)

    def _calib_disable_drive_unlocked(self, robot: SO101Follower) -> None:
        """Turn off powered jog and release torque (caller must hold lock)."""
        if not self._calib_drive and not self._calib_goals:
            try:
                robot.bus.disable_torque()
            except Exception:
                logger.debug("disable_torque while clearing drive failed", exc_info=True)
            return
        try:
            robot.bus.disable_torque()
        except Exception:
            logger.exception("Failed to disable torque when leaving calib drive")
        self._calib_drive = False
        self._calib_goals.clear()

    def enter_calibration(self, arm: str, token: str) -> dict[str, Any]:
        """Disable torque on arm, pause teleop, load editable draft from disk/file."""
        if not self.claim_client(token):
            return {"ok": False, "error": "another_client_connected"}
        with self._lock:
            if arm not in self.robots:
                return {"ok": False, "error": f"unknown_arm:{arm}", "arms": list(self.robots)}
            if self._calib_mode:
                return {"ok": False, "error": "already_in_calib_mode", "arm": self._calib_arm}
            robot = self.robots[arm]
            if not robot.calibration:
                return {"ok": False, "error": "no_calibration_loaded"}
            self._estop.clear()
            self._calib_backup = {
                name: MotorCalibration(**asdict(cal)) for name, cal in robot.calibration.items()
            }
            self._calib_draft = self._calibration_as_dict(robot.calibration)
            self._calib_recording.clear()
            self._calib_mins.clear()
            self._calib_maxes.clear()
            self._calib_raw.clear()
            self._calib_drive = False
            self._calib_goals.clear()
            self._calib_arm = arm
            self._calib_mode = True
            try:
                robot.bus.disable_torque()
            except Exception as exc:
                self._calib_mode = False
                self._calib_arm = None
                logger.exception("Failed to disable torque for calibration")
                return {"ok": False, "error": f"disable_torque_failed:{exc}"}
            logger.info("Entered calibration mode for arm %r", arm)
            return self.get_calibration(arm)

    def calib_set_drive(self, enabled: bool, token: str) -> dict[str, Any]:
        """Enable or disable powered browser jog while remaining in calib mode.

        When enabled: open position limits, enable torque, and hold every joint at
        its present encoder so the arm does not collapse. Jog then nudges goals.
        When disabled: torque off again for hand movement.
        """
        err = self._require_calib_client(token)
        if err:
            return err
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            bus = robot.bus
            names = [m for m in JOINT_KEYS if m in bus.motors]
            if enabled:
                try:
                    # Unlock EEPROM-ish regs: disable torque briefly, open limits, then hold.
                    bus.disable_torque()
                    self._calib_open_position_limits(robot, names)
                    positions = bus.sync_read("Present_Position", names, normalize=False)
                    goals = {m: int(positions[m]) for m in names}
                    bus.enable_torque()
                    for motor, pos in goals.items():
                        bus.write("Goal_Position", motor, pos, normalize=False)
                    self._calib_goals = goals
                    self._calib_raw = dict(goals)
                    self._calib_drive = True
                except Exception as exc:
                    self._calib_drive = False
                    self._calib_goals.clear()
                    logger.exception("calib_set_drive(enable) failed")
                    try:
                        bus.disable_torque()
                    except Exception:
                        logger.debug("cleanup disable_torque failed", exc_info=True)
                    return {"ok": False, "error": f"drive_enable_failed:{exc}"}
            else:
                try:
                    self._calib_disable_drive_unlocked(robot)
                except Exception as exc:
                    logger.exception("calib_set_drive(disable) failed")
                    return {"ok": False, "error": f"drive_disable_failed:{exc}"}
            return {
                "ok": True,
                "drive": self._calib_drive,
                "goals": dict(self._calib_goals),
                "raw": dict(self._calib_raw),
                "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
            }

    def calib_jog(self, deltas: dict[str, int], token: str) -> dict[str, Any]:
        """Nudge selected motors by raw encoder deltas while calib drive is on."""
        err = self._require_calib_client(token)
        if err:
            return err
        if not deltas:
            return {"ok": False, "error": "no_deltas"}
        with self._lock:
            if not self._calib_drive:
                return {"ok": False, "error": "drive_not_enabled"}
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            bus = robot.bus
            applied: dict[str, int] = {}
            try:
                for motor, delta in deltas.items():
                    if motor not in JOINT_KEYS or motor not in bus.motors:
                        continue
                    try:
                        step = int(delta)
                    except (TypeError, ValueError):
                        continue
                    if step == 0:
                        continue
                    max_res = self._calib_motor_max_res(robot, motor)
                    if motor in self._calib_goals:
                        cur = int(self._calib_goals[motor])
                    else:
                        cur = int(bus.read("Present_Position", motor, normalize=False))
                    new_pos = max(0, min(max_res, cur + step))
                    bus.write("Goal_Position", motor, new_pos, normalize=False)
                    self._calib_goals[motor] = new_pos
                    applied[motor] = new_pos
                if applied:
                    # Refresh raw for the UI immediately after the write.
                    names = list(applied.keys())
                    positions = bus.sync_read("Present_Position", names, normalize=False)
                    for motor in names:
                        self._calib_raw[motor] = int(positions[motor])
            except Exception as exc:
                logger.exception("calib_jog failed")
                return {"ok": False, "error": f"jog_failed:{exc}"}
            if not applied:
                return {"ok": False, "error": "no_valid_motors"}
            return {
                "ok": True,
                "drive": True,
                "goals": dict(self._calib_goals),
                "applied": applied,
                "raw": dict(self._calib_raw),
                "recording": sorted(self._calib_recording),
                "recorded_mins": dict(self._calib_mins),
                "recorded_maxes": dict(self._calib_maxes),
                "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
            }

    def calib_set_midpoint(self, motors: list[str], token: str) -> dict[str, Any]:
        """Set half-turn homing so current pose is mid-range for selected motors."""
        err = self._require_calib_client(token)
        if err:
            return err
        motors = [m for m in motors if m in JOINT_KEYS]
        if not motors:
            return {"ok": False, "error": "no_valid_motors"}
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            bus = robot.bus
            # Homing / limit writes need unlocked EEPROM; leave drive off afterward.
            if self._calib_drive:
                self._calib_disable_drive_unlocked(robot)
            try:
                for motor in motors:
                    model = bus._get_motor_model(motor)
                    max_res = bus.model_resolution_table[model] - 1
                    bus.write("Homing_Offset", motor, 0, normalize=False)
                    bus.write("Min_Position_Limit", motor, 0, normalize=False)
                    bus.write("Max_Position_Limit", motor, max_res, normalize=False)
                positions = bus.sync_read("Present_Position", motors, normalize=False)
                offsets = bus._get_half_turn_homings(positions)
                for motor, offset in offsets.items():
                    bus.write("Homing_Offset", motor, int(offset))
                    mid = bus.motors[motor]
                    draft = self._calib_draft.setdefault(
                        motor,
                        {
                            "id": int(mid.id),
                            "drive_mode": 0,
                            "homing_offset": 0,
                            "range_min": 0,
                            "range_max": 4095,
                        },
                    )
                    draft["homing_offset"] = int(offset)
                    draft["id"] = int(mid.id)
            except Exception as exc:
                logger.exception("calib_set_midpoint failed")
                return {"ok": False, "error": f"set_midpoint_failed:{exc}"}
            return {
                "ok": True,
                "offsets": {m: int(offsets[m]) for m in motors},
                "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
            }

    def calib_start_range(self, motors: list[str], token: str) -> dict[str, Any]:
        """Start accumulating raw min/max while the user moves joints by hand."""
        err = self._require_calib_client(token)
        if err:
            return err
        motors = [m for m in motors if m in JOINT_KEYS]
        if not motors:
            return {"ok": False, "error": "no_valid_motors"}
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            try:
                positions = robot.bus.sync_read("Present_Position", motors, normalize=False)
            except Exception as exc:
                return {"ok": False, "error": f"read_failed:{exc}"}
            for motor in motors:
                if motor in FULL_TURN_MOTORS:
                    continue
                pos = int(positions[motor])
                self._calib_mins[motor] = pos
                self._calib_maxes[motor] = pos
            self._calib_recording = {m for m in motors if m not in FULL_TURN_MOTORS}
            return {
                "ok": True,
                "recording": sorted(self._calib_recording),
                "recorded_mins": dict(self._calib_mins),
                "recorded_maxes": dict(self._calib_maxes),
            }

    def calib_stop_range(self, token: str) -> dict[str, Any]:
        """Stop range recording and write mins/maxes into the draft calibration."""
        err = self._require_calib_client(token)
        if err:
            return err
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            recording = list(self._calib_recording)
            self._calib_recording.clear()
            for motor in recording:
                lo = self._calib_mins.get(motor)
                hi = self._calib_maxes.get(motor)
                if lo is None or hi is None or lo >= hi:
                    return {
                        "ok": False,
                        "error": f"invalid_range:{motor}",
                        "recorded_mins": dict(self._calib_mins),
                        "recorded_maxes": dict(self._calib_maxes),
                    }
                m = robot.bus.motors[motor]
                draft = self._calib_draft.setdefault(
                    motor,
                    {
                        "id": int(m.id),
                        "drive_mode": 0,
                        "homing_offset": 0,
                        "range_min": lo,
                        "range_max": hi,
                    },
                )
                draft["range_min"] = int(lo)
                draft["range_max"] = int(hi)
                draft["id"] = int(m.id)
            for motor in FULL_TURN_MOTORS:
                if motor in robot.bus.motors:
                    m = robot.bus.motors[motor]
                    draft = self._calib_draft.setdefault(
                        motor,
                        {
                            "id": int(m.id),
                            "drive_mode": 0,
                            "homing_offset": int(self._calib_draft.get(motor, {}).get("homing_offset", 0)),
                            "range_min": 0,
                            "range_max": 4095,
                        },
                    )
                    draft["range_min"] = 0
                    draft["range_max"] = 4095
                    draft["id"] = int(m.id)
            return {
                "ok": True,
                "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
                "recorded_mins": dict(self._calib_mins),
                "recorded_maxes": dict(self._calib_maxes),
            }

    def calib_update_draft(self, motors: dict[str, dict[str, Any]], token: str) -> dict[str, Any]:
        """Manually edit draft homing_offset / range_min / range_max for selected motors."""
        err = self._require_calib_client(token)
        if err:
            return err
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            for name, vals in motors.items():
                if name not in JOINT_KEYS or name not in robot.bus.motors:
                    continue
                m = robot.bus.motors[name]
                draft = self._calib_draft.setdefault(
                    name,
                    {
                        "id": int(m.id),
                        "drive_mode": 0,
                        "homing_offset": 0,
                        "range_min": 0,
                        "range_max": 4095,
                    },
                )
                if "homing_offset" in vals:
                    draft["homing_offset"] = int(vals["homing_offset"])
                if "range_min" in vals:
                    draft["range_min"] = int(vals["range_min"])
                if "range_max" in vals:
                    draft["range_max"] = int(vals["range_max"])
                if draft["range_min"] >= draft["range_max"] and name not in FULL_TURN_MOTORS:
                    return {
                        "ok": False,
                        "error": f"invalid_range:{name}",
                        "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
                    }
                draft["id"] = int(m.id)
            return {"ok": True, "calibration": {k: dict(v) for k, v in self._calib_draft.items()}}

    def calib_capture_endpoint(self, motors: list[str], endpoint: str, token: str) -> dict[str, Any]:
        """Set draft range_min or range_max from the current raw encoder for each motor."""
        err = self._require_calib_client(token)
        if err:
            return err
        if endpoint not in ("min", "max"):
            return {"ok": False, "error": "endpoint_must_be_min_or_max"}
        motors = [m for m in motors if m in JOINT_KEYS and m not in FULL_TURN_MOTORS]
        if not motors:
            return {"ok": False, "error": "no_valid_motors"}
        with self._lock:
            assert self._calib_arm is not None
            robot = self.robots[self._calib_arm]
            try:
                positions = robot.bus.sync_read("Present_Position", motors, normalize=False)
            except Exception as exc:
                return {"ok": False, "error": f"read_failed:{exc}"}
            for motor in motors:
                pos = int(positions[motor])
                self._calib_raw[motor] = pos
                m = robot.bus.motors[motor]
                draft = self._calib_draft.setdefault(
                    motor,
                    {
                        "id": int(m.id),
                        "drive_mode": 0,
                        "homing_offset": 0,
                        "range_min": pos,
                        "range_max": pos + 1,
                    },
                )
                if endpoint == "min":
                    draft["range_min"] = pos
                    if draft["range_max"] <= pos:
                        draft["range_max"] = pos + 1
                else:
                    draft["range_max"] = pos
                    if draft["range_min"] >= pos:
                        draft["range_min"] = max(0, pos - 1)
                draft["id"] = int(m.id)
            return {
                "ok": True,
                "endpoint": endpoint,
                "raw": {m: int(positions[m]) for m in motors},
                "calibration": {k: dict(v) for k, v in self._calib_draft.items()},
            }

    def save_calibration(self, token: str) -> dict[str, Any]:
        """Write draft to motors + JSON file, re-enable torque, exit calib mode."""
        err = self._require_calib_client(token)
        if err:
            return err
        with self._lock:
            assert self._calib_arm is not None
            arm = self._calib_arm
            robot = self.robots[arm]
            missing = [m for m in JOINT_KEYS if m not in self._calib_draft]
            if missing:
                return {"ok": False, "error": f"incomplete_draft:{','.join(missing)}"}
            for name, vals in self._calib_draft.items():
                if name in FULL_TURN_MOTORS:
                    vals["range_min"] = 0
                    vals["range_max"] = 4095
                elif int(vals["range_min"]) >= int(vals["range_max"]):
                    return {"ok": False, "error": f"invalid_range:{name}"}
            try:
                # Unlock before writing calibration EEPROM registers.
                if self._calib_drive:
                    self._calib_disable_drive_unlocked(robot)
                else:
                    robot.bus.disable_torque()
                cal = self._dict_to_calibration(self._calib_draft)
                robot.calibration = cal
                robot.bus.write_calibration(cal)
                robot._save_calibration()
                robot.bus.enable_torque()
                self._seed_target(arm, robot)
            except Exception as exc:
                logger.exception("save_calibration failed")
                return {"ok": False, "error": f"save_failed:{exc}"}
            path = str(getattr(robot, "calibration_fpath", ""))
            self._calib_mode = False
            self._calib_arm = None
            self._calib_recording.clear()
            self._calib_backup = {}
            self._calib_drive = False
            self._calib_goals.clear()
            logger.info("Calibration saved for arm %r → %s", arm, path)
            return {
                "ok": True,
                "arm": arm,
                "path": path,
                "calibration": self._calibration_as_dict(cal),
                "targets": {a: dict(t) for a, t in self._targets.items()},
            }

    def cancel_calibration(self, token: str) -> dict[str, Any]:
        """Restore previous calibration to motors, re-enable torque, exit calib mode."""
        err = self._require_calib_client(token)
        if err:
            return err
        with self._lock:
            assert self._calib_arm is not None
            arm = self._calib_arm
            robot = self.robots[arm]
            try:
                if self._calib_drive:
                    self._calib_disable_drive_unlocked(robot)
                else:
                    robot.bus.disable_torque()
                if self._calib_backup:
                    robot.calibration = {
                        name: MotorCalibration(**asdict(cal)) for name, cal in self._calib_backup.items()
                    }
                    robot.bus.write_calibration(robot.calibration)
                robot.bus.enable_torque()
                self._seed_target(arm, robot)
            except Exception as exc:
                logger.exception("cancel_calibration failed")
                return {"ok": False, "error": f"cancel_failed:{exc}"}
            self._calib_mode = False
            self._calib_arm = None
            self._calib_recording.clear()
            self._calib_draft.clear()
            self._calib_backup = {}
            self._calib_raw.clear()
            self._calib_drive = False
            self._calib_goals.clear()
            return {
                "ok": True,
                "arm": arm,
                "targets": {a: dict(t) for a, t in self._targets.items()},
            }

    def _tick_calibration(self) -> None:
        """Refresh raw encoder values and expand recorded ranges while in calib mode."""
        if not self._calib_mode or self._calib_arm is None:
            return
        robot = self.robots.get(self._calib_arm)
        if robot is None or not getattr(robot.bus, "is_connected", False):
            return
        try:
            names = [m for m in JOINT_KEYS if m in robot.bus.motors]
            positions = robot.bus.sync_read("Present_Position", names, normalize=False)
            self._calib_raw = {m: int(positions[m]) for m in names}
            for motor in list(self._calib_recording):
                pos = int(positions[motor])
                self._calib_mins[motor] = min(self._calib_mins.get(motor, pos), pos)
                self._calib_maxes[motor] = max(self._calib_maxes.get(motor, pos), pos)
                if motor in self._calib_draft:
                    self._calib_draft[motor]["range_min"] = self._calib_mins[motor]
                    self._calib_draft[motor]["range_max"] = self._calib_maxes[motor]
        except Exception:
            logger.debug("Calibration raw read failed", exc_info=True)

