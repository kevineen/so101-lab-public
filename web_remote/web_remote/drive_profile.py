"""Per-arm drive profiles for Web Remote (speed / acceleration trade-offs).

Human-oriented docs (profiles, 12V swap, safety): ``docs/13_drive_profiles.md``.

SO-101 hardware differs by role:

- **Follower** (drive arm): usually 1:345 gearing; optional **12V** STS3215 for more
  stall torque. Use profile ``full``.
- **Leader** (teleop arm): mixed lower ratios (elbow 1:191) on **7.4V / 5V supply**.
  Designed to be backdriven by hand — weak as a second drive arm.

Web Remote can still position-control the physical leader port. Until that hardware
is replaced with a real follower (ideally 12V), use ``gentle_7v4`` so motion is
slower and less likely to trip Overload. Swap path: set ``drive_profile: full``
on that arm after installing follower motors + correct PSU (never put 12V on
7.4V leader servos).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Body joints only — gripper keeps stock Feetech acceleration.
BODY_JOINTS: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)


@dataclass(frozen=True)
class DriveProfile:
    """Motion limits applied on top of the global rate router."""

    name: str
    # Multiplier on RateRouter step_limit (°/tick).
    step_scale: float = 1.0
    # Hard cap on °/tick after scaling (None = no extra cap).
    max_step_deg: float | None = None
    # Cap while nesting / go-home (None = use max_step_deg only).
    homing_max_step_deg: float | None = None
    # Feetech Acceleration / Maximum_Acceleration (1–254). None = leave LeRobot default.
    body_acceleration: int | None = None
    # Human-readable note for /api/info and logs.
    summary: str = ""

    def effective_step(self, router_step_deg: float, *, homing: bool = False) -> float:
        """Router step → per-arm catch-up cap (never zero)."""
        step = max(0.0, float(router_step_deg)) * float(self.step_scale)
        if self.max_step_deg is not None:
            step = min(step, float(self.max_step_deg))
        if homing and self.homing_max_step_deg is not None:
            step = min(step, float(self.homing_max_step_deg))
        return max(step, 0.5)

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot for /api/info and /api/state."""
        return asdict(self)


# Named presets. YAML ``drive_profile`` must be a key here (aliases allowed).
DRIVE_PROFILES: dict[str, DriveProfile] = {
    # Stock drive-arm behaviour (7.4V or 12V follower hardware).
    "full": DriveProfile(
        name="full",
        step_scale=1.0,
        max_step_deg=None,
        homing_max_step_deg=8.0,
        body_acceleration=None,
        summary="Full rate — use for real follower arms (incl. 12V swap).",
    ),
    # Temporary: physical leader motors driven as second arm.
    # IMPORTANT: do NOT lower Feetech Acceleration here — that softens holding
    # torque and the arm drops under gravity while "raising slowly".
    # Slowness comes only from smaller max_relative_target steps.
    "gentle_7v4": DriveProfile(
        name="gentle_7v4",
        step_scale=0.4,
        max_step_deg=8.0,
        homing_max_step_deg=5.0,
        body_acceleration=None,
        summary="Slower command steps for 7.4V leader-as-drive; keeps stock servo accel (holds vs gravity).",
    ),
}

# Aliases so yaml can say follower_12v when documenting the swap.
DRIVE_PROFILE_ALIASES: dict[str, str] = {
    "follower_full": "full",
    "follower_12v": "full",
    "12v": "full",
    "leader_gentle": "gentle_7v4",
    "leader_7v4_gentle": "gentle_7v4",
    "gentle": "gentle_7v4",
}

DEFAULT_PROFILE_BY_ARM: dict[str, str] = {
    "follower": "full",
    "leader": "gentle_7v4",
}


def resolve_drive_profile(name: str | None, *, arm: str) -> DriveProfile:
    """Resolve yaml/env profile name to a DriveProfile (unknown → arm default)."""
    raw = (name or "").strip().lower()
    if not raw:
        raw = DEFAULT_PROFILE_BY_ARM.get(arm, "full")
    key = DRIVE_PROFILE_ALIASES.get(raw, raw)
    if key not in DRIVE_PROFILES:
        known = ", ".join(sorted({*DRIVE_PROFILES, *DRIVE_PROFILE_ALIASES}))
        raise ValueError(f"Unknown drive_profile {name!r} for arm {arm!r} (known: {known})")
    return DRIVE_PROFILES[key]


def apply_body_acceleration(robot: Any, profile: DriveProfile) -> list[str]:
    """Write Feetech Acceleration for body joints. Returns motors that were updated."""
    accel = profile.body_acceleration
    if accel is None:
        return []
    accel_i = int(accel)
    if not 1 <= accel_i <= 254:
        raise ValueError(f"body_acceleration must be 1–254, got {accel_i}")

    bus = robot.bus
    updated: list[str] = []
    # Prefer writing with torque briefly off (matches LeRobot configure()).
    disable = getattr(bus, "torque_disabled", None)
    ctx = disable() if callable(disable) else _nullcontext()
    with ctx:
        for motor in BODY_JOINTS:
            if motor not in getattr(bus, "motors", {}):
                continue
            if getattr(bus, "protocol_version", 0) == 0:
                bus.write("Maximum_Acceleration", motor, accel_i)
            bus.write("Acceleration", motor, accel_i)
            updated.append(motor)
    return updated


class _nullcontext:
    """Minimal stand-in when bus.torque_disabled is unavailable."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None
