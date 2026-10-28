"""Attach the phone button server to ``robot_client`` without editing vendor code.

Replaces ``RobotClient.control_loop`` so ready / running / result phases are
driven from the phone. Observations still go to the policy server only while
a trial is running and not paused. Ready also accepts model prev/next.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from queue import Queue

from infer_buttons.catalog import index_for_path, load_catalog, send_policy
from infer_buttons.nest import (
    apply_nest_step,
    ensure_torque_on,
    make_staged_nest,
    nest_step_deg,
    restore_nest_step,
    step_staged_nest,
)
from infer_buttons.serial_health import (
    is_port_busy_error,
    release_robot_bus,
    serial_fd_status,
)
from infer_buttons.rollout_record import RolloutRecorder
from infer_buttons.server import start_button_server
from infer_buttons.status import InferStatus
from record_buttons.preview import FramePreview

logger = logging.getLogger("infer_buttons")


def clear_action_queue(client: object) -> None:
    """Drop pending actions so pause / end does not keep moving the arm."""
    lock = getattr(client, "action_queue_lock", None)
    queue = getattr(client, "action_queue", None)
    if lock is None or queue is None:
        return
    with lock:
        client.action_queue = Queue()


def model_label(path: str) -> str:
    text = (path or "").rstrip("/")
    if not text:
        return ""
    name = Path(text).name
    if name == "pretrained_model":
        parts = Path(text).parts
        if len(parts) >= 4 and parts[-2] == "last" and parts[-3] == "checkpoints":
            return parts[-4]
        parent = Path(text).parent.name
        return parent or name
    return name


def _recover_busy_bus(robot: object, *, where: str) -> bool:
    """Clear stuck Feetech ``is_using`` after Port is in use."""
    ok = release_robot_bus(robot)
    if ok:
        logger.warning("%s: cleared stuck bus is_using (Port is in use)", where)
    return ok


def _note_obs(preview: FramePreview, robot: object, *, where: str, last_err: list[float]) -> None:
    """Read one observation for the phone. Rate-limit serial error spam."""
    try:
        obs = robot.get_observation()
        preview.note_observation(obs)
        last_err[0] = 0.0
    except Exception as exc:
        if is_port_busy_error(exc):
            _recover_busy_bus(robot, where=where)
        now = time.monotonic()
        if now - last_err[0] >= 2.0:
            last_err[0] = now
            logger.warning("%s observation failed: %s", where, exc)


def _apply_entry(status: InferStatus, entry, index: int, count: int) -> None:
    status.set_model(
        model=model_label(entry.path),
        policy_type=entry.policy_type,
        model_id=entry.id,
        model_label=entry.label,
        model_index=index,
        model_count=count,
    )


def _switch_policy(client: object, status: InferStatus, entry, *, preview, robot, last_err, dt: float) -> None:
    """Send policy to the server while updating phone load progress."""
    target = f"{entry.id} · {entry.label} ({entry.policy_type})"
    status.begin_load(target)
    status.set_load("send", "ポリシー指示を送信中…", 20)
    print(f"モデル切替 → {target} …", flush=True)

    error: list[BaseException] = []
    done = threading.Event()

    def work() -> None:
        try:
            status.set_load("wait_server", "サーバが重みを読み込み中…（数十秒かかることがあります）", 35)
            send_policy(client, entry)
        except BaseException as exc:  # noqa: BLE001 — surface to caller
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=work, name="infer-model-load", daemon=True).start()
    while not done.wait(0.25):
        # Keep the phone preview alive and let load_elapsed / load_pct advance.
        _note_obs(preview, robot, where="load", last_err=last_err)
        time.sleep(max(0.0, min(dt, 0.05)))

    if error:
        status.end_load(ok=False, message=f"失敗: {error[0]}")
        raise error[0]
    status.end_load(ok=True, message=f"完了: {target}")
    print(
        f"モデル切替完了: {entry.id} {entry.label} · chunk={entry.actions_per_chunk}"
        f"（{status.load_elapsed_s():.1f}s）",
        flush=True,
    )


def install_phone_infer() -> None:
    """Patch ``RobotClient.control_loop`` before ``async_client`` runs."""
    from lerobot.async_inference.robot_client import RobotClient

    original = RobotClient.control_loop

    def control_loop(self, task: str, verbose: bool = False):
        self.start_barrier.wait()
        self.logger.info("Control loop thread starting (phone infer)")

        events = {
            "phase": "ready",
            "paused": False,
            "hold_nest": False,
            "switching": False,
            "start_trial": False,
            "end_trial": False,
            "mark_success": False,
            "mark_failure": None,
            "undo_last": False,
            "model_delta": 0,
            "pause_changed": False,
            "stop_session": False,
            "release_bus": False,
        }
        preview = FramePreview()
        catalog = load_catalog()
        path0 = str(getattr(self.config, "pretrained_name_or_path", "") or "")
        idx = index_for_path(catalog, path0) if catalog else 0
        status = InferStatus.from_environ(
            model=model_label(path0),
            policy_type=str(getattr(self.config, "policy_type", "") or ""),
            task=task or "",
        )
        if catalog:
            _apply_entry(status, catalog[idx], idx, len(catalog))
        server = None
        staged_nest = make_staged_nest()
        if staged_nest is None:
            print("警告: nest 姿勢を読めません。スマホの nest は動きません。", flush=True)
        dt = float(getattr(self.config, "environment_dt", 1.0 / 30.0) or (1.0 / 30.0))
        recorder = RolloutRecorder.create_if_enabled(
            self.robot,
            task or "",
            fps=max(1, int(round(1.0 / dt))),
            model=status.model_id or status.policy_type,
        )
        last_err = [0.0]
        load_clear_at: float | None = None
        nest_was_on = False
        nest_saved_step: object | None = None
        serial_check_due = 0.0

        try:
            server = start_button_server(events, preview=preview, status=status)
            while self.running and not events.get("stop_session"):
                loop_start = time.perf_counter()
                phase = events.get("phase", "ready")

                if load_clear_at is not None and time.monotonic() >= load_clear_at:
                    status.clear_load()
                    load_clear_at = None

                status.tick_bus()

                if events.pop("release_bus", False):
                    clear_action_queue(self)
                    ok = release_robot_bus(self.robot)
                    msg = (
                        "バス復旧: is_using をクリアしました。観測を再試行します。"
                        if ok
                        else "バス復旧失敗: port_handler がありません。"
                    )
                    status.note_bus(msg)
                    print(msg, flush=True)
                    logger.info(msg)

                now_mono = time.monotonic()
                if now_mono >= serial_check_due:
                    serial_check_due = now_mono + 1.0
                    ok_serial, serial_msg = serial_fd_status()
                    if not ok_serial:
                        status.set_serial(ok=False, message=serial_msg)
                        if now_mono - last_err[0] >= 5.0:
                            last_err[0] = now_mono
                            print(serial_msg, flush=True)
                    elif not status.serial_ok:
                        status.set_serial(ok=True)

                if events.get("pause_changed"):
                    status.set_paused(bool(events.get("paused")))
                    if events.get("paused"):
                        clear_action_queue(self)
                    events["pause_changed"] = False

                if phase == "ready":
                    if events.get("undo_last"):
                        events["undo_last"] = False
                        recorder.undo_last_label()
                        if status.undo_last():
                            print(
                                f"直前の結果を取消。成功 {status.successes} / 試行 {status.trial}"
                                f"（失敗内訳 {status.failures}）",
                                flush=True,
                            )
                        else:
                            print("取り消す結果がありません。", flush=True)
                        continue

                    delta = int(events.get("model_delta") or 0)
                    if delta and catalog and not events.get("switching"):
                        events["model_delta"] = 0
                        new_idx = (idx + delta) % len(catalog)
                        if new_idx != idx:
                            entry = catalog[new_idx]
                            events["switching"] = True
                            events["hold_nest"] = False
                            status.clear_nest()
                            clear_action_queue(self)
                            try:
                                _switch_policy(
                                    self,
                                    status,
                                    entry,
                                    preview=preview,
                                    robot=self.robot,
                                    last_err=last_err,
                                    dt=dt,
                                )
                                idx = new_idx
                                _apply_entry(status, entry, idx, len(catalog))
                                status.reset_scores()
                                load_clear_at = time.monotonic() + 2.5
                            except Exception as exc:
                                logger.exception("model switch failed")
                                print(f"モデル切替失敗: {exc}", flush=True)
                                load_clear_at = time.monotonic() + 4.0
                            finally:
                                events["switching"] = False
                                status.switching = False
                        continue

                    if events.get("start_trial") and not events.get("switching"):
                        events["start_trial"] = False
                        events["paused"] = False
                        events["hold_nest"] = False
                        status.clear_nest()
                        status.clear_load()
                        load_clear_at = None
                        clear_action_queue(self)
                        must_go = getattr(self, "must_go", None)
                        if must_go is not None:
                            must_go.set()
                        recorder.begin_episode(
                            {"model": status.model_id or status.policy_type, "trial": status.trial}
                        )
                        status.begin_trial()
                        events["phase"] = "running"
                        print(
                            f"試行 {status.trial}/{status.total_trials or '—'} 開始"
                            f"（{status.model_id or status.policy_type} · 上限 {status.timeout_s:.0f}s）",
                            flush=True,
                        )
                        continue
                    if events.get("hold_nest") and not events.get("switching"):
                        if events.pop("nest_reset", False) or not nest_was_on:
                            clear_action_queue(self)
                            if staged_nest is not None:
                                staged_nest.reset()
                                nest_pose = staged_nest.nest
                                print(
                                    "nest 目標: "
                                    + ", ".join(f"{k}={nest_pose[k]:.1f}" for k in nest_pose),
                                    flush=True,
                                )
                            torqued = ensure_torque_on(self.robot)
                            nest_saved_step = apply_nest_step(self.robot, nest_step_deg())
                            print(
                                "nest へ移動（先に shoulder_lift のみ → 全体"
                                f"{'、torque ON' if torqued else ''}）…",
                                flush=True,
                            )
                            nest_was_on = True
                        info = step_staged_nest(self.robot, staged_nest)
                        status.set_nest(
                            phase=str(info.get("phase") or ""),
                            message=str(info.get("message") or ""),
                            ok=bool(info.get("ok")),
                        )
                        # Do NOT call get_observation here — cameras freeze the nest loop.
                        time.sleep(max(0.0, 0.05 - (time.perf_counter() - loop_start)))
                        continue
                    if nest_was_on:
                        nest_was_on = False
                        restore_nest_step(self.robot, nest_saved_step)
                        nest_saved_step = None
                        status.clear_nest()
                        print("nest 保持を解除", flush=True)
                    _note_obs(preview, self.robot, where="ready", last_err=last_err)
                    time.sleep(max(0.0, dt - (time.perf_counter() - loop_start)))
                    continue

                if phase == "running":
                    if events.get("end_trial") or status.timed_out():
                        reason = "timeout" if status.timed_out() and not events.get("end_trial") else "halt"
                        events["end_trial"] = False
                        events["paused"] = False
                        clear_action_queue(self)
                        events["phase"] = "result"
                        print(
                            f"試行 {status.trial} 終了（{reason}、{status.elapsed_s():.1f}s）。結果を選んでください。",
                            flush=True,
                        )
                        continue
                    if events.get("paused"):
                        _note_obs(preview, self.robot, where="paused", last_err=last_err)
                        time.sleep(max(0.0, dt - (time.perf_counter() - loop_start)))
                        continue
                    try:
                        if self.actions_available():
                            self.control_loop_action(verbose)
                        if self._ready_to_send_observation():
                            obs = self.control_loop_observation(task, verbose)
                            if obs is not None:
                                preview.note_observation(obs)
                                last_err[0] = 0.0
                        recorder.tick()
                    except Exception as exc:
                        if is_port_busy_error(exc):
                            _recover_busy_bus(self.robot, where="running")
                        now = time.monotonic()
                        if now - last_err[0] >= 2.0:
                            last_err[0] = now
                            logger.warning("running control failed: %s", exc)
                    time.sleep(max(0.0, dt - (time.perf_counter() - loop_start)))
                    continue

                if phase == "result":
                    if events.get("mark_success"):
                        events["mark_success"] = False
                        recorder.label_episode(success=True)
                        status.note_success()
                        print(
                            f"成功 {status.successes} / 試行 {status.trial}"
                            f"（失敗内訳 {status.failures}）",
                            flush=True,
                        )
                        events["phase"] = "ready"
                        continue
                    failure = events.get("mark_failure")
                    if failure:
                        events["mark_failure"] = None
                        recorder.label_episode(success=False, kind=str(failure))
                        status.note_failure(str(failure))
                        print(
                            f"失敗 {failure}。成功 {status.successes} / 試行 {status.trial}"
                            f"（失敗内訳 {status.failures}）",
                            flush=True,
                        )
                        events["phase"] = "ready"
                        continue
                    # Live preview only; skip serial spam if the bus is wedged.
                    _note_obs(preview, self.robot, where="result", last_err=last_err)
                    time.sleep(max(0.0, max(dt, 0.2) - (time.perf_counter() - loop_start)))
                    continue

                time.sleep(max(0.0, dt - (time.perf_counter() - loop_start)))

            events["phase"] = "idle"
            print(
                f"セッション終了。成功 {status.successes} / 試行 {status.trial}"
                f"（失敗内訳 {status.failures}）",
                flush=True,
            )
        finally:
            recorder.close()
            preview.close()
            if server is not None:
                server.stop()
            self.shutdown_event.set()

        return None, None

    RobotClient.control_loop = control_loop
    logger.info("Phone infer controls installed (port %s)", os.environ.get("SO101_INFER_BUTTONS_PORT", "8771"))
    _ = original
