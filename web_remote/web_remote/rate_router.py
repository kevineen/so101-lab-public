"""Two motor experts and a router that picks cruise (40 Hz) or approach (20 Hz).

Hard cases are decided locally. The optional text Jev model is asked only when
the center camera and the joint targets do not already force a mode.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .config import JOINT_KEYS, JOINT_LIMITS
from .jev_router import JevRouter
from .scene_state import SceneState

CRUISE_HZ = 40.0
APPROACH_HZ = 20.0
CRUISE_STEP_DEG = 30.0
APPROACH_STEP_DEG = 12.0
# Stay on a new mode briefly, and require the same vote several looks in a row.
DWELL_S = 0.4
CONFIRM_FRAMES = 3
JEV_INTERVAL_S = 1.0
# Fraction of each joint's normalized range that counts as the calibrated edge.
# Gripper is excluded: fully closed is a normal pose, not the edge of the arm.
JOINT_EDGE_FRACTION = 0.08
_EDGE_JOINTS = tuple(key for key in JOINT_KEYS if key != "gripper")

# deg/s of the largest joint-target change, sampled by the watch loop.
_FAST_DEG_PER_S = 40.0
_MOVING_DEG_PER_S = 8.0
_FAST_STEP_DEG = 8.0
_MOVING_STEP_DEG = 2.0


def classify_command(max_delta_deg: float, dt: float) -> str:
    """Label how hard the operator is changing targets: still, moving, or fast."""
    if dt <= 0.0:
        rate = 0.0
    else:
        rate = max_delta_deg / dt
    if rate >= _FAST_DEG_PER_S or max_delta_deg >= _FAST_STEP_DEG:
        return "fast"
    if rate >= _MOVING_DEG_PER_S or max_delta_deg >= _MOVING_STEP_DEG:
        return "moving"
    return "still"


def targets_near_edge(
    targets_by_arm: dict[str, dict[str, float]],
    *,
    fraction: float = JOINT_EDGE_FRACTION,
) -> bool:
    """True when a target sits in the outer fraction of its calibrated range.

    Web Remote targets are already in the normalized range that spans
    ``range_min``..``range_max``, so the UI limits are that calibrated span.
    """
    for joints in targets_by_arm.values():
        for motor in _EDGE_JOINTS:
            if motor not in joints:
                continue
            lo, hi = JOINT_LIMITS[motor]
            span = hi - lo
            if span <= 0.0:
                continue
            margin = span * fraction
            value = float(joints[motor])
            if value <= lo + margin or value >= hi - margin:
                return True
    return False


class RateRouter:
    """Hold the active expert and switch only after a short, stable vote."""

    def __init__(
        self,
        *,
        cruise_hz: float = CRUISE_HZ,
        approach_hz: float = APPROACH_HZ,
        jev: JevRouter | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self.cruise_hz = max(1.0, float(cruise_hz))
        slower = float(approach_hz)
        self.approach_hz = slower if slower < self.cruise_hz else self.cruise_hz
        self._jev = jev
        self._lock = threading.Lock()
        self.mode = "cruise"
        self.reason = "startup"
        self.scene = SceneState()
        self._mode_since = self._clock()
        self._pending: str | None = None
        self._pending_count = 0
        self._latch: tuple[str, str] | None = None
        self._last_jev = -JEV_INTERVAL_S

    def update(
        self,
        scene: SceneState,
        *,
        command_motion: str,
        joint_near_edge: bool,
    ) -> None:
        """Ingest one perception sample. Safe to call off the motor thread."""
        desired, reason, gray = self._hard(scene, command_motion, joint_near_edge)
        if gray:
            answer = self._maybe_jev(scene, command_motion, joint_near_edge)
            if answer is not None:
                desired, reason = answer
                self._latch = answer
            elif self._latch is not None:
                desired, reason = self._latch
            else:
                desired, reason = self.mode, "hold"
        else:
            self._latch = None
        with self._lock:
            self.scene = scene
            self._apply(desired, reason)
            if self.mode == desired:
                self._latch = None

    def current_period(self) -> float:
        """Sleep time for the motor loop at the active expert."""
        with self._lock:
            hz = self.approach_hz if self.mode == "approach" else self.cruise_hz
        return 1.0 / hz

    def step_limit(self) -> float:
        """Per-tick catch-up cap in degrees (and gripper units)."""
        with self._lock:
            if self.mode == "approach" and self.approach_hz < self.cruise_hz:
                return APPROACH_STEP_DEG
            return CRUISE_STEP_DEG

    def snapshot(self) -> dict[str, object]:
        """Status fields for ``/api/state``."""
        with self._lock:
            hz = self.approach_hz if self.mode == "approach" else self.cruise_hz
            step = (
                APPROACH_STEP_DEG
                if self.mode == "approach" and self.approach_hz < self.cruise_hz
                else CRUISE_STEP_DEG
            )
            return {
                "rate_mode": self.mode,
                "control_hz": hz,
                "step_limit": step,
                "reason": self.reason,
                "scene": self.scene.to_dict(),
            }

    def _hard(
        self,
        scene: SceneState,
        command_motion: str,
        joint_near_edge: bool,
    ) -> tuple[str, str, bool]:
        """Return ``(mode, reason, gray)``. Gray means no local expert is forced."""
        if scene.proximity == "near_object":
            return "approach", "near_object", False
        if scene.workspace == "near_edge":
            return "approach", "near_edge", False
        if joint_near_edge:
            return "approach", "joint_edge", False
        scene_open = scene.proximity == "clear" and scene.workspace != "near_edge"
        if scene_open and command_motion == "fast":
            return "cruise", "fast_clear", False
        return self.mode, "hold", True

    def _maybe_jev(
        self,
        scene: SceneState,
        command_motion: str,
        joint_near_edge: bool,
    ) -> tuple[str, str] | None:
        if self._jev is None or not self._jev.enabled:
            return None
        now = self._clock()
        if now - self._last_jev < JEV_INTERVAL_S:
            return None
        self._last_jev = now
        return self._jev.choose_mode(
            scene,
            command_motion=command_motion,
            joint_near_edge=joint_near_edge,
        )

    def _apply(self, desired: str, reason: str) -> None:
        """Commit a mode after repeated votes and a minimum dwell. Caller holds the lock."""
        now = self._clock()
        if desired == self.mode:
            self._pending = None
            self._pending_count = 0
            self.reason = reason
            return
        if self._pending != desired:
            self._pending = desired
            self._pending_count = 1
        else:
            self._pending_count += 1
        if self._pending_count < CONFIRM_FRAMES:
            return
        if now - self._mode_since < DWELL_S:
            return
        self.mode = desired
        self._mode_since = now
        self._pending = None
        self._pending_count = 0
        self.reason = reason
