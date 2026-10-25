"""Pull Pi MJPEG streams and show them as Televiz XR quads (best-effort).

Runs in a daemon thread while ``live_quest`` owns CloudXR DeviceIO (headless).
If XR compositor creation fails, logs the Pi stream URLs for debugging.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .controls import TeleopControlsConfig


class QuestCameraPlanes:
    """Background OpenCV → Televiz quad publisher."""

    def __init__(self, cfg: TeleopControlsConfig) -> None:
        self.cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "idle"

    @property
    def status(self) -> str:
        return self._status

    def stream_urls(self) -> list[tuple[str, str]]:
        base = self.cfg.cameras_pi_base_url.rstrip("/") + "/"
        out: list[tuple[str, str]] = []
        for stream in self.cfg.camera_streams:
            if not stream.enabled:
                continue
            url = urljoin(base, f"api/stream/{stream.name}")
            out.append((stream.name, url))
        return out

    def start(self) -> None:
        if not self.cfg.cameras_enabled:
            self._status = "disabled"
            return
        urls = self.stream_urls()
        if not urls:
            self._status = "no_streams"
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="quest-camera-planes",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def _run(self) -> None:
        try:
            import cv2
            import cupy as cp
            import isaaccapture.viz as viz
            import numpy as np
        except ImportError as exc:
            self._status = f"import_error:{exc}"
            logger.warning("camera planes unavailable (%s); open Pi MJPEG in a browser", exc)
            for name, url in self.stream_urls():
                logger.info("camera %s → %s", name, url)
            return

        urls = self.stream_urls()
        caps: dict[str, cv2.VideoCapture] = {}
        for name, url in urls:
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                logger.warning("could not open camera stream %s (%s)", name, url)
                continue
            caps[name] = cap
            logger.info("camera stream open: %s", url)

        if not caps:
            self._status = "no_open_streams"
            return

        try:
            session_cfg = viz.VizSessionConfig()
            session_cfg.mode = viz.DisplayMode.kXr
            session_cfg.app_name = "So101QuestCameras"
            session = viz.VizSession.create(session_cfg)
        except Exception as exc:  # noqa: BLE001
            self._status = f"viz_create_failed:{exc}"
            logger.warning(
                "Televiz XR session failed (%s). Cameras still on Pi: %s",
                exc,
                ", ".join(u for _, u in urls),
            )
            for cap in caps.values():
                cap.release()
            return

        layers: dict[str, object] = {}
        try:
            for name in caps:
                place = self.cfg.camera_placements.get(name)
                layer_cfg = viz.QuadLayerConfig()
                layer_cfg.name = name
                layer_cfg.resolution = viz.Resolution(640, 480)
                layer_cfg.openxr_composition = True
                placement = viz.QuadLayerPlacement()
                placement.size_meters = (0.55, 0.41)
                pose = viz.Pose3D()
                # Head-relative-ish billboard in front of the user
                dist = place.distance_m if place else 1.5
                yaw = math.radians(place.yaw_deg if place else 0.0)
                pitch = math.radians(place.pitch_deg if place else -5.0)
                x_off = place.x_m if place else 0.0
                pose.position = (
                    x_off + dist * math.sin(yaw),
                    dist * math.sin(pitch),
                    -dist * math.cos(yaw),
                )
                # Identity orientation — runtime faces the quad toward the viewer for quads
                pose.orientation = (0.0, 0.0, 0.0, 1.0)
                placement.pose = pose
                layer_cfg.placement = placement
                layers[name] = session.add_quad_layer(layer_cfg)

            self._status = "running"
            logger.info("Televiz camera planes running (%d)", len(layers))

            while not self._stop.is_set():
                for name, cap in caps.items():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        continue
                    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                    if rgba.shape[0] != 480 or rgba.shape[1] != 640:
                        rgba = cv2.resize(rgba, (640, 480))
                    gpu = cp.asarray(rgba)
                    layers[name].submit(gpu)  # type: ignore[attr-defined]
                session.render()
                time.sleep(1.0 / 15.0)
        except Exception as exc:  # noqa: BLE001
            self._status = f"error:{exc}"
            logger.exception("camera plane loop failed")
        finally:
            try:
                session.destroy()
            except Exception:
                logger.debug("VizSession destroy failed", exc_info=True)
            for cap in caps.values():
                cap.release()
            if self._status == "running":
                self._status = "stopped"
