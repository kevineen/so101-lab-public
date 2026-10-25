"""Lightweight look at the center camera, about 5 Hz.

Produces a :class:`SceneState` from frame differences and nearby edges.
An image model can replace this module later without changing the router.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from .scene_state import (
    Motion,
    Proximity,
    SceneState,
    Workspace,
    coerce_motion,
    describe_scene,
)

# yaml key for the overhead / workspace camera.
CENTER_CAMERA = "center"

_SMALL_WIDTH = 160
# Fraction of the small frame that must change before the arm counts as moving.
_MOVING_FRAC = 0.008
_FAST_FRAC = 0.05
_MIN_ARM_PIXELS = 40
_DIFF_THRESHOLD = 18
# Arm blob this close to the image border is leaving the visible work area.
_EDGE_MARGIN = 0.08
# Static edges in a ring around the arm, compared with the rest of the frame.
_RING_INNER = 0.12
_RING_OUTER = 0.42
# A nearby object leaves a clump of static edges. Absolute density stays low
# because the ring is most of the frame, so the count and the gap vs. the
# rest of the image decide it.
_MIN_OBJECT_EDGES = 40
_DENSITY_GAP = 0.004
_NEAR_RATIO = 1.8

_MOTION_RANK = {"still": 0, "moving": 1, "fast": 2}


def _louder(left: Motion, right: Motion) -> Motion:
    """Keep the stronger of the camera motion and the operator command."""
    if _MOTION_RANK[left] >= _MOTION_RANK[right]:
        return left
    return right


def _small_gray(frame: np.ndarray) -> np.ndarray:
    """Resize one RGB or gray frame to a fixed width for cheap differences."""
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    else:
        gray = frame
    height, width = gray.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("empty frame")
    if width == _SMALL_WIDTH:
        return gray
    new_height = max(1, int(round(height * (_SMALL_WIDTH / float(width)))))
    return cv2.resize(gray, (_SMALL_WIDTH, new_height), interpolation=cv2.INTER_AREA)


def _centroid(mask: np.ndarray) -> tuple[float, float] | None:
    """Mean pixel of a boolean mask, or None when the blob is too small."""
    ys, xs = np.nonzero(mask)
    if xs.size < _MIN_ARM_PIXELS:
        return None
    return float(xs.mean()), float(ys.mean())


def _visual_motion(fraction: float) -> Motion:
    if fraction >= _FAST_FRAC:
        return "fast"
    if fraction >= _MOVING_FRAC:
        return "moving"
    return "still"


def _workspace(centroid: tuple[float, float] | None, shape: tuple[int, int]) -> Workspace:
    if centroid is None:
        return "unknown"
    height, width = shape
    x, y = centroid
    if (
        x < width * _EDGE_MARGIN
        or x > width * (1.0 - _EDGE_MARGIN)
        or y < height * _EDGE_MARGIN
        or y > height * (1.0 - _EDGE_MARGIN)
    ):
        return "near_edge"
    return "inside"


def _proximity(
    edges: np.ndarray,
    centroid: tuple[float, float] | None,
    arm_mask: np.ndarray,
) -> Proximity:
    """Call the scene clear when edges near the arm match the rest of the table.

    A real object shows up as extra static edge inside the ring and not across
    the whole frame. The moving arm itself is masked out.
    """
    if centroid is None:
        return "unknown"
    height, width = edges.shape[:2]
    yy, xx = np.ogrid[:height, :width]
    x, y = centroid
    dist_sq = (xx - x) ** 2 + (yy - y) ** 2
    min_side = float(min(height, width))
    ring = (dist_sq >= (min_side * _RING_INNER) ** 2) & (dist_sq <= (min_side * _RING_OUTER) ** 2)
    ring &= ~arm_mask
    rest = ~ring & ~arm_mask
    edge_on = edges > 0
    ring_count = int(edge_on[ring].sum()) if np.any(ring) else 0
    ring_density = float(edge_on[ring].mean()) if np.any(ring) else 0.0
    rest_density = float(edge_on[rest].mean()) if np.any(rest) else 0.0
    if (
        ring_count >= _MIN_OBJECT_EDGES
        and ring_density >= rest_density * _NEAR_RATIO
        and ring_density >= rest_density + _DENSITY_GAP
    ):
        return "near_object"
    if ring_density <= rest_density * 1.25 + 0.02:
        return "clear"
    return "unknown"


class CenterWatch:
    """Turn the latest center frame into a :class:`SceneState`."""

    def __init__(self) -> None:
        self._previous: np.ndarray | None = None

    def observe(self, frame: np.ndarray | None, *, command_motion: str = "still") -> SceneState:
        """Read one frame. ``command_motion`` is how hard the operator is driving."""
        command = coerce_motion(command_motion)
        now = time.monotonic()
        if frame is None or frame.size == 0:
            return self._state(command, "unknown", "unknown", now)

        try:
            small = _small_gray(frame)
        except (ValueError, cv2.error):
            return self._state(command, "unknown", "unknown", now)

        previous = self._previous
        self._previous = small
        if previous is None or previous.shape != small.shape:
            return self._state(command, "unknown", "unknown", now)

        diff = cv2.absdiff(small, previous)
        changed = diff > _DIFF_THRESHOLD
        fraction = float(changed.mean())
        motion = _louder(_visual_motion(fraction), command)
        kernel = np.ones((5, 5), np.uint8)
        arm_mask = cv2.dilate(changed.astype(np.uint8), kernel, iterations=2).astype(bool)
        centroid = _centroid(changed)
        edges = cv2.Canny(small, 80, 160)
        proximity = _proximity(edges, centroid, arm_mask)
        workspace = _workspace(centroid, small.shape[:2])
        return self._state(motion, proximity, workspace, now)

    @staticmethod
    def _state(motion: Motion, proximity: Proximity, workspace: Workspace, now: float) -> SceneState:
        return SceneState(
            motion=motion,
            proximity=proximity,
            workspace=workspace,
            source="center_cv",
            summary=describe_scene(motion, proximity, workspace),
            updated_at=now,
        )
