"""Trial clock and scoreboard for the phone infer page."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field


FAILURE_KINDS = ("no_reach", "no_grasp", "no_place", "disturb")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


@dataclass
class InferStatus:
    """Shared trial counters. The control loop is the only writer of the clock."""

    model: str = ""
    policy_type: str = ""
    task: str = ""
    model_id: str = ""
    model_label: str = ""
    model_index: int = 0
    model_count: int = 0
    switching: bool = False
    # Model-load progress (phone UI while policy_server reloads weights).
    load_phase: str = ""  # prepare | send | wait_server | done | error | ""
    load_message: str = ""
    load_target: str = ""
    load_pct: int = 0  # 0–100; approximate when the server gives no real %
    _load_started: float | None = None
    # Nest approach status (ready-phase hold).
    nest_phase: str = ""  # lift | all | ""
    nest_message: str = ""
    nest_ok: bool = True
    # Serial / bus health (USB re-enumeration leaves a deleted ttyACM FD).
    serial_ok: bool = True
    serial_message: str = ""
    # Short-lived hint after phone "バス復旧" (cleared by tick_bus).
    bus_message: str = ""
    _bus_message_until: float | None = None
    total_trials: int = 10
    timeout_s: float = 60.0
    trial: int = 0
    successes: int = 0
    failures: dict[str, int] = field(default_factory=lambda: {k: 0 for k in FAILURE_KINDS})
    last_result: str = ""
    _run_started: float | None = None
    _elapsed_paused: float = 0.0
    _pause_started: float | None = None

    @classmethod
    def from_environ(cls, *, model: str = "", policy_type: str = "", task: str = "") -> InferStatus:
        return cls(
            model=model or os.environ.get("SO101_INFER_MODEL", ""),
            policy_type=policy_type or os.environ.get("SO101_INFER_POLICY_TYPE", ""),
            task=task or os.environ.get("SO101_INFER_TASK", ""),
            total_trials=env_int("SO101_INFER_TRIALS", 10),
            timeout_s=env_float("SO101_INFER_TIMEOUT_S", 60.0),
        )

    def begin_trial(self) -> None:
        self.trial += 1
        self.last_result = ""
        self._elapsed_paused = 0.0
        self._pause_started = None
        self._run_started = time.monotonic()

    def set_paused(self, paused: bool) -> None:
        if paused:
            if self._pause_started is None and self._run_started is not None:
                self._pause_started = time.monotonic()
            return
        if self._pause_started is not None:
            self._elapsed_paused += time.monotonic() - self._pause_started
            self._pause_started = None

    def elapsed_s(self) -> float:
        if self._run_started is None:
            return 0.0
        now = time.monotonic()
        paused = self._elapsed_paused
        if self._pause_started is not None:
            paused += now - self._pause_started
        return max(0.0, now - self._run_started - paused)

    def timed_out(self) -> bool:
        return self.timeout_s > 0 and self.elapsed_s() >= self.timeout_s

    def note_success(self) -> None:
        self.successes += 1
        self.last_result = "success"
        self._run_started = None
        self._pause_started = None

    def note_failure(self, kind: str) -> None:
        if kind not in FAILURE_KINDS:
            kind = "disturb"
        self.failures[kind] = int(self.failures.get(kind, 0)) + 1
        self.last_result = kind
        self._run_started = None
        self._pause_started = None

    def undo_last(self) -> bool:
        """Revert the most recent success/failure and free that trial slot.

        Returns False when there is nothing to undo.
        """
        if not self.last_result:
            return False
        if self.last_result == "success":
            self.successes = max(0, self.successes - 1)
        elif self.last_result in FAILURE_KINDS:
            kind = self.last_result
            self.failures[kind] = max(0, int(self.failures.get(kind, 0)) - 1)
        else:
            return False
        self.last_result = ""
        self.trial = max(0, self.trial - 1)
        self._run_started = None
        self._pause_started = None
        return True

    def reset_scores(self) -> None:
        """Clear trial tallies when the phone switches models."""
        self.trial = 0
        self.successes = 0
        self.failures = {k: 0 for k in FAILURE_KINDS}
        self.last_result = ""
        self._run_started = None
        self._pause_started = None
        self._elapsed_paused = 0.0

    def set_model(
        self,
        *,
        model: str,
        policy_type: str,
        model_id: str = "",
        model_label: str = "",
        model_index: int = 0,
        model_count: int = 0,
    ) -> None:
        self.model = model
        self.policy_type = policy_type
        self.model_id = model_id
        self.model_label = model_label
        self.model_index = model_index
        self.model_count = model_count

    def begin_load(self, target: str) -> None:
        """Mark the start of a policy-server weight reload."""
        self.switching = True
        self.load_target = target
        self.load_phase = "prepare"
        self.load_message = "切替準備中…"
        self.load_pct = 5
        self._load_started = time.monotonic()

    def set_load(self, phase: str, message: str, pct: int) -> None:
        self.load_phase = phase
        self.load_message = message
        self.load_pct = max(0, min(100, int(pct)))

    def end_load(self, *, ok: bool, message: str = "") -> None:
        if ok:
            self.load_phase = "done"
            self.load_message = message or "読み込み完了"
            self.load_pct = 100
        else:
            self.load_phase = "error"
            self.load_message = message or "読み込み失敗"
            self.load_pct = 0
        self.switching = False
        # Keep the banner briefly; clear timer so elapsed freezes at final value.
        # Caller may clear_load() after a short delay; phone also clears when not switching.

    def clear_load(self) -> None:
        self.load_phase = ""
        self.load_message = ""
        self.load_target = ""
        self.load_pct = 0
        self._load_started = None

    def set_nest(self, *, phase: str = "", message: str = "", ok: bool = True) -> None:
        self.nest_phase = phase
        self.nest_message = message
        self.nest_ok = bool(ok)

    def clear_nest(self) -> None:
        self.nest_phase = ""
        self.nest_message = ""
        self.nest_ok = True

    def set_serial(self, *, ok: bool, message: str = "") -> None:
        self.serial_ok = bool(ok)
        self.serial_message = message if not ok else ""

    def note_bus(self, message: str, *, hold_s: float = 4.0) -> None:
        """Show a transient bus-recovery hint on the phone."""
        self.bus_message = message
        self._bus_message_until = time.monotonic() + max(0.5, float(hold_s))

    def tick_bus(self) -> None:
        if self._bus_message_until is None:
            return
        if time.monotonic() >= self._bus_message_until:
            self.bus_message = ""
            self._bus_message_until = None

    def load_elapsed_s(self) -> float:
        if self._load_started is None:
            return 0.0
        return max(0.0, time.monotonic() - self._load_started)

    def public(self) -> dict:
        loading = bool(self.switching) or bool(self.load_phase)
        # While waiting on the server, nudge the bar slowly so the phone looks alive.
        pct = self.load_pct
        if self.switching and self.load_phase == "wait_server":
            elapsed = self.load_elapsed_s()
            # Cap at 92% until the RPC returns.
            pct = max(pct, min(92, 30 + int(elapsed * 2)))
        return {
            "model": self.model,
            "policy_type": self.policy_type,
            "task": self.task,
            "model_id": self.model_id,
            "model_label": self.model_label,
            "model_index": self.model_index,
            "model_count": self.model_count,
            "switching": self.switching,
            "loading": loading,
            "load_phase": self.load_phase,
            "load_message": self.load_message,
            "load_target": self.load_target,
            "load_pct": pct,
            "load_elapsed_s": round(self.load_elapsed_s(), 1),
            "nest_phase": self.nest_phase,
            "nest_message": self.nest_message,
            "nest_ok": self.nest_ok,
            "serial_ok": self.serial_ok,
            "serial_message": self.serial_message,
            "bus_message": self.bus_message,
            "trial": self.trial,
            "total": self.total_trials,
            "successes": self.successes,
            "failures": dict(self.failures),
            "last_result": self.last_result,
            "can_undo": bool(self.last_result),
            "elapsed_s": round(self.elapsed_s(), 1),
            "limit_s": self.timeout_s,
        }
