"""Episode count and record clock for the phone page.

``lerobot-record`` ends an episode when ``time.perf_counter()`` inside
``record_loop`` reaches ``episode_time_s``. Replacing that module's
``time.perf_counter`` with :meth:`PauseClock.perf_counter` freezes the
budget while the phone is paused. The control loop keeps its own clock,
so the arm still follows the leader.
"""

from __future__ import annotations

import threading
import time

_DEFAULT_EPISODES = 50
_DEFAULT_EPISODE_S = 60.0
_DEFAULT_RESET_S = 60.0

_LIMIT_FLAGS = {
    "--dataset.num_episodes": "num_episodes",
    "--dataset.episode_time_s": "episode_time_s",
    "--dataset.reset_time_s": "reset_time_s",
}


def _parse_float(text: str, fallback: float) -> float:
    try:
        return float(text)
    except ValueError:
        return fallback


def dataset_limits_from_argv(argv: list[str]) -> tuple[int, float, float]:
    """Read the episode budget from ``lerobot-record`` CLI flags.

    The decorated ``record()`` parses those flags inside a closure, so the
    phone hook never sees the config object. Both ``--flag=value`` and
    ``--flag value`` are accepted. Anything else stays at the LeRobot default.
    """
    found = {
        "num_episodes": float(_DEFAULT_EPISODES),
        "episode_time_s": _DEFAULT_EPISODE_S,
        "reset_time_s": _DEFAULT_RESET_S,
    }
    index = 0
    while index < len(argv):
        token = argv[index]
        for flag, name in _LIMIT_FLAGS.items():
            if token.startswith(flag + "="):
                found[name] = _parse_float(token.split("=", 1)[1], found[name])
                break
            if token == flag and index + 1 < len(argv):
                found[name] = _parse_float(argv[index + 1], found[name])
                index += 1
                break
        index += 1
    episodes = int(found["num_episodes"])
    if episodes < 0:
        episodes = _DEFAULT_EPISODES
    return episodes, found["episode_time_s"], found["reset_time_s"]


class PauseClock:
    """``perf_counter`` that stands still while ``events['paused']`` is set."""

    def __init__(self, holder: dict) -> None:
        self._holder = holder
        self._real = time.perf_counter
        self._paused_total = 0.0
        self._mark: float | None = None
        self._lock = threading.Lock()

    def perf_counter(self) -> float:
        """Monotonic time minus every interval spent paused."""
        now = self._real()
        with self._lock:
            paused = self._is_paused()
            if paused and self._mark is None:
                self._mark = now
            elif not paused and self._mark is not None:
                self._paused_total += now - self._mark
                self._mark = None
            held = (now - self._mark) if self._mark is not None else 0.0
            return now - self._paused_total - held

    def _is_paused(self) -> bool:
        events = self._holder.get("events")
        return bool(events and events.get("paused"))


class _TimeProxy:
    """Stand-in for the ``time`` module that only redirects ``perf_counter``."""

    is_pause_proxy = True

    def __init__(self, real: object, clock: PauseClock) -> None:
        self._real = real
        self._clock = clock

    def __getattr__(self, name: str):
        if name == "perf_counter":
            return self._clock.perf_counter
        return getattr(self._real, name)


def install_pause_clock(record_mod: object, clock: PauseClock) -> None:
    """Point ``lerobot_record.time.perf_counter`` at ``clock`` when that module is real."""
    real = getattr(record_mod, "time", None)
    if real is None or not hasattr(real, "perf_counter"):
        return
    if getattr(real, "is_pause_proxy", False):
        return
    setattr(record_mod, "time", _TimeProxy(real, clock))


class RecordStatus:
    """Saved-episode count and the clock the phone displays for this take."""

    def __init__(self, clock: PauseClock) -> None:
        self.clock = clock
        self.dataset: object | None = None
        self.total = 0
        self.episode_time_s = 0.0
        self.reset_time_s = 0.0
        self.saved = 0
        self.episode = 0
        self.limit_s = 0.0
        self._origin: float | None = None
        self._running = False
        self._frozen = 0.0
        self._lock = threading.Lock()

    def configure(self, total: int, episode_time_s: float, reset_time_s: float) -> None:
        with self._lock:
            self.total = total
            self.episode_time_s = episode_time_s
            self.reset_time_s = reset_time_s

    def current_saved(self) -> int:
        """Episodes already stored on the dataset, or the last value we published."""
        dataset = self.dataset
        value = getattr(dataset, "num_episodes", None) if dataset is not None else None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        with self._lock:
            return self.saved

    def note_saved(self, saved: int) -> None:
        with self._lock:
            self.saved = saved

    def show_take(self, saved: int, *, running: bool, limit_s: float) -> None:
        """Publish take ``saved + 1``. ``running`` starts the on-screen clock."""
        with self._lock:
            self.saved = saved
            self.episode = saved + 1
            self.limit_s = limit_s
            self._frozen = 0.0
            self._running = running
            self._origin = self.clock.perf_counter() if running else None

    def show_reset(self, saved: int, limit_s: float) -> None:
        """Reset still belongs to the take that has not been saved yet."""
        self.show_take(saved, running=True, limit_s=limit_s)

    def freeze(self) -> None:
        """Keep the last elapsed value after the vendor loop returns."""
        with self._lock:
            if self._running and self._origin is not None:
                self._frozen = max(0.0, self.clock.perf_counter() - self._origin)
            self._running = False
            self._origin = None

    def public(self) -> dict:
        with self._lock:
            elapsed = self._frozen
            if self._running and self._origin is not None:
                elapsed = max(0.0, self.clock.perf_counter() - self._origin)
            return {
                "episode": self.episode,
                "saved": self.saved,
                "total": self.total,
                "elapsed_s": elapsed,
                "limit_s": self.limit_s,
            }
