"""Unit tests for depth colorization used by Web Remote MJPEG."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_remote.depth_viz import (  # noqa: E402
    colorize_depth_mm,
    depth_stream_name,
    read_colorized_depth,
)
from web_remote.session import _camera_names_with_depth  # noqa: E402


class DepthVizTests(unittest.TestCase):
    def test_stream_name(self) -> None:
        self.assertEqual(depth_stream_name("center"), "center_depth")
        self.assertEqual(depth_stream_name("d435"), "d435_depth")

    def test_colorize_shape_and_invalid_black(self) -> None:
        depth = np.zeros((4, 5), dtype=np.uint16)
        depth[1, 2] = 1500
        rgb = colorize_depth_mm(depth, max_mm=3000.0)
        self.assertEqual(rgb.shape, (4, 5, 3))
        self.assertEqual(rgb.dtype, np.uint8)
        # Zero depth stays black.
        self.assertTrue(np.array_equal(rgb[0, 0], [0, 0, 0]))
        # Valid pixel gets a non-black colormap value.
        self.assertFalse(np.array_equal(rgb[1, 2], [0, 0, 0]))

    def test_colorize_accepts_hw1(self) -> None:
        depth = np.full((2, 3, 1), 1000, dtype=np.uint16)
        rgb = colorize_depth_mm(depth)
        self.assertEqual(rgb.shape, (2, 3, 3))

    def test_read_colorized_depth_skips_without_flag(self) -> None:
        cam = MagicMock()
        cam.use_depth = False
        self.assertIsNone(read_colorized_depth(cam))

    def test_read_colorized_depth_ok(self) -> None:
        cam = MagicMock()
        cam.use_depth = True
        cam.async_read_depth.return_value = np.full((8, 8), 800, dtype=np.uint16)
        rgb = read_colorized_depth(cam)
        self.assertIsNotNone(rgb)
        assert rgb is not None
        self.assertEqual(rgb.shape, (8, 8, 3))

    def test_camera_names_with_depth(self) -> None:
        color = MagicMock()
        color.use_depth = False
        depth_cam = MagicMock()
        depth_cam.use_depth = True
        names = _camera_names_with_depth({"center": color, "d435": depth_cam})
        self.assertEqual(names, ["center", "d435", "d435_depth"])


if __name__ == "__main__":
    unittest.main()
