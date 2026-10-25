"""Pi-side WebSocket receiver: teleop JSON → dual SO-101 joint targets.

Do not run alongside LeLab / Web Remote (shared USB serial).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
import time
from pathlib import Path
from typing import Any

from .arms import DEFAULT_CONFIG_PATH, DualArmConfig, load_dual_arm_config
from .contract import JOINT_KEYS, ContractError, TeleopCommand, parse_command
from .controls import load_teleop_config
from .ik import DEFAULT_URDF_PATH, IkSolver, build_ik
from .config_watch import TeleopConfigWatcher, apply_teleop_runtime
from .nest import DEFAULT_HOME_PATH, has_home_flags, joints_for_arm, near_home, summarize_nest
from .safety import SoftLimits

logger = logging.getLogger(__name__)


class ArmRuntime:
    """Per-physical-arm target buffer + optional LeRobot follower."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.targets = {k: 0.0 for k in JOINT_KEYS}
        self.last_rx_mono = 0.0
        self.holding = True
        self.robot: Any = None
        self._lock = threading.Lock()

    def seed_from_obs(self) -> None:
        if self.robot is None:
            return
        obs = self.robot.get_observation()
        with self._lock:
            for key in JOINT_KEYS:
                pos_key = f"{key}.pos"
                if pos_key in obs and isinstance(obs[pos_key], (int, float)):
                    self.targets[key] = float(obs[pos_key])

    def apply_targets(self, joints: dict[str, float], *, now: float) -> None:
        with self._lock:
            self.targets.update(joints)
            self.last_rx_mono = now
            self.holding = False

    def mark_hold(self) -> None:
        with self._lock:
            self.holding = True

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self.targets)

    def send(self) -> None:
        if self.robot is None:
            return
        with self._lock:
            if self.holding:
                return
            action = {f"{k}.pos": float(v) for k, v in self.targets.items()}
        try:
            self.robot.send_action(action)
        except Exception:
            logger.debug("send_action failed for %r", self.name, exc_info=True)


