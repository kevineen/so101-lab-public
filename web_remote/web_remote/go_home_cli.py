"""Standalone: move SO-101 arms to the saved nest pose (no Web Remote server).

Used after MolmoAct2 robot_client exits, or anytime Web Remote is stopped.
Shares ``~/.cache/so101-lab/home_poses.json`` with the Web UI.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, JOINT_KEYS, build_web_remote_config
from .drive_profile import apply_body_acceleration
from .home_pose import DEFAULT_HOME_PATH, joints_for_arm, near_home

logger = logging.getLogger(__name__)


def _approach(
    robot: object,
    target: dict[str, float],
    *,
    timeout_s: float,
    tol_deg: float,
    step_deg: float,
    hz: float,
) -> bool:
    """Repeatedly send_action until near home or timeout."""
    robot.config.max_relative_target = float(step_deg)  # type: ignore[attr-defined]
    deadline = time.monotonic() + timeout_s
    period = 1.0 / max(1.0, hz)
    action = {f"{k}.pos": float(v) for k, v in target.items()}
    while time.monotonic() < deadline:
        robot.send_action(action)  # type: ignore[attr-defined]
        obs = robot.get_observation()  # type: ignore[attr-defined]
        current = {
            key: float(obs[f"{key}.pos"])
            for key in JOINT_KEYS
            if f"{key}.pos" in obs and isinstance(obs[f"{key}.pos"], (int, float))
        }
        if near_home(current, target, tol_deg=tol_deg):
            return True
        time.sleep(period)
    return False


def _approach_lift_first(
    robot: object,
    target: dict[str, float],
    *,
    timeout_s: float,
    tol_deg: float,
    step_deg: float,
    hz: float,
) -> bool:
    """Raise shoulder_lift (motor 2) first, then the full nest pose."""
    from so101_common.nest_stages import LIFT_JOINT, joints_from_observation, lift_then_all_targets

    obs = robot.get_observation()  # type: ignore[attr-defined]
    current = joints_from_observation(obs)
    lift_only, full = lift_then_all_targets(current, target, lift_joint=LIFT_JOINT)
    # Spend up to half the budget on the lift; remainder on the full pose.
    lift_budget = max(5.0, timeout_s * 0.45)
    rest_budget = max(5.0, timeout_s - lift_budget)
    logger.info("Homing phase 1/2: %s → nest (hold other joints)", LIFT_JOINT)
    ok_lift = _approach(
        robot,
        lift_only,
        timeout_s=lift_budget,
        tol_deg=tol_deg,
        step_deg=step_deg,
        hz=hz,
    )
    if not ok_lift:
        logger.warning("Lift phase timed out; continuing to full nest")
    logger.info("Homing phase 2/2: full nest pose")
    return _approach(
        robot,
        full,
        timeout_s=rest_budget,
        tol_deg=tol_deg,
        step_deg=step_deg,
        hz=hz,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Move SO-101 to saved nest / home pose")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p.add_argument("--home-file", type=Path, default=DEFAULT_HOME_PATH)
    p.add_argument("--follower-id", default="my_follower")
    p.add_argument("--leader-id", default="my_leader_drive")
    p.add_argument("--no-leader", action="store_true")
    p.add_argument("--arm", choices=("follower", "leader"), default=None, help="one arm only")
    p.add_argument("--timeout", type=float, default=45.0)
    p.add_argument("--tol", type=float, default=2.5)
    p.add_argument(
        "--step",
        type=float,
        default=None,
        help="max deg per control tick (default: drive_profile for that arm)",
    )
    p.add_argument("--hz", type=float, default=20.0)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from lerobot.robots.so_follower import SO101Follower

    bundle = build_web_remote_config(
        args.config,
        follower_id=args.follower_id,
        leader_id=args.leader_id,
        enable_leader=not args.no_leader,
    )
    names = [args.arm] if args.arm else list(bundle.arms)
    robots: list[tuple[str, SO101Follower]] = []

    try:
        for name in names:
            cfg = bundle.arms[name]
            profile = bundle.drive_profiles.get(name)
            step = (
                float(args.step)
                if args.step is not None
                else (profile.effective_step(5.0, homing=True) if profile else 5.0)
            )
            cfg.disable_torque_on_disconnect = False
            cfg.max_relative_target = step
            logger.info(
                "Connecting %r on %s (drive_profile=%s step=%.2f°) ...",
                name,
                cfg.port,
                profile.name if profile else "full",
                step,
            )
            robot = SO101Follower(cfg)
            robot.connect(calibrate=False)
            if profile is not None:
                apply_body_acceleration(robot, profile)
            target, from_file = joints_for_arm(name, path=args.home_file)
            src = "file" if from_file else "default(0°/grip50)"
            logger.info("Homing %r from %s → %s", name, src, {k: round(v, 1) for k, v in target.items()})
            ok = _approach_lift_first(
                robot,
                target,
                timeout_s=args.timeout,
                tol_deg=args.tol,
                step_deg=step,
                hz=args.hz,
            )
            if ok:
                logger.info("Arm %r reached nest pose", name)
            else:
                logger.warning("Arm %r timed out approaching nest (holding last command)", name)
            robots.append((name, robot))
    finally:
        for name, robot in robots:
            try:
                if robot.is_connected:
                    robot.disconnect()
                    logger.info("Disconnected %r (torque left ON)", name)
            except Exception:
                logger.exception("disconnect failed for %r", name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
