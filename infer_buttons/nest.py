"""Drive the connected follower toward nest: lift first, then the rest.

Joint I/O uses the motor bus only — never ``get_observation()`` — so camera
stalls cannot freeze nest. Phone preview stays frozen while nest is held.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from so101_common.nest_stages import LIFT_JOINT, StagedNest

logger = logging.getLogger("infer_buttons")

_ARM = "follower"
_DEFAULT_NEST_STEP = 8.0


def nest_step_deg(default: float = _DEFAULT_NEST_STEP) -> float:
    """Per-tick clamp while nesting."""
    raw = os.environ.get("SO101_INFER_NEST_STEP", "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.5, float(raw))
    except ValueError:
        return float(default)


def make_staged_nest(arm: str = _ARM, path: Path | None = None) -> StagedNest | None:
    """Build a staged nest driver from the saved home pose file."""
    try:
        from so101_common.home_pose import joints_for_arm
    except ImportError:
        logger.warning("so101_common.home_pose unavailable; nest button does nothing")
        return None
    joints, from_file = joints_for_arm(arm, path=path)
    if not joints:
        logger.warning("nest pose empty for arm=%s; nest button does nothing", arm)
        return None
    if not from_file:
        logger.warning("nest pose for %s is factory default (home file missing?)", arm)
    return StagedNest(joints)


def ensure_torque_on(robot: object) -> bool:
    """Enable follower torque so Goal_Position commands actually move."""
    bus = getattr(robot, "bus", None)
    enable = getattr(bus, "enable_torque", None) if bus is not None else None
    if not callable(enable):
        return False
    try:
        enable()
        return True
    except Exception:
        logger.exception("enable_torque failed")
        return False


def read_torque_enable(robot: object) -> dict[str, int] | None:
    """Best-effort Torque_Enable map (1=on)."""
    bus = getattr(robot, "bus", None)
    if bus is None or not hasattr(bus, "sync_read"):
        return None
    try:
        raw = bus.sync_read("Torque_Enable", num_retry=0)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    out: dict[str, int] = {}
    for key, val in raw.items():
        try:
            out[str(key)] = int(val)
        except (TypeError, ValueError):
            continue
    return out


def read_joint_positions(robot: object) -> dict[str, float]:
    """Read present joint angles without touching cameras."""
    bus = getattr(robot, "bus", None)
    if bus is not None and hasattr(bus, "sync_read"):
        try:
            cfg = getattr(robot, "config", None)
            retries = int(getattr(cfg, "num_read_retries", 0) or 0) if cfg is not None else 0
            raw = bus.sync_read("Present_Position", num_retry=retries)
            if isinstance(raw, dict) and raw:
                return {str(key): float(val) for key, val in raw.items() if isinstance(val, (int, float))}
        except Exception:
            logger.exception("bus Present_Position read failed")
            return {}
    logger.warning("robot.bus unavailable; nest cannot read joints safely")
    return {}


def apply_nest_step(robot: object, step: float) -> float | None:
    """Set ``max_relative_target`` for nest; return previous value (or None)."""
    cfg = getattr(robot, "config", None)
    if cfg is None:
        return None
    saved = getattr(cfg, "max_relative_target", None)
    cfg.max_relative_target = float(step)
    return saved if isinstance(saved, (int, float)) else saved


def restore_nest_step(robot: object, saved: object) -> None:
    cfg = getattr(robot, "config", None)
    if cfg is None or saved is None:
        return
    cfg.max_relative_target = saved


def step_staged_nest(robot: object, staged: StagedNest | None) -> dict:
    """One nest tick (bus only). Returns status for the phone / logs."""
    info: dict = {
        "ok": False,
        "phase": "",
        "message": "",
        "lift_err": None,
        "moved": False,
    }
    if staged is None:
        info["message"] = "nest 姿勢が未設定（home_poses.json）"
        return info
    info["phase"] = staged.phase

    before = read_joint_positions(robot)
    if not before:
        info["message"] = "関節角が読めない（bus）"
        return info

    action = staged.action_from_current(before)
    if not action:
        info["message"] = "nest 指令が空"
        return info

    goal = staged.nest.get(LIFT_JOINT)
    here = before.get(LIFT_JOINT)
    if goal is not None and here is not None:
        info["lift_err"] = round(abs(here - goal), 1)

    step = nest_step_deg()
    saved = apply_nest_step(robot, step)
    try:
        sent = robot.send_action(action)  # type: ignore[attr-defined]
    except Exception as exc:
        restore_nest_step(robot, saved)
        logger.exception("staged nest send_action failed")
        info["message"] = f"send_action 失敗: {exc}"
        return info

    # Keep the elevated nest step while holding; restore happens on nest-off in hook.
    _ = saved
    _ = sent

    after = read_joint_positions(robot)
    if after and LIFT_JOINT in before and LIFT_JOINT in after:
        delta = abs(after[LIFT_JOINT] - before[LIFT_JOINT])
        # Also count any joint motion during "all".
        if staged.phase == "all":
            delta = max(
                (abs(after.get(k, before.get(k, 0.0)) - before.get(k, 0.0)) for k in staged.nest),
                default=0.0,
            )
        info["moved"] = delta >= 0.15
        if goal is not None and LIFT_JOINT in after:
            info["lift_err"] = round(abs(after[LIFT_JOINT] - goal), 1)

    if info["moved"]:
        staged.note_progress()
    elif staged.phase == "lift":
        staged.note_no_progress()
        if staged.phase == "all":
            ensure_torque_on(robot)
            info["message"] = "肩が動かないので全体 nest へ切替"
            info["phase"] = "all"
            info["ok"] = True
            return info
        ensure_torque_on(robot)

    info["ok"] = True
    info["phase"] = staged.phase
    err = info["lift_err"]
    if staged.phase == "lift":
        base = f"肩だけ nest へ（残り {err}°）" if err is not None else "肩だけ nest へ"
    else:
        base = "全体を nest へ移動／保持"

    if not info["moved"] and (err or 0) > staged.tol_deg:
        torques = read_torque_enable(robot)
        tip = ""
        if torques is not None and any(v == 0 for v in torques.values()):
            tip = " — Torque_Enable=0"
        elif staged.phase == "lift":
            tip = " — 肩が拘束？全体へ切替待ち"
        info["message"] = base + tip
        info["ok"] = False
    else:
        info["message"] = base
    return info


def nest_action(arm: str = _ARM, path: Path | None = None) -> dict[str, float] | None:
    staged = make_staged_nest(arm, path=path)
    if staged is None:
        return None
    return {f"{key}.pos": float(value) for key, value in staged.nest.items()}


def step_nest(robot: object, action: dict[str, float] | None) -> bool:
    """Legacy one-shot full nest (prefer ``step_staged_nest``)."""
    if not action:
        return False
    try:
        robot.send_action(action)  # type: ignore[attr-defined]
    except Exception:
        logger.exception("nest send_action failed")
        return False
    return True
