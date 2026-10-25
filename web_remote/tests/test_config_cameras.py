"""center_source resolution for so101_dual_cam.yaml-style configs."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_remote.config import (  # noqa: E402
    CENTER_STREAM,
    _build_cameras,
    resolve_center_source,
)


_XIAO = {
    "class": "OpenCVCamera",
    "enabled": True,
    "url": "http://192.168.77.30:81/stream",
    "fps": 15,
    "width": 640,
    "height": 480,
}
_D435 = {
    "class": "RealSenseCamera",
    "enabled": True,
    "serial_number": "213023456789",
    "fps": 30,
    "width": 640,
    "height": 480,
    "use_depth": True,
}
_WRIST = {
    "class": "OpenCVCamera",
    "enabled": True,
    "device": "/dev/video0",
    "fps": 30,
    "width": 640,
    "height": 480,
}


class ResolveCenterSourceTests(unittest.TestCase):
    def test_yaml_alias(self) -> None:
        self.assertEqual(resolve_center_source({"center_source": "d435"}), "center_d435")
        self.assertEqual(resolve_center_source({"center_source": "xiao"}), "center_xiao")

    def test_env_overrides_yaml(self) -> None:
        with patch.dict(os.environ, {"CENTER_SOURCE": "d435"}, clear=False):
            self.assertEqual(
                resolve_center_source({"center_source": "xiao"}),
                "center_d435",
            )

    def test_missing_returns_none(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CENTER_SOURCE", None)
            self.assertIsNone(resolve_center_source({}))


class BuildCamerasTests(unittest.TestCase):
    def test_selects_d435_as_center(self) -> None:
        cams = _build_cameras(
            {
                "center_xiao": _XIAO,
                "center_d435": _D435,
                "wrist_follower": _WRIST,
            },
            center_source="center_d435",
        )
        self.assertEqual(set(cams), {CENTER_STREAM, "wrist_follower"})
        self.assertEqual(cams[CENTER_STREAM].serial_number_or_name, "213023456789")

    def test_selects_xiao_as_center(self) -> None:
        cams = _build_cameras(
            {
                "center_xiao": _XIAO,
                "center_d435": _D435,
                "wrist_follower": _WRIST,
            },
            center_source="center_xiao",
        )
        self.assertEqual(set(cams), {CENTER_STREAM, "wrist_follower"})
        self.assertEqual(str(cams[CENTER_STREAM].index_or_path), _XIAO["url"])

    def test_legacy_center_key_without_source(self) -> None:
        cams = _build_cameras(
            {"center": _XIAO, "wrist_follower": _WRIST},
            center_source=None,
        )
        self.assertEqual(set(cams), {CENTER_STREAM, "wrist_follower"})

    def test_missing_candidate_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build_cameras({"center_xiao": _XIAO}, center_source="center_d435")

    def test_preview_opens_d435_beside_xiao_center(self) -> None:
        d435 = {**_D435, "preview": True}
        cams = _build_cameras(
            {
                "center_xiao": _XIAO,
                "center_d435": d435,
                "wrist_follower": _WRIST,
            },
            center_source="center_xiao",
        )
        self.assertEqual(set(cams), {CENTER_STREAM, "d435", "wrist_follower"})
        self.assertTrue(cams["d435"].use_depth)
        self.assertEqual(str(cams[CENTER_STREAM].index_or_path), _XIAO["url"])

    def test_preview_false_skips_inactive_center(self) -> None:
        cams = _build_cameras(
            {
                "center_xiao": _XIAO,
                "center_d435": {**_D435, "preview": False},
            },
            center_source="center_xiao",
        )
        self.assertEqual(set(cams), {CENTER_STREAM})


if __name__ == "__main__":
    unittest.main()
