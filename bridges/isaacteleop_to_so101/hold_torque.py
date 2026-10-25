"""Re-enable torque and hold measured pose on both SO-101 arms.

Run after a limp/drop. Exit with Ctrl+C leaves torque ON
(``disable_torque_on_disconnect=False``).

接続・計測姿勢の保持は :mod:`so101_common.connection` の共通実装を使う。
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

from so101_common.connection import connect_follower, measured_position_action

from .arms import DEFAULT_CONFIG_PATH, load_dual_arm_config

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_path = Path(os.environ.get("BRIDGE_CONFIG", str(DEFAULT_CONFIG_PATH)))
    bundle = load_dual_arm_config(config_path)

    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    robots: list[tuple[str, SO101Follower]] = []

    def shutdown(*_args: object) -> None:
        logger.info("exit: closing buses with torque left ON")
        for name, robot in robots:
            try:
                if robot.is_connected:
                    robot.disconnect()
                    logger.info("arm %r disconnected (torque still enabled)", name)
            except Exception:
                logger.exception("disconnect failed for %r", name)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for name, phys in bundle.arms.items():
        cfg = SO101FollowerConfig(
            port=phys.port,
            id=phys.robot_id,
            cameras={},
            max_relative_target=5.0,
            use_degrees=True,
            disable_torque_on_disconnect=False,
        )
        logger.info("Connecting %r on %s ...", name, phys.port)
        robot = connect_follower(cfg)

        action = measured_position_action(robot)
        robot.send_action(action)
        robots.append((name, robot))
        logger.info(
            "Holding %r at %s",
            name,
            {k: round(v, 1) for k, v in action.items()},
        )

    logger.info("Torque ON on %d arm(s). Ctrl+C to exit (torque stays on).", len(robots))
    while True:
        for name, robot in robots:
            try:
                robot.send_action(measured_position_action(robot))
            except Exception:
                logger.exception("hold tick failed for %r", name)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
