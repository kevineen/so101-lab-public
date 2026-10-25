"""Main-PC sender: push teleop contract frames to the Pi bridge.

Sources:
- ``demo-bimanual``: left/right joint sinusoids (no Quest; end-to-end smoke)
- ``jsonl``: replay a file of contract JSON lines
- ``stdin``: one JSON object per line from stdin
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from .contract import SCHEMA_VERSION, TeleopCommand, parse_command

logger = logging.getLogger(__name__)


def _now_ns() -> int:
    return time.time_ns()


def make_joint_cmd(
    arm: str,
    joints: dict[str, float],
    *,
    gripper_unit: float | None = None,
    frame_id: str | None = None,
    valid: bool = True,
) -> TeleopCommand:
    """Build a joints-mode command (preferred for Phase D smoke tests)."""
    grip = gripper_unit
    if grip is None:
        # joints gripper is 0–100; contract field is 0–1
        grip = max(0.0, min(1.0, float(joints.get("gripper", 0.0)) / 100.0))
    return TeleopCommand(
        schema_version=SCHEMA_VERSION,
        timestamp_ns=_now_ns(),
        frame_id=frame_id or f"teleop_{arm}",
        arm=arm,
        ee_pose=None,
        gripper=grip,
        valid=valid,
        joints=dict(joints),
    )


def iter_bimanual_demo(
    hz: float,
    duration_s: float | None,
    *,
    left_home: dict[str, float] | None = None,
    right_home: dict[str, float] | None = None,
) -> Iterable[TeleopCommand]:
    """Generate slow mirrored sinusoids around the measured home pose.

    Absolute targets near 0° would yank parked arms through ``max_relative_target``
    clamps; always orbit the pose reported in the receiver ``hello`` message.
    """
    period = 1.0 / max(1.0, hz)
    zero = {
        "shoulder_pan": 0.0,
        "shoulder_lift": 0.0,
        "elbow_flex": 0.0,
        "wrist_flex": 0.0,
        "wrist_roll": 0.0,
        "gripper": 20.0,
    }
    left_home = dict(left_home or zero)
    right_home = dict(right_home or zero)
    t0 = time.monotonic()
    n = 0
    while True:
        t = time.monotonic() - t0
        if duration_s is not None and t >= duration_s:
            break
        # Tiny amplitudes; never command absolute zeros or joint-limit extremes.
        w = 2.0 * math.pi * 0.10 * t
        d_pan = 4.0 * math.sin(w)
        d_lift = 3.0 * math.sin(w + 0.7)
        d_elbow = 3.0 * math.sin(w + 1.4)
        d_wflex = 3.0 * math.sin(w + 2.1)
        d_wroll = 6.0 * math.sin(w + 2.8)
        d_grip = 4.0 * (0.5 + 0.5 * math.sin(w))

        def _around(home: dict[str, float], *, flip_pan_roll: bool) -> dict[str, float]:
            sign = -1.0 if flip_pan_roll else 1.0
            out = {
                "shoulder_pan": home["shoulder_pan"] + sign * d_pan,
                "shoulder_lift": home["shoulder_lift"] + d_lift,
                "elbow_flex": home["elbow_flex"] + d_elbow,
                "wrist_flex": home["wrist_flex"] + d_wflex,
                "wrist_roll": home["wrist_roll"] + sign * d_wroll,
                "gripper": home.get("gripper", 20.0) + d_grip,
            }
            # Soft clamp away from ±100° body limits (leave margin).
            for key in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex"):
                out[key] = max(-85.0, min(85.0, out[key]))
            out["wrist_roll"] = max(-170.0, min(170.0, out["wrist_roll"]))
            out["gripper"] = max(0.0, min(100.0, out["gripper"]))
            return out

        left = _around(left_home, flip_pan_roll=False)
        right = _around(right_home, flip_pan_roll=True)
        yield make_joint_cmd("left", left)
        yield make_joint_cmd("right", right)
        n += 1
        # Pace a left+right pair as one frame slot.
        target = t0 + n * period
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def iter_jsonl(path: Path) -> Iterable[TeleopCommand]:
    with path.open(encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                yield parse_command(line)
            except Exception as exc:  # noqa: BLE001
                logger.error("jsonl line %d: %s", line_no, exc)
                raise


def iter_stdin() -> Iterable[TeleopCommand]:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        yield parse_command(line)


async def _recv_hello(ws: Any, timeout_s: float = 2.0) -> dict[str, Any]:
    """Read the receiver welcome payload (current joint snapshots)."""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("type") != "hello":
        raise RuntimeError(f"expected hello from receiver, got: {raw!r:.200}")
    return data


async def request_go_home(ws: Any, *, timeout_s: float = 60.0) -> dict[str, Any]:
    """Ask Pi receiver to move arms to saved nest (Web Remote 初期位置)."""
    logger.info("Requesting nest go_home on Pi (Web Remote saved pose)…")
    await ws.send(json.dumps({"type": "go_home", "arm": "both", "timeout_s": timeout_s}))
    deadline = time.monotonic() + timeout_s + 20.0
    ack: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if not isinstance(msg, dict):
            continue
        kind = msg.get("type")
        if kind == "go_home_ack":
            logger.info("Pi accepted go_home — moving to nest…")
            continue
        if kind == "go_home":
            ack = msg
            break
        logger.warning("unexpected message during go_home: %s", msg)
    if ack is None:
        raise RuntimeError("go_home: no result from Pi (connection dropped?)")
    if not ack.get("ok"):
        raise RuntimeError(f"go_home failed: {ack}")
    for name, info in (ack.get("arms") or {}).items():
        src = info.get("source", "?")
        reached = info.get("reached")
        err = info.get("error")
        extra = f" error={err}" if err else ""
        logger.info("nest %s: source=%s reached=%s%s", name, src, reached, extra)
    missing = [a for a, ok in (ack.get("has_home") or {}).items() if not ok]
    if missing:
        logger.warning(
            "no saved nest for %s (using 0°/grip50). Save in Web Remote first.",
            missing,
        )
    return ack


def _arms_after_go_home(
    arms: dict[str, Any],
    ack: dict[str, Any],
) -> dict[str, Any]:
    """Prefer nest joint targets from go_home ack so demo orbits the nest."""
    out = dict(arms)
    for name, info in (ack.get("arms") or {}).items():
        joints = info.get("joints") if isinstance(info, dict) else None
        if isinstance(joints, dict) and joints:
            out[str(name)] = dict(joints)
    return out


async def send_stream(
    host: str,
    port: int,
    path: str,
    commands: Iterable[TeleopCommand] | None = None,
    *,
    hz: float | None = None,
    demo_bimanual: bool = False,
    duration: float | None = None,
    go_home: bool = False,
    go_home_timeout_s: float = 45.0,
) -> None:
    import websockets

    uri = f"ws://{host}:{port}{path}"
    logger.info("connecting %s", uri)
    async with websockets.connect(uri, max_size=2**20) as ws:
        logger.info("connected")
        hello = await _recv_hello(ws)
        arms = dict(hello.get("arms") or {})
        resolve = hello.get("resolve") or {}
        left_key = str(resolve.get("left", "follower"))
        right_key = str(resolve.get("right", "leader"))
        logger.info(
            "hello arms=%s has_home=%s supports_go_home=%s left_pan=%.1f right_pan=%.1f",
            list(arms),
            hello.get("has_home"),
            hello.get("supports_go_home"),
            float((arms.get(left_key) or {}).get("shoulder_pan", 0.0)),
            float((arms.get(right_key) or {}).get("shoulder_pan", 0.0)),
        )

        if go_home:
            if not hello.get("supports_go_home"):
                raise RuntimeError(
                    "Pi receiver is too old for go_home — pull so101-lab on Pi "
                    "and restart start_bridge_receiver.sh"
                )
            ack = await request_go_home(ws, timeout_s=go_home_timeout_s)
            arms = _arms_after_go_home(arms, ack)
            logger.info(
                "post go_home left_pan=%.1f right_pan=%.1f — starting stream",
                float((arms.get(left_key) or {}).get("shoulder_pan", 0.0)),
                float((arms.get(right_key) or {}).get("shoulder_pan", 0.0)),
            )

        if demo_bimanual:
            stream: Iterable[TeleopCommand] = iter_bimanual_demo(
                hz or 30.0,
                duration,
                left_home=arms.get(left_key),
                right_home=arms.get(right_key),
            )
            period = None  # demo paces itself
        else:
            if commands is None:
                raise ValueError("commands required unless demo_bimanual=True")
            stream = commands
            period = (1.0 / hz) if hz and hz > 0 else None

        for cmd in stream:
            t0 = time.monotonic()
            # Refresh timestamp on send so receiver timeout stays honest for replays.
            fresh = TeleopCommand(
                schema_version=cmd.schema_version,
                timestamp_ns=_now_ns(),
                frame_id=cmd.frame_id,
                arm=cmd.arm,
                ee_pose=cmd.ee_pose,
                gripper=cmd.gripper,
                valid=cmd.valid,
                joints=cmd.joints,
                mode=cmd.mode,
            )
            await ws.send(fresh.to_json())
            try:
                ack = await asyncio.wait_for(ws.recv(), timeout=1.0)
                logger.debug("ack %s", ack)
            except TimeoutError:
                logger.warning("no ack from receiver")
            if period is not None:
                await asyncio.sleep(max(0.0, period - (time.monotonic() - t0)))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SO-101 dual-arm teleop bridge sender (main PC)")
    p.add_argument("--host", required=True, help="Pi LAN IP")
    p.add_argument("--port", type=int, default=8870)
    p.add_argument("--path", default="/teleop")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo-bimanual", action="store_true", help="left/right joint sinusoid")
    src.add_argument("--jsonl", type=Path, help="replay contract JSON lines")
    src.add_argument("--stdin", action="store_true", help="read JSON lines from stdin")
    p.add_argument("--hz", type=float, default=30.0, help="send rate (demo / pacing)")
    p.add_argument("--duration", type=float, default=None, help="demo seconds (default: forever)")
    p.add_argument(
        "--go-home",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="On connect, ask Pi to move arms to saved nest before sending (default: on)",
    )
    p.add_argument(
        "--go-home-timeout",
        type=float,
        default=45.0,
        help="Seconds for nest approach on Pi",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    common = dict(
        go_home=bool(args.go_home),
        go_home_timeout_s=float(args.go_home_timeout),
    )
    try:
        if args.demo_bimanual:
            asyncio.run(
                send_stream(
                    args.host,
                    args.port,
                    args.path,
                    demo_bimanual=True,
                    hz=args.hz,
                    duration=args.duration,
                    **common,
                )
            )
        elif args.jsonl is not None:
            asyncio.run(
                send_stream(
                    args.host,
                    args.port,
                    args.path,
                    iter_jsonl(args.jsonl),
                    hz=args.hz,
                    **common,
                )
            )
        else:
            asyncio.run(
                send_stream(
                    args.host,
                    args.port,
                    args.path,
                    iter_stdin(),
                    hz=args.hz,
                    **common,
                )
            )
    except KeyboardInterrupt:
        logger.info("sender stopped")


if __name__ == "__main__":
    main()
