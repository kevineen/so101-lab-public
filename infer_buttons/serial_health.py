"""Detect a dead follower serial handle and clear a stuck Feetech bus flag."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("infer_buttons")


def serial_fd_status(pid: int | None = None) -> tuple[bool, str]:
    """Return (ok, message). ``ok=False`` when an open ttyACM FD is deleted."""
    pid = int(pid or os.getpid())
    fd_dir = Path(f"/proc/{pid}/fd")
    if not fd_dir.is_dir():
        return True, ""
    try:
        entries = list(fd_dir.iterdir())
    except OSError:
        return True, ""
    saw_acm = False
    for entry in entries:
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if "ttyACM" not in target and "USB_Single_Serial" not in target:
            continue
        saw_acm = True
        if target.endswith("(deleted)") or " (deleted)" in target:
            return False, f"モータUSB切断（{target}）。推論クライアントを再起動してください。"
    if not saw_acm:
        # Port may still be opening; do not alarm yet.
        return True, ""
    return True, ""


def release_bus_port(bus: object) -> bool:
    """Clear scservo ``is_using`` so the next TX is not stuck on COMM_PORT_BUSY.

    The Feetech SDK sets ``port_handler.is_using`` for the duration of a packet.
    If a prior sync_read/write is interrupted or overlaps, the flag stays True and
    every later TX returns ``Port is in use!`` until something clears it — same
    recovery ``MotorsBus.disconnect`` / web_remote use.
    """
    port = getattr(bus, "port_handler", None)
    if port is None:
        return False
    try:
        port.is_using = False
        if getattr(port, "is_open", False):
            clear = getattr(port, "clearPort", None)
            if callable(clear):
                clear()
        return True
    except Exception:
        logger.debug("bus port release failed", exc_info=True)
        return False


def release_robot_bus(robot: object) -> bool:
    """Release the follower bus flag on ``robot.bus`` if present."""
    bus = getattr(robot, "bus", None)
    if bus is None:
        return False
    return release_bus_port(bus)


def is_port_busy_error(exc: BaseException) -> bool:
    """True when Feetech reports a stuck ``is_using`` / Port is in use."""
    text = str(exc)
    return "Port is in use" in text or "COMM_PORT_BUSY" in text
