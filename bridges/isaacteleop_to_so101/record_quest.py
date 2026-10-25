"""Phase C: Quest / CloudXR → contract JSONL (main PC, no Pi).

Requires ``isaaccapture`` (teleop venv). Example::

    PYTHONPATH=. python -m bridges.isaacteleop_to_so101.record_quest \\
      --out data/quest_teleop/run.jsonl --duration 20 --arms right
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from .from_retarget import command_from_retarget, summarize_jsonl
from .quest_pipeline import build_controller_pipeline, require_isaaccapture

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    require_isaaccapture()

    from isaaccapture.cloudxr import CloudXRLauncher
    from isaaccapture.teleop_session_manager import TeleopSession, TeleopSessionConfig

    parser = argparse.ArgumentParser(description=__doc__)
    CloudXRLauncher.add_launcher_arguments(parser)
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="JSONL output path (one contract object per line)",
    )
    parser.add_argument("--duration", type=float, default=20.0, help="Seconds to record")
    parser.add_argument("--hz", type=float, default=30.0, help="Target step rate")
    parser.add_argument(
        "--arms",
        choices=("right", "left", "both"),
        default="right",
        help="Which logical arms to record (default: right controller)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print a status line ~2 Hz",
    )
    args = parser.parse_args(argv)

    if args.arms == "both":
        arms = ["left", "right"]
    elif args.arms == "left":
        arms = ["left"]
    else:
        arms = ["right"]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    period = 1.0 / max(1.0, args.hz)

    pipeline = build_controller_pipeline(arms)
    session_config = TeleopSessionConfig(
        app_name="So101QuestRecord",
        trackers=[],
        pipeline=pipeline,
    )

    host_ip = os.environ.get("SO101_HOST_IP", "")
    try:
        import socket

        host_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        pass

    print(f"Recording → {args.out}")
    print(f"Arms: {arms}  duration={args.duration}s  hz≈{args.hz}")
    print("Quest: Meta Quest Browser → Connect, then move right controller / squeeze trigger")
    if host_ip:
        print(f"Client hint: https://{host_ip}:48322/client/")
    print("----")

    n_written = 0
    with CloudXRLauncher.launch_context(args), TeleopSession(session_config) as session:
        t0 = time.monotonic()
        last_print = 0.0
        with args.out.open("w", encoding="utf-8") as fh:
            while time.monotonic() - t0 < args.duration:
                result = session.step()
                ts = time.time_ns()
                for arm in arms:
                    pose = result[f"pose_{arm}"][0]
                    grip = float(result[f"gripper_{arm}"][0])
                    cmd = command_from_retarget(
                        arm=arm,
                        pose7=pose,
                        isaac_gripper=grip,
                        timestamp_ns=ts,
                    )
                    fh.write(cmd.to_json() + "\n")
                    n_written += 1
                if args.verbose and (time.monotonic() - last_print) >= 0.5:
                    last_print = time.monotonic()
                    arm0 = arms[0]
                    pose = result[f"pose_{arm0}"][0]
                    grip = float(result[f"gripper_{arm0}"][0])
                    cmd = command_from_retarget(
                        arm=arm0, pose7=pose, isaac_gripper=grip, timestamp_ns=ts
                    )
                    p = cmd.ee_pose.position_m if cmd.ee_pose else (0, 0, 0)
                    print(
                        f"[{time.monotonic() - t0:5.1f}s] {arm0} "
                        f"pos=({p[0]:.3f},{p[1]:.3f},{p[2]:.3f}) "
                        f"grip={cmd.gripper:.2f} valid={cmd.valid}"
                    )
                time.sleep(period)

    stats = summarize_jsonl(str(args.out))
    print("----")
    print(f"Wrote {n_written} lines → {args.out}")
    print(
        f"stats: frames={stats['frames']} valid={stats['valid_frames']} "
        f"hz≈{stats['approx_hz']} gripper=[{stats['gripper_min']}, {stats['gripper_max']}]"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
