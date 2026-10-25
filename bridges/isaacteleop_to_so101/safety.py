"""Software soft limits (separate from Feetech / calibration motor ranges).

Used to keep Quest teleop inside a safe box so arms are less likely to hit
the table, the torso, or each other. This is NOT full collision checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contract import JOINT_KEYS, JOINT_LIMITS_DEG, clamp_joints


@dataclass(frozen=True)
class AxisBounds:
    """Inclusive ``[min, max]`` for one scalar."""

    lo: float
    hi: float

    def clamp(self, value: float) -> float:
        return max(self.lo, min(self.hi, float(value)))


@dataclass
class SoftLimits:
    """Per-physical-arm soft joint limits + optional tip XYZ box (meters)."""

    # arm name (follower|leader|*) → joint → (lo, hi) degrees
    joint_limits_deg: dict[str, dict[str, AxisBounds]] = field(default_factory=dict)
    # arm → axis x|y|z → bounds in robot base meters
    tip_bounds_m: dict[str, dict[str, AxisBounds]] = field(default_factory=dict)
    enabled: bool = True

    def joint_bounds_for(self, arm: str) -> dict[str, AxisBounds]:
        """Merge ``*`` defaults with arm-specific overrides."""
        out = dict(self.joint_limits_deg.get("*") or {})
        out.update(self.joint_limits_deg.get(arm) or {})
        return out

    def tip_bounds_for(self, arm: str) -> dict[str, AxisBounds]:
        out = dict(self.tip_bounds_m.get("*") or {})
        out.update(self.tip_bounds_m.get(arm) or {})
        return out

    def clamp_joints(self, arm: str, joints: Mapping[str, float]) -> dict[str, float]:
        """Hardware clamp then soft joint clamp for ``arm``."""
        base = clamp_joints(joints)
        if not self.enabled:
            return base
        soft = self.joint_bounds_for(arm)
        if not soft:
            return base
        out = dict(base)
        for key, bounds in soft.items():
            if key not in out:
                continue
            out[key] = bounds.clamp(out[key])
            # Never exceed hardware envelope even if yaml is wider.
            hw = JOINT_LIMITS_DEG.get(key)
            if hw is not None:
                out[key] = max(hw[0], min(hw[1], out[key]))
        return out

    def clamp_tip(
        self,
        arm: str,
        tip_xyz: tuple[float, float, float] | list[float],
    ) -> tuple[float, float, float]:
        """Clamp tip position in robot base; no-op if no tip bounds for arm."""
        x, y, z = float(tip_xyz[0]), float(tip_xyz[1]), float(tip_xyz[2])
        if not self.enabled:
            return x, y, z
        bounds = self.tip_bounds_for(arm)
        if not bounds:
            return x, y, z
        if "x" in bounds:
            x = bounds["x"].clamp(x)
        if "y" in bounds:
            y = bounds["y"].clamp(y)
        if "z" in bounds:
            z = bounds["z"].clamp(z)
        return x, y, z

    def clamp_tip_anchored(
        self,
        arm: str,
        tip0: tuple[float, float, float] | list[float],
        tip_des: tuple[float, float, float] | list[float],
    ) -> tuple[float, float, float]:
        """Clamp ``tip_des`` without yanking the clutch FK anchor ``tip0``.

        If nest FK tip sits outside ``tip_bounds_m``, a hard clamp on every
        frame collapses depth (Δx → same boundary) and can force continuous
        down/up motion (Δz → boundary). Expand the effective box to include
        ``tip0`` so delta=0 holds the nest; only further excursion is limited.
        """
        t0 = (float(tip0[0]), float(tip0[1]), float(tip0[2]))
        td = (float(tip_des[0]), float(tip_des[1]), float(tip_des[2]))
        if not self.enabled:
            return td
        bounds = self.tip_bounds_for(arm)
        if not bounds:
            return td
        out: list[float] = []
        for axis, t0_v, td_v in zip(("x", "y", "z"), t0, td, strict=True):
            if axis not in bounds:
                out.append(td_v)
                continue
            b = bounds[axis]
            lo = min(b.lo, t0_v)
            hi = max(b.hi, t0_v)
            out.append(max(lo, min(hi, td_v)))
        return out[0], out[1], out[2]

def _parse_pair(raw: Any, *, context: str) -> AxisBounds:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{context} must be [min, max]")
    lo, hi = float(raw[0]), float(raw[1])
    if lo > hi:
        lo, hi = hi, lo
    return AxisBounds(lo=lo, hi=hi)


def parse_soft_limits(raw: Mapping[str, Any] | None) -> SoftLimits:
    """Parse ``safety:`` block from quest_teleop.yaml."""
    if not raw:
        return SoftLimits(enabled=False)
    enabled = bool(raw.get("enabled", True))
    joint_limits: dict[str, dict[str, AxisBounds]] = {}
    raw_joints = raw.get("soft_joint_limits_deg") or {}
    if isinstance(raw_joints, Mapping):
        # Flat form: { shoulder_pan: [a,b], ... } → apply to all arms via "*"
        flat_keys = set(raw_joints) & set(JOINT_KEYS)
        if flat_keys and not any(k in {"follower", "leader", "*"} for k in raw_joints):
            joint_limits["*"] = {
                k: _parse_pair(raw_joints[k], context=f"soft_joint_limits_deg.{k}")
                for k in flat_keys
            }
        for arm, joints in raw_joints.items():
            if arm in JOINT_KEYS:
                continue
            if not isinstance(joints, Mapping):
                raise ValueError(f"soft_joint_limits_deg.{arm} must be a mapping")
            arm_key = str(arm)
            joint_limits[arm_key] = {
                str(j): _parse_pair(pair, context=f"soft_joint_limits_deg.{arm}.{j}")
                for j, pair in joints.items()
            }

    tip_bounds: dict[str, dict[str, AxisBounds]] = {}
    raw_tips = raw.get("tip_bounds_m") or {}
    if isinstance(raw_tips, Mapping):
        flat_axes = set(raw_tips) & {"x", "y", "z"}
        if flat_axes and not any(k in {"follower", "leader", "*"} for k in raw_tips):
            tip_bounds["*"] = {
                a: _parse_pair(raw_tips[a], context=f"tip_bounds_m.{a}") for a in flat_axes
            }
        for arm, axes in raw_tips.items():
            if arm in {"x", "y", "z"}:
                continue
            if not isinstance(axes, Mapping):
                raise ValueError(f"tip_bounds_m.{arm} must be a mapping")
            tip_bounds[str(arm)] = {
                str(a): _parse_pair(pair, context=f"tip_bounds_m.{arm}.{a}")
                for a, pair in axes.items()
                if str(a) in {"x", "y", "z"}
            }

    return SoftLimits(
        joint_limits_deg=joint_limits,
        tip_bounds_m=tip_bounds,
        enabled=enabled,
    )
