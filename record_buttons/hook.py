"""Attach the phone button server to ``lerobot-record`` without editing vendor code.

``record()`` looks up ``init_keyboard_listener`` and ``record_loop`` as globals
at call time, so replacing those two names on the module is enough.

An episode does not start until Start. Stop opens a review. Only a kept take
is saved, and the copy to the other PC runs after that, before the next Start.
"""

from __future__ import annotations

import os
import sys
import time

from record_buttons.nest import run_ready_with_nest
from record_buttons.offload import current_session
from record_buttons.preview import FramePreview
from record_buttons.server import start_button_server
from record_buttons.status import (
    PauseClock,
    RecordStatus,
    dataset_limits_from_argv,
    install_pause_clock,
)

# Short teleop slice so the nest toggle can be noticed while following.
_READY_SLICE_S = 0.35


def dataset_argument(args: tuple, kwargs: dict) -> object:
    """Return the dataset passed into ``record_loop`` (None during reset)."""
    if "dataset" in kwargs:
        return kwargs["dataset"]
    # record_loop(robot, events, fps, teleop_pp, robot_pp, obs_pp, dataset=...)
    if len(args) > 6:
        return args[6]
    return None


def events_argument(args: tuple, kwargs: dict) -> dict | None:
    if "events" in kwargs and isinstance(kwargs["events"], dict):
        return kwargs["events"]
    if len(args) > 1 and isinstance(args[1], dict):
        return args[1]
    return None


def teleop_argument(args: tuple, kwargs: dict) -> object | None:
    if "teleop" in kwargs:
        return kwargs["teleop"]
    # After dataset in the positional layout used by record().
    if len(args) > 7:
        return args[7]
    return None


def wait_for_decision(events: dict, pause=time.sleep) -> None:
    """Block until keep (``exit_early``), discard, or session stop."""
    while not (
        events.get("exit_early") or events.get("rerecord_episode") or events.get("stop_recording")
    ):
        pause(0.05)


def sync_before_next(events: dict) -> None:
    """Copy kept episodes before the next Start, off the control loop."""
    session = current_session()
    if session is None or not session.needs_sync:
        return
    events["phase"] = "upload"
    session.sync_saved()


def episode_gate(
    events: dict,
    follow,
    record,
    preview: FramePreview,
    sync=sync_before_next,
    pause=time.sleep,
    status: RecordStatus | None = None,
) -> None:
    """Run one episode as ready → record → review.

    ``follow`` teleops without writing frames until Start or session stop.
    ``record`` is the vendor episode loop. Returning with ``rerecord_episode``
    makes ``record()`` drop the buffer instead of saving it. A keep leaves
    that flag clear so the vendor saves, then the next call transfers.
    """
    if events.get("stop_recording"):
        events["rerecord_episode"] = True
        events["exit_early"] = False
        events["paused"] = False
        events["phase"] = "idle"
        return
    if status is not None:
        status.note_saved(status.current_saved())
    sync(events)
    if events.get("stop_recording"):
        events["rerecord_episode"] = True
        events["exit_early"] = False
        events["paused"] = False
        events["phase"] = "idle"
        return
    events["exit_early"] = False
    events["rerecord_episode"] = False
    events["paused"] = False
    events["start_episode"] = False
    # Default OFF: leader follow until Start. Phone "両方 nest へ" opts into nest hold.
    events["hold_nest"] = False
    events["nest_holding"] = False
    if status is not None:
        status.show_take(status.current_saved(), running=False, limit_s=status.episode_time_s)
    events["phase"] = "ready"
    follow()
    events["hold_nest"] = False
    events["nest_holding"] = False
    if events.get("stop_recording") or events.get("rerecord_episode"):
        events["rerecord_episode"] = True
        events["exit_early"] = False
        events["paused"] = False
        events["start_episode"] = False
        events["phase"] = "idle"
        return
    events["exit_early"] = False
    events["start_episode"] = False
    events["paused"] = False
    preview.clear()
    if status is not None:
        status.show_take(status.current_saved(), running=True, limit_s=status.episode_time_s)
    events["phase"] = "record"
    record()
    if status is not None:
        status.freeze()
    events["paused"] = False
    if events.get("stop_recording") or events.get("rerecord_episode"):
        events["rerecord_episode"] = True
        events["exit_early"] = False
        events["paused"] = False
        events["phase"] = "idle"
        return
    if preview.hooked and preview.frame_count <= 0:
        print("フレームが無いので、この本は残しません。", flush=True)
        events["rerecord_episode"] = True
        events["exit_early"] = False
        events["paused"] = False
        events["phase"] = "idle"
        return
    events["exit_early"] = False
    events["phase"] = "review"
    wait_for_decision(events, pause)
    if events.get("stop_recording") or events.get("rerecord_episode"):
        events["rerecord_episode"] = True
    events["exit_early"] = False
    events["paused"] = False
    events["phase"] = "idle"


