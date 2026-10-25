"""Small JPEG samples of the episode being recorded, for the phone review page.

The control loop only copies a frame every few ticks. Depth colorization and
JPEG encoding run on a side thread so the 30 Hz loop does not wait on OpenCV.

RealSense depth (``*_depth``, mm as uint16) is colorized so the phone can
show it next to RGB. When a depth twin exists, its RGB sibling is omitted
from the preview so the D435 tile reads as depth.
"""

from __future__ import annotations

import re
import threading

_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
_MAX_SAMPLES = 12
_SAMPLE_EVERY = 8
# Live view: copy on the control thread, colorize+JPEG on the side thread.
# Every 10th observation (~3 Hz at 30 Hz) is enough for the phone tile.
_LIVE_EVERY = 10
# Lab table ~0.3–3 m; farther depths share the max color.
_MAX_DEPTH_MM = 3000.0
_DEPTH_SUFFIX = "_depth"


def camera_name(key: object) -> str:
    """Last segment of a feature key, or empty when it is not a safe path token."""
    if not isinstance(key, str) or not key:
        return ""
    name = key.rsplit(".", 1)[-1]
    if _NAME_RE.fullmatch(name) is None:
        return ""
    return name


def _rgb_uint8(value: object):
    """Return an HWC uint8 RGB array, or None when the value is not a color frame."""
    try:
        import numpy as np
    except ImportError:
        return None
    arr = np.asarray(value)
    if arr.ndim == 3 and arr.shape[0] in (1, 3) and arr.shape[-1] not in (1, 3, 4):
        arr = np.transpose(arr, (1, 2, 0))
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8:
        return None
    return np.ascontiguousarray(arr)


def _depth_mm(value: object):
    """Return a contiguous depth map (HxW), or None when it is not depth."""
    try:
        import numpy as np
    except ImportError:
        return None
    arr = np.asarray(value)
    if arr.ndim == 3 and arr.shape[0] == 1 and arr.shape[-1] != 1:
        arr = np.transpose(arr, (1, 2, 0))
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[..., 0]
    if arr.ndim != 2 or arr.size == 0:
        return None
    if arr.dtype != np.uint16 and not np.issubdtype(arr.dtype, np.floating):
        return None
    return np.ascontiguousarray(arr)


