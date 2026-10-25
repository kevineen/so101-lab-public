"""Phase D: Quest / CloudXR → contract JSON → Pi bridge (live).

Clutch (default A/X = primary_click): hold to follow, release to hold pose.
ApproxIk re-anchors when clutch re-engages (receiver resets on valid=false).

Example::

    PYTHONPATH=. python -m bridges.isaacteleop_to_so101.live_quest \\
      --host ${SO101_PI_LAN_IP} --config configs/quest_teleop.yaml -v
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from .controls import (
    ClutchState,
    TeleopControlsConfig,
    axis_value,
    clutch_engaged,
    gripper_axis_is_bipolar,
    gripper_axis_to_contract,
    load_teleop_config,
)
from .from_retarget import command_from_retarget, pose7_is_tracked
from .quest_camera_planes import QuestCameraPlanes
from .quest_pipeline import build_controller_pipeline, require_isaaccapture
from .sender import _now_ns, _recv_hello, request_go_home

logger = logging.getLogger(__name__)


def _resolve_arms(cli_arms: str | None, cfg: TeleopControlsConfig) -> list[str]:
    if cli_arms is None:
        return list(cfg.arms) if cfg.arms else ["left", "right"]
    if cli_arms == "both":
        return ["left", "right"]
    if cli_arms == "left":
        return ["left"]
    if cli_arms == "right":
        return ["right"]
    return list(cfg.arms)


async def _live_loop(
    *,
    host: str,
    port: int,
    path: str,
    arms: list[str],
    duration_s: float,
    hz: float,
    verbose: bool,
    dump: Path | None,
    teleop_cfg: TeleopControlsConfig,
    cloudxr_args: argparse.Namespace,
    enable_cameras: bool,
    go_home: bool,
    go_home_timeout_s: float,
) -> None:
    import websockets
    from isaaccapture.cloudxr import CloudXRLauncher
    from isaaccapture.teleop_session_manager import TeleopSession, TeleopSessionConfig

    pipeline = build_controller_pipeline(arms, include_gripper_retargeter=False)
    session_config = TeleopSessionConfig(
        app_name="So101QuestLiveBridge",
        trackers=[],
        pipeline=pipeline,
    )
    period = 1.0 / max(1.0, hz)
    uri = f"ws://{host}:{port}{path}"
    clutch = ClutchState()

    dump_fp = None
    if dump is not None:
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump_fp = dump.open("w", encoding="utf-8")

    cam = None
    if enable_cameras and teleop_cfg.cameras_enabled:
        # Stream from the same Pi as the bridge (--host wins over yaml IP)
        teleop_cfg.cameras_pi_base_url = f"http://{host}:8765"
        cam = QuestCameraPlanes(teleop_cfg)

    print(f"Bridge: {uri}")
    dur_label = "unlimited (Ctrl+C to stop)" if duration_s <= 0 else f"{duration_s}s"
    print(f"Arms: {arms}  duration={dur_label}  hz≈{hz}")
    print(
        f"Arm map: left→{teleop_cfg.arm_resolve.left}  "
        f"right→{teleop_cfg.arm_resolve.right}"
    )
    print(
        f"Clutch: {teleop_cfg.clutch_axis} (>= {teleop_cfg.clutch_threshold})  "
        f"Gripper: {teleop_cfg.gripper_axis}"
    )
    print(
        f"Motion: mode={teleop_cfg.motion_mode}  "
        f"pos_scale={teleop_cfg.pos_scale}  axis_map={teleop_cfg.axis_map}"
    )
    if teleop_cfg.motion_mode == "relative_ee":
        print(
            "Relative EE: PC sends raw Quest pose; Pi --ik relative tracks gripper tip."
        )
    if go_home:
        print("On connect: go_home to nest, then clutch teleop.")
    print("Hold clutch button to follow; release to hold pose. Move slowly.")
    if cam is not None:
        for name, url in cam.stream_urls():
            print(f"Camera {name}: {url}")
    print("----")

    try:
        with CloudXRLauncher.launch_context(cloudxr_args), TeleopSession(
            session_config
        ) as session:
            if cam is not None:
                cam.start()
                logger.info("camera planes status=%s", cam.status)

            async with websockets.connect(uri, max_size=2**20) as ws:
                hello = await _recv_hello(ws)
                logger.info(
                    "hello arms=%s has_home=%s supports_go_home=%s",
                    list((hello.get("arms") or {}).keys()),
                    hello.get("has_home"),
                    hello.get("supports_go_home"),
                )
                if go_home:
                    if not hello.get("supports_go_home"):
                        raise RuntimeError(
                            "Pi receiver is too old for go_home — pull so101-lab on Pi "
                            "and restart: BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v"
                        )
                    await request_go_home(ws, timeout_s=go_home_timeout_s)
                    print("Nest done — clutch to teleop.")

                t0 = time.monotonic()
                last_print = 0.0
                sent = 0
                # duration_s <= 0 → run until Ctrl+C
                while duration_s <= 0 or (time.monotonic() - t0) < duration_s:
                    step_t0 = time.monotonic()
                    result = session.step()
                    ts = _now_ns()
                    status_bits: list[str] = []

                    for arm in arms:
                        pose_raw = result[f"pose_{arm}"][0]
                        pose7 = [float(x) for x in pose_raw]
                        ctrl = result[f"controller_{arm}"]
                        if getattr(ctrl, "is_none", False):
                            engaged = False
                            grip_unit = 0.0
                            clutch_raw = 0.0
                        else:
                            clutch_raw = axis_value(ctrl, teleop_cfg.clutch_axis)
                            engaged = clutch_engaged(
                                clutch_raw, threshold=teleop_cfg.clutch_threshold
                            )
                            grip_raw = axis_value(ctrl, teleop_cfg.gripper_axis)
                            grip_unit = gripper_axis_to_contract(
                                grip_raw,
                                deadzone=teleop_cfg.gripper_deadzone,
                                invert=teleop_cfg.gripper_invert,
                                bipolar=gripper_axis_is_bipolar(teleop_cfg.gripper_axis),
                            )

                        engaged, rising = clutch.update(arm, engaged)
                        tracked = pose7_is_tracked(pose7)
                        force_valid = bool(engaged and tracked)
                        # relative_ee: Pi applies pos_scale after FK tip anchor — do not
                        # double-scale on the PC.
                        if force_valid and teleop_cfg.motion_mode != "relative_ee":
                            pose7 = clutch.scaled_pose(
                                arm,
                                pose7,
                                pos_scale=teleop_cfg.pos_scale,
                                rising=rising,
                            )

                        cmd = command_from_retarget(
                            arm=arm,
                            pose7=pose7,
                            contract_gripper=grip_unit,
                            timestamp_ns=ts,
                            force_valid=force_valid,
                        )
                        payload = cmd.to_dict()
                        payload["timestamp_ns"] = _now_ns()
                        line = json.dumps(payload, separators=(",", ":"))
                        await ws.send(line)
                        sent += 1
                        if dump_fp is not None:
                            dump_fp.write(line + "\n")
                        try:
                            ack = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            if verbose and logger.isEnabledFor(logging.DEBUG):
                                logger.debug("ack %s", ack)
                        except TimeoutError:
                            logger.warning("no ack from receiver")

                        status_bits.append(
                            f"{arm}:clutch={'ON' if engaged else 'off'} "
                            f"grip={cmd.gripper:.2f} valid={cmd.valid}"
                        )

                    if verbose and (time.monotonic() - last_print) >= 0.5:
                        last_print = time.monotonic()
                        arm0 = arms[0]
                        pose = result[f"pose_{arm0}"][0]
                        print(
                            f"[{time.monotonic() - t0:5.1f}s] "
                            + " | ".join(status_bits)
                            + f" | pos=({float(pose[0]):.2f},{float(pose[1]):.2f},{float(pose[2]):.2f})"
                            + f" sent={sent}"
                            + (f" cams={cam.status}" if cam else "")
                        )

                    await asyncio.sleep(max(0.0, period - (time.monotonic() - step_t0)))
    finally:
        if cam is not None:
            cam.stop()
        if dump_fp is not None:
            dump_fp.close()
            print(f"Dumped JSONL → {dump}")

    print(f"Done. frames_sent≈{sent}")


def main(argv: list[str] | None = None) -> int:
    require_isaaccapture()
    from isaaccapture.cloudxr import CloudXRLauncher

    root = Path(__file__).resolve().parents[2]
    default_cfg = root / "configs" / "quest_teleop.yaml"

    parser = argparse.ArgumentParser(description=__doc__)
    CloudXRLauncher.add_launcher_arguments(parser)
    parser.add_argument("--host", required=True, help="Pi LAN IP")
    parser.add_argument("--port", type=int, default=8870)
    parser.add_argument("--path", default="/teleop")
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Seconds to run; 0 or negative = unlimited until Ctrl+C (default)",
    )
    parser.add_argument("--hz", type=float, default=30.0)
    parser.add_argument(
        "--config",
        type=Path,
        default=default_cfg,
        help="quest_teleop.yaml (clutch / gripper / cameras)",
    )
    parser.add_argument(
        "--arms",
        choices=("right", "left", "both", "from-config"),
        default="from-config",
        help="Logical arms (default: from YAML, usually both)",
    )
    parser.add_argument("--dump", type=Path, default=None)
    parser.add_argument("--no-cameras", action="store_true", help="Disable Televiz camera planes")
    parser.add_argument(
        "--go-home",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="On connect, ask Pi to move arms to saved nest (default: on)",
    )
    parser.add_argument(
        "--go-home-timeout",
        type=float,
        default=45.0,
        help="Seconds for nest approach on Pi",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    teleop_cfg = load_teleop_config(args.config)
    cli_arms = None if args.arms == "from-config" else args.arms
    arms = _resolve_arms(cli_arms, teleop_cfg)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if teleop_cfg.source_path:
        logger.info("teleop config: %s", teleop_cfg.source_path)

    try:
        asyncio.run(
            _live_loop(
                host=args.host,
                port=args.port,
                path=args.path,
                arms=arms,
                duration_s=args.duration,
                hz=args.hz,
                verbose=args.verbose,
                dump=args.dump,
                teleop_cfg=teleop_cfg,
                cloudxr_args=args,
                enable_cameras=not args.no_cameras,
                go_home=bool(args.go_home),
                go_home_timeout_s=float(args.go_home_timeout),
            )
        )
    except KeyboardInterrupt:
        logger.info("live quest stopped")
        return 130
    except OSError as exc:
        logger.error("bridge connect failed: %s (is Pi receiver running?)", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