class CombinedListener:
    """Stop the keyboard listener and the phone server together."""

    def __init__(self, keyboard: object, server: object) -> None:
        self.keyboard = keyboard
        self.server = server
        self._stopped = False

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self.server is not None:
            self.server.stop()
        if self.keyboard is not None and hasattr(self.keyboard, "stop"):
            self.keyboard.stop()


def bind_from_env() -> tuple[str, int]:
    host = os.environ.get("SO101_RECORD_BUTTONS_HOST", "0.0.0.0")
    raw = os.environ.get("SO101_RECORD_BUTTONS_PORT", "8770")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"SO101_RECORD_BUTTONS_PORT が数値ではありません: {raw}") from exc
    if port < 0 or port > 65535:
        raise SystemExit(f"SO101_RECORD_BUTTONS_PORT が範囲外です: {port}")
    return host, port


def install_frame_preview(preview: FramePreview, holder: dict, dataset_mod: object | None = None) -> None:
    """Copy occasional camera frames out of ``add_frame``. Import errors skip preview.

    While ``events['paused']`` is set the frame is not counted and not written.
    The live image comes from ``get_observation`` instead, so the phone still moves.
    """
    if dataset_mod is None:
        try:
            import lerobot.datasets.lerobot_dataset as dataset_mod
        except ImportError:
            print("プレビューは出せません。確認は現場を見て判断してください。", flush=True)
            return
    original_add = dataset_mod.LeRobotDataset.add_frame

    def add_frame(self: object, frame: dict) -> None:
        events = holder.get("events")
        if events and events.get("paused"):
            return
        try:
            preview.note(frame)
        except Exception:
            # A bad frame must not stop the recording loop.
            pass
        original_add(self, frame)

    preview.hooked = True
    dataset_mod.LeRobotDataset.add_frame = add_frame


def _robot_argument(args: tuple, kwargs: dict) -> object | None:
    if "robot" in kwargs:
        return kwargs["robot"]
    if args:
        return args[0]
    return None


def _attach_live_preview(robot: object | None, preview: FramePreview):
    """Sample cameras from ``get_observation``. Return the original method, or None."""
    if robot is None or not hasattr(robot, "get_observation"):
        return None
    original = robot.get_observation

    def get_observation():
        obs = original()
        try:
            preview.note_observation(obs)
        except Exception:
            pass
        return obs

    robot.get_observation = get_observation
    return original


def _detach_live_preview(robot: object | None, original) -> None:
    if robot is not None and original is not None:
        robot.get_observation = original


def _install_keyboard_start_episode() -> None:
    """Keyboard ``n`` during ready/homing must set ``start_episode`` (phone Start does)."""
    try:
        import lerobot.utils.keyboard_input as keyboard_mod
    except ImportError:
        return

    if getattr(keyboard_mod.apply_recording_control, "_record_buttons_start", False):
        return
    original = keyboard_mod.apply_recording_control

    def apply_recording_control(control: str, events: dict) -> None:
        original(control, events)
        if control == "right" and events.get("phase") in ("ready", "homing"):
            if not events.get("stop_recording") and not events.get("rerecord_episode"):
                events["start_episode"] = True

    apply_recording_control._record_buttons_start = True  # type: ignore[attr-defined]
    keyboard_mod.apply_recording_control = apply_recording_control


