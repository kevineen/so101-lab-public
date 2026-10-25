"""drive_profile resolution and step scaling."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_remote.config import ARM_FOLLOWER, ARM_LEADER, build_web_remote_config  # noqa: E402
from web_remote.drive_profile import (  # noqa: E402
    DRIVE_PROFILES,
    resolve_drive_profile,
)


class ResolveDriveProfileTests(unittest.TestCase):
    def test_defaults_by_arm(self) -> None:
        self.assertEqual(resolve_drive_profile(None, arm="follower").name, "full")
        self.assertEqual(resolve_drive_profile(None, arm="leader").name, "gentle_7v4")

    def test_aliases_for_12v_swap(self) -> None:
        self.assertEqual(resolve_drive_profile("follower_12v", arm="leader").name, "full")
        self.assertEqual(resolve_drive_profile("12v", arm="leader").name, "full")
        self.assertEqual(resolve_drive_profile("leader_7v4_gentle", arm="leader").name, "gentle_7v4")

    def test_gentle_step_is_slower_than_full(self) -> None:
        full = DRIVE_PROFILES["full"].effective_step(30.0)
        gentle = DRIVE_PROFILES["gentle_7v4"].effective_step(30.0)
        self.assertGreater(full, gentle)
        self.assertLessEqual(gentle, 8.0)
        # Must keep stock Feetech accel so the arm can hold against gravity.
        self.assertIsNone(DRIVE_PROFILES["gentle_7v4"].body_acceleration)

    def test_unknown_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_drive_profile("nope", arm="follower")


class BuildConfigDriveProfileTests(unittest.TestCase):
    def test_yaml_profiles(self) -> None:
        text = """
robot:
  follower_arm:
    port: /dev/ttyACM0
    drive_profile: full
  leader_arm:
    enabled: true
    port: /dev/ttyACM1
    drive_profile: gentle_7v4
cameras: {}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            bundle = build_web_remote_config(path)
            self.assertEqual(bundle.drive_profiles[ARM_FOLLOWER].name, "full")
            self.assertEqual(bundle.drive_profiles[ARM_LEADER].name, "gentle_7v4")
            self.assertLess(
                bundle.arms[ARM_LEADER].max_relative_target,
                bundle.arms[ARM_FOLLOWER].max_relative_target,
            )
        finally:
            path.unlink(missing_ok=True)

    def test_swap_leader_to_full(self) -> None:
        text = """
robot:
  follower_arm:
    port: /dev/ttyACM0
  leader_arm:
    enabled: true
    port: /dev/ttyACM1
    drive_profile: follower_12v
cameras: {}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            bundle = build_web_remote_config(path)
            self.assertEqual(bundle.drive_profiles[ARM_LEADER].name, "full")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
