"""Slow nest approach / hold for record_buttons (follower + leader).

Uses ``~/.cache/so101-lab/home_poses.json`` (same file as Web Remote / go_so101_home).
The phone ``nest`` toggle sets ``events["hold_nest"]``. While that flag is on,
both arms step toward nest and keep holding until Start or the toggle turns off.

Staged approach: ``wrist_flex`` (motor id 4) is driven to its nest angle first,
then the remaining joints move together. Leveling the wrist before the arm
moves keeps a gripped object from swinging during the return. The first joint
is overridden with ``SO101_RECORD_NEST_FIRST_JOINT``; if it never moves, the
full-nest command takes over after ``_STUCK_TICKS_BEFORE_ALL`` ticks.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from so101_common.home_pose import DEFAULT_HOME_PATH, joints_for_arm, near_home, near_target
from so101_common.joints import JOINT_KEYS

logger = logging.getLogger("record_buttons.nest")

# Slow approach: ~2°/tick at 20 Hz. Override with SO101_RECORD_NEST_STEP.
_DEFAULT_STEP_DEG = 2.0
_DEFAULT_HZ = 20.0
_DEFAULT_TOL_DEG = 2.5

#: nest への到着前に先に戻す関節。SO-101 のモーター ID 4 = wrist_flex（手首ピッチ）。
NEST_FIRST_JOINT = "wrist_flex"
#: 先行関節がまったく動かなければ全関節 nest へ切替するまでの tick 数（20 Hz で 1.5 秒）。
_STUCK_TICKS_BEFORE_ALL = 30
#: 先行関節が「動いた」とみなす 1 tick あたりの最小変化（度）。
_STUCK_DELTA_DEG = 0.1


def nest_enabled() -> bool:
    """False when ``SO101_RECORD_GO_HOME=0`` (same idea as Quest ``GO_HOME=0``)."""
    raw = os.environ.get("SO101_RECORD_GO_HOME", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def nest_first_joint() -> str:
    """Joint returned to nest first. Override with ``SO101_RECORD_NEST_FIRST_JOINT``."""
    raw = os.environ.get("SO101_RECORD_NEST_FIRST_JOINT", "").strip()
    return raw or NEST_FIRST_JOINT


def first_stage_target(nest: dict[str, float], first_joint: str) -> dict[str, float]:
    """Nest angles for the first-stage joint only. Empty when it is not in ``nest``."""
    if first_joint in nest:
        return {first_joint: float(nest[first_joint])}
    return {}


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def nest_step_deg() -> float:
    return float(_float_env("SO101_RECORD_NEST_STEP", _DEFAULT_STEP_DEG))


def nest_hz() -> float:
    return float(_float_env("SO101_RECORD_NEST_HZ", _DEFAULT_HZ))


def nest_tol_deg() -> float:
    return float(_DEFAULT_TOL_DEG)


def load_nest_targets(home_file: Path | None = None) -> dict[str, dict[str, float]]:
    """Return ``{"follower": joints, "leader": joints}`` from the home file."""
    path = home_file or DEFAULT_HOME_PATH
    follower, _ = joints_for_arm("follower", path=path)
    leader, _ = joints_for_arm("leader", path=path)
    return {"follower": follower, "leader": leader}


def joints_from_pos_dict(data: object) -> dict[str, float]:
    """Extract joint degrees from an observation / action dict with ``*.pos`` keys."""
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for key in JOINT_KEYS:
        value = data.get(f"{key}.pos")
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def step_toward(
    current: dict[str, float],
    target: dict[str, float],
    step_deg: float,
) -> dict[str, float]:
    """Move each joint at most ``step_deg`` toward ``target``."""
    stepped: dict[str, float] = {}
    for key in JOINT_KEYS:
        if key not in target:
            continue
        cur = float(current.get(key, target[key]))
        goal = float(target[key])
        delta = goal - cur
        if abs(delta) <= step_deg:
            stepped[key] = goal
        else:
            stepped[key] = cur + step_deg if delta > 0 else cur - step_deg
    return stepped


def action_from_joints(joints: dict[str, float]) -> dict[str, float]:
    return {f"{key}.pos": float(value) for key, value in joints.items()}


def enable_leader_drive(teleop: object | None) -> bool:
    """Turn leader torque on so Goal_Position commands hold. Return True if enabled."""
    if teleop is None:
        return False
    enable = getattr(teleop, "enable_torque", None)
    if not callable(enable):
        return False
    try:
        enable()
        return True
    except Exception:
        logger.exception("enable_torque failed on teleop")
        return False


def release_leader_drive(teleop: object | None) -> None:
    """Backdrive-friendly: disable leader torque after nest hold."""
    if teleop is None:
        return
    disable = getattr(teleop, "disable_torque", None)
    if not callable(disable):
        return
    try:
        disable()
    except Exception:
        logger.exception("disable_torque failed on teleop")


def _drive_leader_step(teleop: object, target: dict[str, float], step_deg: float) -> dict[str, float]:
    """Step the leader toward ``target`` via ``send_feedback``. Return current joints."""
    get_action = getattr(teleop, "get_action", None)
    send_feedback = getattr(teleop, "send_feedback", None)
    if not callable(get_action) or not callable(send_feedback):
        return {}
    current = joints_from_pos_dict(get_action())
    if not current:
        return {}
    goal = step_toward(current, target, step_deg)
    send_feedback(action_from_joints(goal))
    return current


def _drive_follower_step(robot: object, target: dict[str, float], step_deg: float) -> dict[str, float]:
    """Step the follower toward nest using ``max_relative_target`` + ``send_action``."""
    cfg = getattr(robot, "config", None)
    if cfg is not None:
        cfg.max_relative_target = float(step_deg)
    robot.send_action(action_from_joints(target))
    obs = robot.get_observation()
    return joints_from_pos_dict(obs)


def tick_nest_both_joints(
    robot: object,
    teleop: object | None,
    targets: dict[str, dict[str, float]],
    *,
    step_deg: float | None = None,
) -> tuple[bool, bool, dict[str, float], dict[str, float]]:
    """One control tick. Return ``(follower_near, leader_near, follower_joints, leader_joints)``.

    ``near_home`` assumes a full target; callers that pass a partial (staged)
    target must compute arrival from the returned joints themselves.
    """
    step = float(step_deg if step_deg is not None else nest_step_deg())
    tol = nest_tol_deg()
    follower_near = False
    leader_near = False
    follower_joints: dict[str, float] = {}
    leader_joints: dict[str, float] = {}

    follower_target = targets["follower"]
    if robot is not None and hasattr(robot, "send_action") and hasattr(robot, "get_observation"):
        follower_joints = _drive_follower_step(robot, follower_target, step)
        follower_near = bool(follower_joints) and near_home(follower_joints, follower_target, tol_deg=tol)

    leader_target = targets["leader"]
    if teleop is not None:
        leader_joints = _drive_leader_step(teleop, leader_target, step)
        if leader_joints:
            leader_near = near_home(leader_joints, leader_target, tol_deg=tol)
        else:
            leader_near = True  # no leader drive available — do not block forever
    else:
        leader_near = True

    return follower_near, leader_near, follower_joints, leader_joints


def tick_nest_both(
    robot: object,
    teleop: object | None,
    targets: dict[str, dict[str, float]],
    *,
    step_deg: float | None = None,
) -> tuple[bool, bool]:
    """One control tick. Return ``(follower_near, leader_near)``."""
    follower_near, leader_near, _, _ = tick_nest_both_joints(robot, teleop, targets, step_deg=step_deg)
    return follower_near, leader_near


def _joint_moved(now: float | None, before: float | None) -> bool:
    """True when a joint advanced at least ``_STUCK_DELTA_DEG`` between reads."""
    if now is None or before is None:
        return False
    return abs(float(now) - float(before)) >= _STUCK_DELTA_DEG


def run_ready_with_nest(
    *,
    events: dict,
    robot: object,
    teleop: object | None,
    follow_slice,
    pause=time.sleep,
    home_file: Path | None = None,
) -> None:
    """Ready-phase loop: teleop follow, or nest-hold while ``hold_nest`` is on.

    ``follow_slice`` runs a short vendor ``record_loop`` without a dataset (teleop
    only). Start sets ``start_episode``; that ends this loop so recording can begin.
    """
    if not nest_enabled():
        follow_slice()
        return

    targets = load_nest_targets(home_file)
    path = home_file or DEFAULT_HOME_PATH
    step = nest_step_deg()
    rate = nest_hz()
    period = 1.0 / max(1.0, rate)
    cfg = getattr(robot, "config", None) if robot is not None else None
    saved_limit = getattr(cfg, "max_relative_target", None) if cfg is not None else None
    leader_driven = False
    was_holding = False

    first = nest_first_joint()
    first_follower = first_stage_target(targets["follower"], first)
    first_leader = first_stage_target(targets["leader"], first)
    staged = bool(first_follower) and bool(first_leader)
    first_targets = {"follower": first_follower, "leader": first_leader}
    tol = nest_tol_deg()
    stage = "first"
    stuck = 0
    last_follower: float | None = None
    last_leader: float | None = None

    try:
        while not events.get("stop_recording") and not events.get("start_episode"):
            if events.get("rerecord_episode"):
                break

            if events.get("hold_nest"):
                if not was_holding:
                    extra = f"、まず {first} を nest 角度へ" if staged else ""
                    print(
                        f"両腕を nest へゆっくり移動／保持します（{path}、step={step:.1f}°{extra}）…",
                        flush=True,
                    )
                    was_holding = True
                    stage = "first" if staged else "all"
                    stuck = 0
                    last_follower = None
                    last_leader = None
                if not leader_driven:
                    leader_driven = enable_leader_drive(teleop)
                events["phase"] = "homing"
                follower_near = False
                leader_near = False
                if stage == "first":
                    _, _, cur_f, cur_l = tick_nest_both_joints(
                        robot, teleop, first_targets, step_deg=step
                    )
                    follower_done = bool(cur_f) and near_target(cur_f, first_follower, tol_deg=tol)
                    leader_done = not bool(cur_l) or near_target(cur_l, first_leader, tol_deg=tol)
                    moved = _joint_moved(cur_f.get(first), last_follower) or _joint_moved(
                        cur_l.get(first), last_leader
                    )
                    last_follower = cur_f.get(first, last_follower)
                    last_leader = cur_l.get(first, last_leader)
                    if follower_done and leader_done:
                        stage = "all"
                        stuck = 0
                        print(f"{first} を nest 角度へ揃えました。他の関節を nest へ戻します。", flush=True)
                    elif moved:
                        stuck = 0
                    else:
                        stuck += 1
                        if stuck >= _STUCK_TICKS_BEFORE_ALL:
                            stage = "all"
                            stuck = 0
                            print(f"{first} が動かないので全関節で nest へ戻します。", flush=True)
                else:
                    follower_near, leader_near = tick_nest_both(robot, teleop, targets, step_deg=step)
                if follower_near and leader_near:
                    events["phase"] = "ready"
                    events["nest_holding"] = True
                else:
                    events["nest_holding"] = False
                if events.get("exit_early") and not events.get("start_episode"):
                    events["exit_early"] = False
                pause(period)
                continue

            # Nest toggle off: release leader and resume teleop follow slices.
            if was_holding:
                print("nest 保持を解除。leader 追従に戻ります。", flush=True)
                was_holding = False
            events["nest_holding"] = False
            if leader_driven:
                release_leader_drive(teleop)
                leader_driven = False
            if cfg is not None:
                cfg.max_relative_target = saved_limit
            events["phase"] = "ready"
            follow_slice()
            # Vendor record_loop clears exit_early on Start; start_episode remains.
            if events.get("exit_early") and not events.get("start_episode"):
                events["exit_early"] = False
    finally:
        events["nest_holding"] = False
        if leader_driven:
            release_leader_drive(teleop)
        if cfg is not None:
            cfg.max_relative_target = saved_limit


def approach_follower_nest(
    robot: object,
    *,
    home_file: Path | None = None,
    step_deg: float | None = None,
    hz: float | None = None,
    timeout_s: float | None = None,
    tol_deg: float | None = None,
    pause=time.sleep,
) -> bool:
    """Legacy one-shot follower-only approach (kept for tests / scripts)."""
    if not nest_enabled():
        logger.info("Skipping nest approach (SO101_RECORD_GO_HOME=0)")
        return True
    if robot is None or not hasattr(robot, "send_action") or not hasattr(robot, "get_observation"):
        logger.warning("Cannot approach nest: robot has no send_action/get_observation")
        return False

    step = float(step_deg if step_deg is not None else nest_step_deg())
    rate = float(hz if hz is not None else nest_hz())
    timeout = float(timeout_s if timeout_s is not None else _float_env("SO101_RECORD_NEST_TIMEOUT", 60.0))
    tol = float(tol_deg if tol_deg is not None else nest_tol_deg())
    targets = load_nest_targets(home_file)
    target = targets["follower"]
    cfg = getattr(robot, "config", None)
    saved_limit = getattr(cfg, "max_relative_target", None) if cfg is not None else None
    period = 1.0 / max(1.0, rate)
    deadline = time.monotonic() + timeout
    reached = False
    try:
        while time.monotonic() < deadline:
            current = _drive_follower_step(robot, target, step)
            if current and near_home(current, target, tol_deg=tol):
                reached = True
                break
            pause(period)
    finally:
        if cfg is not None:
            cfg.max_relative_target = saved_limit
    return reached