class BridgeReceiver:
    """WebSocket /teleop server + control loop."""

    def __init__(
        self,
        config: DualArmConfig,
        ik: IkSolver,
        *,
        host: str = "0.0.0.0",
        port: int = 8870,
        path: str = "/teleop",
        control_hz: float = 50.0,
        cmd_timeout_s: float = 0.2,
        dry_run: bool = False,
        dump_path: Path | None = None,
        home_path: Path | None = None,
        go_home_timeout_s: float = 45.0,
        soft_limits: SoftLimits | None = None,
        teleop_config_path: Path | None = None,
    ) -> None:
        self.config = config
        self.ik = ik
        self.host = host
        self.port = port
        self.path = path
        self.control_hz = control_hz
        self.cmd_timeout_s = cmd_timeout_s
        self.dry_run = dry_run
        self.dump_path = dump_path
        self.home_path = Path(home_path) if home_path else DEFAULT_HOME_PATH
        self.go_home_timeout_s = float(go_home_timeout_s)
        self.soft_limits = soft_limits or SoftLimits(enabled=False)
        self.teleop_config_path = Path(teleop_config_path) if teleop_config_path else None
        self.runtimes: dict[str, ArmRuntime] = {name: ArmRuntime(name) for name in config.arms}
        self._stop = threading.Event()
        self._ctrl_thread: threading.Thread | None = None
        self._dump_fp = None
        self._config_watcher: TeleopConfigWatcher | None = None

    def connect_robots(self) -> None:
        if self.dry_run:
            logger.info("dry-run: skipping robot connect; arms=%s", list(self.runtimes))
            return

        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

        for name, phys in self.config.arms.items():
            cfg = SO101FollowerConfig(
                port=phys.port,
                id=phys.robot_id,
                cameras={},
                max_relative_target=10.0,
                use_degrees=True,
                # CRITICAL: default LeRobot True would limp both arms on exit → free-fall.
                disable_torque_on_disconnect=False,
            )
            logger.info("Connecting %r id=%s on %s ...", name, phys.robot_id, phys.port)
            robot = self._connect_with_retries(SO101Follower, cfg, name=name)
            if not robot.calibration:
                raise RuntimeError(
                    f"No calibration for {name!r}. Run lerobot-calibrate with "
                    f"--robot.port={phys.port} --robot.id={phys.robot_id}"
                )
            rt = self.runtimes[name]
            rt.robot = robot
            rt.seed_from_obs()
            logger.info("Arm %r ready", name)

    def _connect_with_retries(
        self,
        cls: Any,
        cfg: Any,
        *,
        name: str,
        attempts: int = 4,
        pause_s: float = 0.8,
    ) -> Any:
        """Feetech Lock/torque writes occasionally drop a status packet — retry."""
        last_exc: Exception | None = None
        for i in range(1, attempts + 1):
            robot = cls(cfg)
            try:
                robot.connect(calibrate=False)
                return robot
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("connect %r attempt %d/%d failed: %s", name, i, attempts, exc)
                try:
                    if getattr(robot, "is_connected", False):
                        robot.disconnect()
                    elif getattr(getattr(robot, "bus", None), "is_connected", False):
                        robot.bus.disconnect()
                except Exception:
                    logger.debug("cleanup after failed connect", exc_info=True)
                time.sleep(pause_s)
        assert last_exc is not None
        raise last_exc

    def disconnect_robots(self) -> None:
        """Leave torque ON so arms keep the last pose (no free-fall on Ctrl+C)."""
        for rt in self.runtimes.values():
            robot = rt.robot
            if robot is None:
                continue
            try:
                if robot.is_connected:
                    # Freeze at measured pose, then disconnect without clearing torque.
                    rt.seed_from_obs()
                    rt.holding = False
                    rt.send()
                    time.sleep(0.05)
                    robot.disconnect()
                    logger.info(
                        "Arm %r disconnected with torque left enabled (hold pose)",
                        rt.name,
                    )
            except Exception:
                logger.exception("disconnect failed for %r", rt.name)
            rt.robot = None

    def handle_command(self, cmd: TeleopCommand) -> dict[str, Any]:
        """Apply one validated command; returns a small ack dict."""
        try:
            phys = self.config.physical_for(cmd.arm)
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}

        rt = self.runtimes[phys.name]
        now = time.monotonic()

        if not cmd.valid:
            rt.mark_hold()
            self.ik.reset(phys.name)
            return {"ok": True, "arm": phys.name, "held": True, "reason": "valid_false"}

        seed = rt.snapshot()
        joints = self.ik.solve(phys.name, cmd, seed)
        if joints is None:
            return {"ok": False, "error": "no_joints_from_ik", "arm": phys.name}

        # Software soft limits (yaml) — inside hardware JOINT_LIMITS_DEG.
        joints = self.soft_limits.clamp_joints(phys.name, joints)
        rt.apply_targets(joints, now=now)
        self._dump(cmd, phys.name, joints)

        if self.dry_run:
            logger.info(
                "dry-run arm=%s logical=%s joints=%s",
                phys.name,
                cmd.arm,
                {k: round(v, 1) for k, v in joints.items()},
            )
        return {"ok": True, "arm": phys.name, "logical": cmd.arm, "holding": False}

    def _resolve_go_home_arms(self, arm: str | None) -> list[str]:
        """Map go_home arm selector → physical runtime names."""
        if arm is None or arm in {"", "both", "all"}:
            return list(self.runtimes)
        key = str(arm).strip().lower()
        if key in self.runtimes:
            return [key]
        # Logical left/right/single via resolve table
        try:
            phys = self.config.physical_for(key)
            return [phys.name]
        except KeyError:
            raise KeyError(f"unknown go_home arm {arm!r}; use follower|leader|left|right|both") from None

    def go_home(
        self,
        arm: str | None = None,
        *,
        timeout_s: float | None = None,
        tol_deg: float = 2.5,
        hz: float = 20.0,
    ) -> dict[str, Any]:
        """Move arm(s) to Web Remote nest pose, then hold. Resets IK anchors."""
        try:
            names = self._resolve_go_home_arms(arm)
        except KeyError as exc:
            return {"ok": False, "type": "go_home", "error": str(exc)}

        timeout = float(self.go_home_timeout_s if timeout_s is None else timeout_s)
        period = 1.0 / max(1.0, hz)
        results: dict[str, Any] = {}

        for name in names:
            rt = self.runtimes[name]
            target, from_file = joints_for_arm(name, path=self.home_path)
            src = "file" if from_file else "default"
            self.ik.reset(name)
            if self.dry_run:
                rt.apply_targets(target, now=time.monotonic())
                results[name] = {"ok": True, "source": src, "reached": True, "dry_run": True}
                logger.info("dry-run go_home %s source=%s target=%s", name, src, {k: round(v, 1) for k, v in target.items()})
                continue

            if rt.robot is None:
                results[name] = {"ok": False, "error": "not_connected", "source": src}
                continue

            logger.info(
                "go_home %s source=%s → %s",
                name,
                src,
                {k: round(v, 1) for k, v in target.items()},
            )
            deadline = time.monotonic() + timeout
            reached = False
            try:
                while time.monotonic() < deadline:
                    rt.apply_targets(target, now=time.monotonic())
                    try:
                        rt.seed_from_obs()
                    except Exception as exc:  # noqa: BLE001 — keep approaching
                        logger.warning("go_home %s seed_from_obs: %s", name, exc)
                    if near_home(rt.snapshot(), target, tol_deg=tol_deg):
                        reached = True
                        break
                    time.sleep(period)
                # Keep commanding nest so control loop holds after approach.
                rt.apply_targets(target, now=time.monotonic())
                self.ik.reset(name)
            except Exception as exc:  # noqa: BLE001
                logger.exception("go_home %s failed", name)
                results[name] = {"ok": False, "error": str(exc), "source": src}
                continue
            results[name] = {
                "ok": True,
                "source": src,
                "reached": reached,
                "joints": {k: round(v, 1) for k, v in target.items()},
            }
            if reached:
                logger.info("go_home %s reached nest", name)
            else:
                logger.warning("go_home %s timed out (holding last nest command)", name)

        ok = all(bool(v.get("ok")) for v in results.values()) if results else False
        return {
            "ok": ok,
            "type": "go_home",
            "arms": results,
            "home_path": str(self.home_path),
            "has_home": has_home_flags(path=self.home_path, arm_names=list(self.runtimes)),
        }

    def _dump(self, cmd: TeleopCommand, phys: str, joints: dict[str, float]) -> None:
        if self.dump_path is None:
            return
        if self._dump_fp is None:
            self.dump_path.parent.mkdir(parents=True, exist_ok=True)
            self._dump_fp = self.dump_path.open("a", encoding="utf-8")
        import json

        row = {
            "rx_mono": time.monotonic(),
            "physical": phys,
            "cmd": cmd.to_dict(),
            "joints": joints,
        }
        self._dump_fp.write(json.dumps(row, separators=(",", ":")) + "\n")
        self._dump_fp.flush()

    def _control_loop(self) -> None:
        period = 1.0 / max(1.0, self.control_hz)
        while not self._stop.is_set():
            t0 = time.monotonic()
            now = t0
            for rt in self.runtimes.values():
                if rt.last_rx_mono > 0 and (now - rt.last_rx_mono) > self.cmd_timeout_s:
                    if not rt.holding:
                        logger.warning(
                            "arm %r cmd timeout (%.0f ms) — holding pose",
                            rt.name,
                            self.cmd_timeout_s * 1000,
                        )
                    rt.mark_hold()
                else:
                    rt.send()
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, period - elapsed))

    def start_control(self) -> None:
        self._stop.clear()
        self._ctrl_thread = threading.Thread(target=self._control_loop, name="bridge-ctrl", daemon=True)
        self._ctrl_thread.start()

    def stop_control(self) -> None:
        self._stop.set()
        if self._ctrl_thread and self._ctrl_thread.is_alive():
            self._ctrl_thread.join(timeout=2.0)
        if self._dump_fp is not None:
            self._dump_fp.close()
            self._dump_fp = None

    def _request_path(self, websocket: Any) -> str:
        """websockets 10–17: path may live on the socket or on ``request``."""
        req_path = getattr(websocket, "path", None)
        if req_path:
            return str(req_path)
        request = getattr(websocket, "request", None)
        if request is not None:
            return str(getattr(request, "path", self.path) or self.path)
        return self.path

    async def _ws_handler(self, websocket: Any) -> None:
        req_path = self._request_path(websocket)
        # Accept "/teleop" and bare "/" only when configured path is "/teleop"
        # (some clients omit the path). Prefer exact match.
        allowed = {self.path, self.path.rstrip("/") + "/"}
        if req_path not in allowed and not (req_path in {"", "/"} and self.path == "/teleop"):
            await websocket.close(code=1008, reason=f"use path {self.path}")
            return

        peer = getattr(websocket, "remote_address", None)
        logger.info("client connected %s", peer)
        # Welcome: measured joints so senders can orbit the current pose (not zero).
        import json

        nest_info = summarize_nest(path=self.home_path)
        hello = {
            "ok": True,
            "type": "hello",
            "arms": {name: rt.snapshot() for name, rt in self.runtimes.items()},
            "resolve": {
                "left": self.config.resolve.left,
                "right": self.config.resolve.right,
                "single": self.config.resolve.single,
            },
            "home_path": nest_info["path"],
            "has_home": has_home_flags(path=self.home_path, arm_names=list(self.runtimes)),
            "supports_go_home": True,
        }
        await websocket.send(json.dumps(hello, separators=(",", ":")))
        try:
            async for message in websocket:
                # Control plane: {"type":"go_home","arm":"both"|...}
                try:
                    raw = json.loads(message) if isinstance(message, (str, bytes)) else message
                except (TypeError, json.JSONDecodeError):
                    raw = None
                if isinstance(raw, dict) and raw.get("type") == "go_home":
                    arm_sel = raw.get("arm")
                    timeout = raw.get("timeout_s")
                    arm_arg = (
                        None
                        if arm_sel in (None, "", "both", "all")
                        else str(arm_sel)
                    )
                    timeout_val = float(timeout) if timeout is not None else None
                    logger.info("go_home requested arm=%s timeout=%s", arm_sel, timeout_val)

                    def _go_home_call() -> dict[str, Any]:
                        try:
                            return self.go_home(arm_arg, timeout_s=timeout_val)
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("go_home crashed")
                            return {
                                "ok": False,
                                "type": "go_home",
                                "error": f"{type(exc).__name__}: {exc}",
                            }

                    try:
                        # Acknowledge quickly so the client knows we received the request
                        # before the (possibly long) approach blocks the worker thread.
                        await websocket.send(
                            json.dumps(
                                {"ok": True, "type": "go_home_ack", "arm": arm_sel},
                                separators=(",", ":"),
                            )
                        )
                        ack = await asyncio.to_thread(_go_home_call)
                        await websocket.send(json.dumps(ack, separators=(",", ":")))
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("go_home reply failed")
                        try:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "ok": False,
                                        "type": "go_home",
                                        "error": f"{type(exc).__name__}: {exc}",
                                    },
                                    separators=(",", ":"),
                                )
                            )
                        except Exception:
                            logger.debug("could not send go_home error ack", exc_info=True)
                    continue
                if isinstance(raw, dict) and raw.get("type") == "teleop_config_patch":
                    # Quest settings UI / PC → apply overlay on Pi and persist overrides.
                    overlay = raw.get("overlay") or {}
                    try:
                        if self.teleop_config_path is not None and isinstance(overlay, dict):
                            from .controls import load_teleop_config, save_teleop_overrides

                            ov_path = save_teleop_overrides(
                                overlay, config_path=self.teleop_config_path
                            )
                            cfg = load_teleop_config(self.teleop_config_path)
                            apply_teleop_runtime(self, cfg)
                            ack = {
                                "ok": True,
                                "type": "teleop_config_patch",
                                "overrides_path": str(ov_path),
                                "pos_scale": cfg.pos_scale,
                                "axis_map": cfg.axis_map,
                                "safety_enabled": cfg.soft_limits.enabled,
                            }
                        else:
                            ack = {
                                "ok": False,
                                "type": "teleop_config_patch",
                                "error": "no_teleop_config_path",
                            }
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("teleop_config_patch failed")
                        ack = {
                            "ok": False,
                            "type": "teleop_config_patch",
                            "error": str(exc),
                        }
                    await websocket.send(json.dumps(ack, separators=(",", ":")))
                    continue
                try:
                    cmd = parse_command(message)
                except ContractError as exc:
                    await websocket.send(f'{{"ok":false,"error":"contract","detail":"{exc}"}}')
                    logger.warning("bad payload: %s", exc)
                    continue
                ack = self.handle_command(cmd)
                await websocket.send(json.dumps(ack, separators=(",", ":")))
        except Exception as exc:
            # ConnectionClosed is normal; anything else must be visible on the Pi log.
            name = type(exc).__name__
            if "ConnectionClosed" in name:
                logger.info("client disconnected %s (%s)", peer, exc)
            else:
                logger.exception("websocket handler error %s", peer)
        finally:
            logger.info("client closed %s — holding all arms", peer)
            for rt in self.runtimes.values():
                rt.mark_hold()
                self.ik.reset(rt.name)

    async def run_async(self) -> None:
        import websockets

        self.connect_robots()
        self.start_control()
        if self.teleop_config_path is not None:
            self._config_watcher = TeleopConfigWatcher(
                self.teleop_config_path,
                apply=lambda cfg: apply_teleop_runtime(self, cfg),
            )
            self._config_watcher.start()
        logger.info(
            "bridge listening ws://%s:%s%s  arms=%s dry_run=%s timeout=%.0fms",
            self.host,
            self.port,
            self.path,
            list(self.runtimes),
            self.dry_run,
            self.cmd_timeout_s * 1000,
        )
        try:
            # Long go_home approaches need headroom beyond the default ping timeout.
            async with websockets.serve(
                self._ws_handler,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=90,
            ):
                await asyncio.Future()  # run forever
        finally:
            if self._config_watcher is not None:
                self._config_watcher.stop()
                self._config_watcher = None
            self.stop_control()
            self.disconnect_robots()

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def _shutdown(*_args: Any) -> None:
            logger.info("shutdown signal")
            self.stop_control()
            for task in asyncio.all_tasks(loop):
                task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda *_: _shutdown())

        try:
            loop.run_until_complete(self.run_async())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            self.stop_control()
            self.disconnect_robots()
            loop.close()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SO-101 dual-arm teleop bridge receiver (Pi)")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8870)
    p.add_argument("--path", default="/teleop")
    p.add_argument("--control-hz", type=float, default=50.0)
    p.add_argument("--cmd-timeout", type=float, default=0.2, help="seconds without cmd → hold")
    p.add_argument("--follower-id", default="my_follower")
    p.add_argument("--leader-id", default="my_leader_drive")
    p.add_argument("--no-leader", action="store_true", help="follower only")
    p.add_argument(
        "--ik",
        choices=("approx", "placo", "relative", "none"),
        default="approx",
        help="approx=heuristic Δ; relative=FK tip tracking (needs placo+URDF)",
    )
    p.add_argument(
        "--urdf",
        default=None,
        help=f"URDF for placo/relative (default: {DEFAULT_URDF_PATH})",
    )
    p.add_argument(
        "--teleop-config",
        type=Path,
        default=None,
        help="quest_teleop.yaml for relative EE axis_map / pos_scale",
    )
    p.add_argument(
        "--max-step-deg",
        type=float,
        default=3.0,
        help="ApproxIk per-axis joint step clamp (degrees)",
    )
    p.add_argument("--dry-run", action="store_true", help="no serial; log joint targets")
    p.add_argument("--dump", type=Path, default=None, help="append JSONL of received cmds")
    p.add_argument(
        "--home-file",
        type=Path,
        default=DEFAULT_HOME_PATH,
        help="Web Remote nest JSON (go_home)",
    )
    p.add_argument(
        "--go-home-timeout",
        type=float,
        default=45.0,
        help="seconds for go_home approach",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    teleop = load_teleop_config(args.teleop_config) if args.teleop_config else None
    resolve = teleop.arm_resolve if teleop is not None else None
    config = load_dual_arm_config(
        args.config,
        follower_id=args.follower_id,
        leader_id=args.leader_id,
        enable_leader=not args.no_leader,
        resolve=resolve,
    )
    pos_scale = float(teleop.pos_scale) if teleop is not None else 1.0
    axis_map = dict(teleop.axis_map) if teleop is not None else None
    soft_limits = teleop.soft_limits if teleop is not None else SoftLimits(enabled=False)
    if teleop is not None:
        logger.info(
            "arm_resolve left→%s right→%s single→%s",
            config.resolve.left,
            config.resolve.right,
            config.resolve.single,
        )
        logger.info(
            "soft_limits enabled=%s joints=%s tip=%s",
            soft_limits.enabled,
            sorted(soft_limits.joint_limits_deg),
            sorted(soft_limits.tip_bounds_m),
        )
    if teleop is not None and args.ik == "approx" and teleop.motion_mode == "relative_ee":
        logger.info(
            "teleop config motion.mode=relative_ee but --ik=%s; "
            "pass --ik relative for tip tracking",
            args.ik,
        )
    ik = build_ik(
        args.ik,
        urdf=args.urdf,
        max_step_deg=args.max_step_deg,
        pos_scale=pos_scale,
        axis_map=axis_map,
        soft_limits=soft_limits,
    )
    logger.info("IK solver=%s urdf=%s", args.ik, args.urdf or DEFAULT_URDF_PATH)
    BridgeReceiver(
        config,
        ik,
        host=args.host,
        port=args.port,
        path=args.path,
        control_hz=args.control_hz,
        cmd_timeout_s=args.cmd_timeout,
        dry_run=args.dry_run,
        dump_path=args.dump,
        home_path=args.home_file,
        go_home_timeout_s=args.go_home_timeout,
        soft_limits=soft_limits,
        teleop_config_path=args.teleop_config,
    ).run()

if __name__ == "__main__":
    main()
