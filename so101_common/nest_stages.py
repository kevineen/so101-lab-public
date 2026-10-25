"""Staged nest: move ``shoulder_lift`` (motor id 2) to nest before the other joints.

Moving pan/elbow first while the arm is low collides with the table. Command only
the lift joint until it is near the nest angle, then drive the full nest pose.
"""

from __future__ import annotations

from .joints import JOINT_KEYS

#: Dynamixel / Feetech id 2 on SO-101 follower / leader.
LIFT_JOINT = "shoulder_lift"


def joints_from_observation(obs: object) -> dict[str, float]:
    """Read present joint angles from a robot observation mapping."""
    if not isinstance(obs, dict):
        return {}
    out: dict[str, float] = {}
    for key in JOINT_KEYS:
        raw = obs.get(f"{key}.pos")
        if isinstance(raw, (int, float)):
            out[key] = float(raw)
    return out


def lift_then_all_targets(
    current: dict[str, float],
    nest: dict[str, float],
    *,
    lift_joint: str = LIFT_JOINT,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (lift-only target, full nest target).

    Lift-only commands **only** ``lift_joint`` (other joints omitted so we do not
    freeze a stretched trial pose that can bind the shoulder).
    """
    full = {key: float(nest[key]) for key in JOINT_KEYS if key in nest}
    lift_only: dict[str, float] = {}
    if lift_joint in nest:
        lift_only[lift_joint] = float(nest[lift_joint])
    elif lift_joint in current:
        lift_only[lift_joint] = float(current[lift_joint])
    return lift_only, full


class StagedNest:
    """Tick-based nest for the phone infer ready loop."""

    def __init__(
        self,
        nest: dict[str, float],
        *,
        lift_joint: str = LIFT_JOINT,
        tol_deg: float = 4.0,
        stuck_ticks_before_all: int = 15,
    ) -> None:
        self.nest = {key: float(value) for key, value in nest.items()}
        self.lift_joint = lift_joint
        self.tol_deg = float(tol_deg)
        self.stuck_ticks_before_all = int(stuck_ticks_before_all)
        self.phase = "lift"  # then "all"
        self._stuck = 0

    def reset(self) -> None:
        self.phase = "lift"
        self._stuck = 0

    def note_no_progress(self) -> None:
        """Call when a lift tick did not move the shoulder; may force phase ``all``."""
        if self.phase != "lift":
            return
        self._stuck += 1
        if self._stuck >= self.stuck_ticks_before_all:
            self.phase = "all"
            self._stuck = 0

    def note_progress(self) -> None:
        self._stuck = 0

    def action_from_current(self, current: dict[str, float]) -> dict[str, float] | None:
        """One ``send_action`` dict from joint degrees, or None when nest/current empty."""
        if not self.nest or not current:
            return None
        if self.phase == "lift":
            goal = self.nest.get(self.lift_joint)
            here = current.get(self.lift_joint)
            if goal is not None and here is not None and abs(here - goal) <= self.tol_deg:
                self.phase = "all"
            else:
                lift_only, _ = lift_then_all_targets(current, self.nest, lift_joint=self.lift_joint)
                if not lift_only:
                    return None
                return {f"{key}.pos": float(value) for key, value in lift_only.items()}
        return {f"{key}.pos": float(value) for key, value in self.nest.items() if key in JOINT_KEYS}

    def action(self, obs: object) -> dict[str, float] | None:
        """One ``send_action`` dict (``*.pos`` keys), or None when nest is empty."""
        return self.action_from_current(joints_from_observation(obs))
