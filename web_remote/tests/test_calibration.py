"""CalibrationMixin のスモークテスト（実機不要・fake bus で検証）。

ドラフト編集の直列化・復元とレンジ記録の集計ロジックを検証する。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from lerobot.motors.motors_bus import MotorCalibration

from web_remote.calibration import CalibrationMixin


def _fake_robot() -> SimpleNamespace:
    """_tick_calibration が触る部分だけを持つ fake。"""
    calibration = {
        name: MotorCalibration(
            id=i + 1,
            drive_mode=0,
            homing_offset=2048,
            range_min=512,
            range_max=3583,
        )
        for i, name in enumerate(
            ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
        )
    }

    positions = {name: 1500 + i for i, name in enumerate(calibration)}

    class Bus:
        motors = dict(calibration)
        is_connected = True

        def sync_read(self, _reg, names, normalize=False):
            return dict(positions)

    bus = Bus()
    return SimpleNamespace(calibration=calibration, bus=bus, id="fake_so101")


class _Host(CalibrationMixin):
    """Mixin が要求する最小の属性だけ用意したホスト。"""

    def __init__(self) -> None:
        self.robots: dict[str, Any] = {"follower": _fake_robot()}
        self._calib_mode = False
        self._calib_arm: str | None = None
        self._calib_draft: dict[str, dict[str, int]] = {}
        self._calib_recording: set[str] = set()
        self._calib_mins: dict[str, int] = {}
        self._calib_maxes: dict[str, int] = {}
        self._calib_raw: dict[str, int] = {}
        self._calib_drive = False
        self._calib_goals: dict[str, int] = {}

    def claim_client(self, token: str) -> bool:
        return token == "tok"


class CalibrationSerializationTests(unittest.TestCase):
    def test_dict_roundtrip(self) -> None:
        host = _Host()
        robot = host.robots["follower"]
        as_dict = host._calibration_as_dict(robot.calibration)
        self.assertEqual(as_dict["shoulder_pan"]["homing_offset"], 2048)
        restored = host._dict_to_calibration(as_dict)
        self.assertEqual(restored["gripper"].range_max, 3583)

    def test_tick_records_range_when_recording(self) -> None:
        host = _Host()
        host._calib_mode = True
        host._calib_arm = "follower"
        host._calib_draft = host._calibration_as_dict(host.robots["follower"].calibration)
        host._calib_recording = {"wrist_roll"}

        host._tick_calibration()

        raw = host._calib_raw["wrist_roll"]
        self.assertEqual(host._calib_mins["wrist_roll"], raw)
        self.assertEqual(host._calib_maxes["wrist_roll"], raw)
        self.assertEqual(host._calib_draft["wrist_roll"]["range_min"], raw)

    def test_tick_noop_outside_calib_mode(self) -> None:
        host = _Host()
        host._tick_calibration()  # 例外を出さない
        self.assertEqual(host._calib_raw, {})

    def test_require_calib_client(self) -> None:
        host = _Host()
        err = host._require_calib_client("tok")
        self.assertEqual(err, {"ok": False, "error": "not_in_calib_mode"})
        host._calib_mode = True
        host._calib_arm = "follower"
        self.assertIsNone(host._require_calib_client("tok"))
        self.assertEqual(
            host._require_calib_client("other"), {"ok": False, "error": "another_client_connected"}
        )


if __name__ == "__main__":
    unittest.main()