def install_phone_buttons(host: str | None = None, port: int | None = None) -> None:
    """Patch the record module so the phone page shares its ``events`` dict."""
    import lerobot.scripts.lerobot_record as record_mod

    if host is None or port is None:
        env_host, env_port = bind_from_env()
        host = env_host if host is None else host
        port = env_port if port is None else port

    _install_keyboard_start_episode()
    holder: dict = {"events": None}
    preview = FramePreview()
    install_frame_preview(preview, holder)
    clock = PauseClock(holder)
    status = RecordStatus(clock)
    total, episode_s, reset_s = dataset_limits_from_argv(sys.argv[1:])
    status.configure(total, episode_s, reset_s)
    install_pause_clock(record_mod, clock)
    original_init = record_mod.init_keyboard_listener
    original_loop = record_mod.record_loop

    def init_keyboard_listener():
        _install_keyboard_start_episode()
        listener, events = original_init()
        # Keep any flags the keyboard listener already uses, and add phase.
        if "phase" not in events:
            events["phase"] = "idle"
        events["paused"] = False
        events.setdefault("hold_nest", False)
        events.setdefault("nest_holding", False)
        events.setdefault("start_episode", False)
        holder["events"] = events
        session = current_session()
        if session is not None:
            session.events = events
        server = start_button_server(events, host, port, preview, status)
        if server is not None:
            lines = "\n".join(f"  {line}" for line in server.listen_lines())
            print(
                "\n同じ Wi-Fi のブラウザで開いてください（腕の接続が終わったあとです）:\n"
                f"{lines}\n"
                "エピソード数、記録時間、front_depth（深度）/ wrist を表示します。\n"
                "開始待ちでは「両方 nest へ」トグルで両腕を nest に動かして保持できます"
                "（まず手首 ID4 を nest 角度へ、そのあと他の関節を戻します）。\n"
                "記録開始、記録終了、一時停止。残すか捨てるかは止めたあとです。\n"
                "キーボードの n / r / q も使えます。一時停止と nest はブラウザだけです。\n",
                flush=True,
            )
        return CombinedListener(listener, server), events

    def record_loop(*args, **kwargs):
        events = events_argument(args, kwargs)
        dataset = dataset_argument(args, kwargs)
        if events is None:
            return original_loop(*args, **kwargs)
        if dataset is not None:
            status.dataset = dataset
        robot = _robot_argument(args, kwargs)
        teleop = teleop_argument(args, kwargs)
        original_get = _attach_live_preview(robot, preview)
        try:
            if dataset is None:
                events["paused"] = False
                # 残す / 捨てるのどちらでも reset_time_s 待ちと「成功」ボタンを挟まない。
                # 物と腕の戻しは次の開始待ち（leader 追従）で行い、揃ったら記録開始。
                events["phase"] = "idle"
                return

            def follow_slice() -> None:
                call = dict(kwargs)
                call["dataset"] = None
                call["control_time_s"] = _READY_SLICE_S
                call["timer"] = None
                original_loop(*args, **call)

            def follow() -> None:
                run_ready_with_nest(
                    events=events,
                    robot=robot,
                    teleop=teleop,
                    follow_slice=follow_slice,
                )

            def record() -> None:
                original_loop(*args, **kwargs)

            try:
                episode_gate(events, follow, record, preview, status=status)
            finally:
                # Between episodes (save, speech) the page should say 待機,
                # unless a transfer is already on screen.
                if events.get("phase") not in ("upload",):
                    events["phase"] = "idle"
        finally:
            _detach_live_preview(robot, original_get)

    record_mod.init_keyboard_listener = init_keyboard_listener
    record_mod.record_loop = record_loop
