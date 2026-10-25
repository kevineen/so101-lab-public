"""Poll quest_teleop.yaml (+ overrides) and push hot-reloads into the receiver."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from .controls import load_teleop_config, overrides_path_for
from .ik import RelativeEeIk
from .safety import SoftLimits

logger = logging.getLogger(__name__)


class TeleopConfigWatcher:
    """Background mtime watcher for soft_limits / axis_map / pos_scale."""

    def __init__(
        self,
        config_path: Path,
        *,
        apply: Callable[[object], None],
        interval_s: float = 1.0,
    ) -> None:
        self.config_path = Path(config_path)
        self.overrides_path = overrides_path_for(self.config_path)
        self.apply = apply
        self.interval_s = float(interval_s)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stamp = self._current_stamp()

    def _current_stamp(self) -> tuple[float, float]:
        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime if path.is_file() else 0.0
            except OSError:
                return 0.0

        return _mtime(self.config_path), _mtime(self.overrides_path)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="teleop-config-watch", daemon=True)
        self._thread.start()
        logger.info(
            "watching teleop config %s (+ %s)",
            self.config_path,
            self.overrides_path.name,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            stamp = self._current_stamp()
            if stamp == self._stamp:
                continue
            self._stamp = stamp
            try:
                cfg = load_teleop_config(self.config_path)
                self.apply(cfg)
                logger.info(
                    "reloaded teleop config pos_scale=%.2f axis_map=%s soft=%s",
                    cfg.pos_scale,
                    cfg.axis_map,
                    cfg.soft_limits.enabled,
                )
            except Exception:
                logger.exception("teleop config reload failed")


def apply_teleop_runtime(receiver: object, cfg: object) -> None:
    """Push motion/safety fields into a running BridgeReceiver."""
    soft: SoftLimits = getattr(cfg, "soft_limits")
    setattr(receiver, "soft_limits", soft)
    ik = getattr(receiver, "ik", None)
    if isinstance(ik, RelativeEeIk):
        ik.update_runtime(
            pos_scale=float(getattr(cfg, "pos_scale")),
            axis_map=dict(getattr(cfg, "axis_map")),
            soft_limits=soft,
        )