def colorize_depth_mm(value: object, *, max_mm: float = _MAX_DEPTH_MM):
    """Turn a depth map (mm) into HWC uint8 RGB, or None when it is not depth."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    arr = _depth_mm(value)
    if arr is None:
        return None
    valid = arr > 0
    scaled = np.zeros(arr.shape, dtype=np.uint8)
    if valid.any() and max_mm > 0:
        clipped = np.clip(arr.astype(np.float32), 0.0, float(max_mm))
        scaled = (clipped / float(max_mm) * 255.0).astype(np.uint8)
    bgr = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    bgr[~valid] = 0
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def preview_sources_from_mapping(frame: object) -> dict[str, object]:
    """Copy raw preview frames for the encode thread (no OpenCV / colorize).

    Depth stays as mm maps. When ``front_depth`` is present, ``front`` is dropped.
    """
    if not isinstance(frame, dict):
        return {}
    images: dict[str, object] = {}
    for key, value in frame.items():
        name = camera_name(key)
        if not name:
            continue
        if name.endswith(_DEPTH_SUFFIX):
            arr = _depth_mm(value)
        else:
            arr = _rgb_uint8(value)
        if arr is None:
            continue
        images[name] = arr.copy()
    for name in list(images):
        if name.endswith(_DEPTH_SUFFIX):
            images.pop(name[: -len(_DEPTH_SUFFIX)], None)
    return images


def materialize_preview_images(sources: dict[str, object] | None) -> dict[str, object]:
    """Colorize depth sources into RGB for JPEG encoding."""
    if not sources:
        return {}
    images: dict[str, object] = {}
    for name, value in sources.items():
        if name.endswith(_DEPTH_SUFFIX):
            rgb = colorize_depth_mm(value)
        else:
            rgb = _rgb_uint8(value)
        if rgb is None:
            continue
        images[name] = rgb
    return images


def images_from_mapping(frame: object) -> dict[str, object]:
    """Copy previewable frames and colorize depth (for tests / offline use)."""
    return materialize_preview_images(preview_sources_from_mapping(frame))


def encode_jpeg(rgb) -> bytes:
    """Downscale an RGB frame to a JPEG. Empty bytes when OpenCV cannot encode it."""
    try:
        import cv2
    except ImportError:
        return b""
    height, width = rgb.shape[:2]
    if width > 320:
        scaled = max(1, int(height * (320 / width)))
        rgb = cv2.resize(rgb, (320, scaled), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        return b""
    return buf.tobytes()


def _encode_images(sources: dict | None) -> dict[str, bytes]:
    """Colorize (if needed) and JPEG-encode a camera map."""
    encoded: dict[str, bytes] = {}
    for name, rgb in materialize_preview_images(sources).items():
        blob = encode_jpeg(rgb)
        if blob:
            encoded[name] = blob
    return encoded


class FramePreview:
    """Latest sampled JPEGs for one episode. ``clear`` at the start of each take."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._pending: dict[str, object] | None = None
        self._live_pending: dict[str, object] | None = None
        self._live: dict[str, bytes] = {}
        self._live_seq = 0
        self._obs_count = 0
        self._samples: list[dict[str, bytes]] = []
        self._generation = 0
        self.frame_count = 0
        self.hooked = False
        self._closed = False
        self._thread = threading.Thread(target=self._encode_loop, name="record-preview", daemon=True)
        self._thread.start()

    def clear(self) -> None:
        """Drop samples from the previous take."""
        with self._lock:
            self._generation += 1
            self.frame_count = 0
            self._samples.clear()
            self._pending = None

    def note(self, frame: dict) -> None:
        """Count one recorded frame and, every few frames, queue a JPEG sample."""
        with self._lock:
            self.frame_count += 1
            count = self.frame_count
        if count % _SAMPLE_EVERY != 1:
            return
        images = preview_sources_from_mapping(frame)
        if not images:
            return
        with self._lock:
            # Keep the newest unread sample. The control loop must not wait.
            self._pending = images
        self._wake.set()

    def note_observation(self, obs: object) -> None:
        """Queue a live JPEG from ``robot.get_observation`` without writing the dataset."""
        with self._lock:
            self._obs_count += 1
            count = self._obs_count
        if count % _LIVE_EVERY != 1:
            return
        images = preview_sources_from_mapping(obs)
        if not images:
            return
        with self._lock:
            self._live_pending = images
        self._wake.set()

    def info(self) -> dict:
        """Frame count, review samples, and the cameras available for the live view."""
        with self._lock:
            review: list[str] = []
            if self._samples:
                review = list(self._samples[-1].keys())
            live = list(self._live.keys())
            return {
                "frames": self.frame_count,
                "samples": len(self._samples),
                "cameras": live or review,
                "review_cameras": review,
                "live_seq": self._live_seq,
            }

    def jpeg(self, camera: str, index: int) -> bytes | None:
        """One sampled JPEG, or None when the index or camera is absent."""
        if _NAME_RE.fullmatch(camera) is None:
            return None
        with self._lock:
            if index < 0 or index >= len(self._samples):
                return None
            return self._samples[index].get(camera)

    def live_jpeg(self, camera: str) -> bytes | None:
        """Latest live JPEG for one camera, or None when that camera has no frame yet."""
        if _NAME_RE.fullmatch(camera) is None:
            return None
        with self._lock:
            return self._live.get(camera)

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    def _encode_loop(self) -> None:
        while not self._closed:
            self._wake.wait()
            self._wake.clear()
            if self._closed:
                return
            with self._lock:
                pending = self._pending
                live = self._live_pending
                self._pending = None
                self._live_pending = None
                generation = self._generation
            if not pending and not live:
                continue
            encoded_sample = _encode_images(pending) if pending else {}
            encoded_live = encoded_sample if live is pending and encoded_sample else _encode_images(live)
            if not encoded_sample and not encoded_live:
                continue
            with self._lock:
                if encoded_live:
                    self._live = encoded_live
                    self._live_seq += 1
                if encoded_sample and generation == self._generation:
                    self._samples.append(encoded_sample)
                    del self._samples[:-_MAX_SAMPLES]
