"""SO-101 フォロワーの接続・保持（トルク ON）・切断の共通イディオム。

かつて bridges/hold_torque.py と bridges/receiver.py に重複していた:
- リトライ付き connect（bus が半開のまま残る場合の後始末つき）
- 計測姿勢で固めてから ``disable_torque_on_disconnect=False`` のまま切断
  （Ctrl+C で脱力落下させない）

lerobot は遅延 import（so101_common は lerobot 無しでも import 可能にする）。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

logger = logging.getLogger(__name__)


def connect_follower(
    cfg: "SO101FollowerConfig",
    *,
    attempts: int = 4,
    pause_s: float = 0.8,
) -> "SO101Follower":
    """リトライ付きでフォロワに接続する。全失敗時は最後の例外を送出。

    失敗した試行では bus が残らないよう明示的に disconnect する
    （半開の bus が次の接続を妨げるのを防ぐ）。
    """
    from lerobot.robots.so_follower import SO101Follower

    robot = SO101Follower(cfg)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            robot.connect(calibrate=False)
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("connect attempt %d/%d failed: %s", attempt, attempts, exc)
            try:
                if getattr(getattr(robot, "bus", None), "is_connected", False):
                    robot.bus.disconnect()
                elif robot.is_connected:
                    robot.disconnect()
            except Exception:  # noqa: BLE001
                logger.debug("cleanup after failed connect", exc_info=True)
            robot = SO101Follower(cfg)
            time.sleep(pause_s)
    if last_exc is not None:
        raise last_exc
    return robot


def measured_position_action(robot: "SO101Follower") -> dict[str, Any]:
    """現在計測される関節角を ``send_action`` 可能な形（``*.pos``）で返す。"""
    obs = robot.get_observation()
    return {
        k: float(v) for k, v in obs.items() if isinstance(k, str) and k.endswith(".pos")
    }


def hold_and_disconnect(robot: "SO101Follower", *, settle_s: float = 0.05) -> None:
    """計測姿勢に固めてから切断（トルクはクリアしない = 脱力しない）。

    ``SO101FollowerConfig(disable_torque_on_disconnect=False)`` と組み合わせて
    使う。例外は呼び出し側の責務でハンドリングしない（ここでは投げる）。
    """
    robot.send_action(measured_position_action(robot))
    time.sleep(settle_s)
    robot.disconnect()
