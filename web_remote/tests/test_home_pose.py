"""Unit tests for nest / home pose persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from web_remote.home_pose import (
    default_joints,
    joints_for_arm,
    load_home_file,
    near_home,
    save_home_file,
)


class HomePoseTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "home_poses.json"
            pose = default_joints()
            pose["shoulder_pan"] = 12.5
            pose["gripper"] = 40.0
            save_home_file({"follower": pose}, path=path, merge=False)
            data = load_home_file(path)
            self.assertIn("follower", data["arms"])
            self.assertAlmostEqual(data["arms"]["follower"]["shoulder_pan"], 12.5)
            joints, from_file = joints_for_arm("follower", path=path)
            self.assertTrue(from_file)
            self.assertAlmostEqual(joints["shoulder_pan"], 12.5)

    def test_default_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            joints, from_file = joints_for_arm("leader", path=path)
            self.assertFalse(from_file)
            self.assertEqual(joints["gripper"], 50.0)

    def test_near_home(self) -> None:
        t = default_joints()
        c = dict(t)
        c["shoulder_pan"] = 1.0
        self.assertTrue(near_home(c, t, tol_deg=2.5))
        c["shoulder_pan"] = 10.0
        self.assertFalse(near_home(c, t, tol_deg=2.5))


if __name__ == "__main__":
    unittest.main()
