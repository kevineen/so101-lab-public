"""Colorize RealSense depth (mm) for Web Remote MJPEG preview."""

from __future__ import annotations

import cv2
import numpy as np

# Logical MJPEG name: color stream ``center`` → depth twin ``center_depth``.
DEPTH_STREAM_SUFFIX = "_depth"

# Clip visualization to this range (farther = same max color). Lab table ~0.3–2 m.
DEFAULT_MAX_DEPTH_MM = 3000.0


def depth_stream_name(color_stream: str) -> str:
    """Return the MJPEG name for the colorized depth twin of a color stream."""
    return f"{color_stream}{DEPTH_STREAM_SUFFIX}"


def colorize_depth_mm(
    depth: np.ndarray,
    *,
    max_mm: float = DEFAULT_MAX_DEPTH_MM,
) -> np.ndarray:
    """Convert uint16 depth (H,W) or (H,W,1) in millimeters to RGB uint8.

    Invalid / zero pixels stay black. Uses OpenCV TURBO so near/far are easy
    to tell apart when checking camera placement in the browser.
    """
    if depth.ndim == 3:
        depth = depth[..., 0]
    if depth.ndim != 2:
        raise ValueError(f"depth must be HxW or HxWx1, got shape {depth.shape}")

    valid = depth > 0
    # Scale valid mm into 0..255 for applyColorMap.
    scaled = np.zeros(depth.shape, dtype=np.uint8)
    if valid.any() and max_mm > 0:
        clipped = np.clip(depth.astype(np.float32), 0.0, float(max_mm))
        scaled = (clipped / float(max_mm) * 255.0).astype(np.uint8)

    bgr = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    bgr[~valid] = 0
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def read_colorized_depth(cam: object, *, timeout_ms: int = 200) -> np.ndarray | None:
    """Read depth from a RealSense-like camera and return an RGB preview frame."""
    if not getattr(cam, "use_depth", False):
        return None
    read_depth = getattr(cam, "async_read_depth", None)
    if not callable(read_depth):
        read_depth = getattr(cam, "read_depth", None)
    if not callable(read_depth):
        return None
    try:
        try:
            depth = read_depth(timeout_ms=timeout_ms)
        except TypeError:
            # read_depth() in some versions has no timeout kwarg
            depth = read_depth()
    except Exception:
        return None
    if depth is None:
        return None
    return colorize_depth_mm(np.asarray(depth))
