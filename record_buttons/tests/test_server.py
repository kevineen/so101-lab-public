"""Phone buttons start, stop, review, and keep a take, without a robot."""

from __future__ import annotations

import json
import sys
import threading
import time
import types
import unittest
import urllib.error
import urllib.request

from record_buttons.hook import CombinedListener, episode_gate, install_frame_preview, install_phone_buttons
from record_buttons.preview import FramePreview
from record_buttons.server import (
    ButtonBoard,
    fresh_events,
    origin_allowed,
    preferred_interfaces,
    start_button_server,
)
from record_buttons.status import (
    PauseClock,
    RecordStatus,
    dataset_limits_from_argv,
    install_pause_clock,
)


def _open(url: str, method: str = "GET", origin: str | None = None) -> tuple[int, bytes]:
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    if origin is not None:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=2) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class FlagTests(unittest.TestCase):
    def test_start_matches_next_while_waiting(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        code, payload = ButtonBoard(events).submit("start")
        self.assertEqual(code, 200)
        self.assertTrue(events["exit_early"])
        self.assertFalse(events["rerecord_episode"])
        self.assertFalse(events["stop_recording"])
        self.assertTrue(payload["pending"])
        self.assertEqual(payload["last"], "start")

    def test_halt_ends_the_take_without_discarding(self) -> None:
        events = fresh_events()
        events["phase"] = "record"
        code, _payload = ButtonBoard(events).submit("halt")
        self.assertEqual(code, 200)
        self.assertTrue(events["exit_early"])
        self.assertFalse(events["rerecord_episode"])

    def test_keep_during_review_does_not_mark_rerecord(self) -> None:
        events = fresh_events()
        events["phase"] = "review"
        ButtonBoard(events).submit("keep")
        self.assertTrue(events["exit_early"])
        self.assertFalse(events["rerecord_episode"])

    def test_discard_matches_rerecord(self) -> None:
        events = fresh_events()
        events["phase"] = "review"
        code, _payload = ButtonBoard(events).submit("discard")
        self.assertEqual(code, 200)
        self.assertTrue(events["exit_early"])
        self.assertTrue(events["rerecord_episode"])

    def test_stop_during_record_discards_the_open_take(self) -> None:
        events = fresh_events()
        events["phase"] = "record"
        ButtonBoard(events).submit("stop")
        self.assertTrue(events["stop_recording"])
        self.assertTrue(events["exit_early"])
        self.assertTrue(events["rerecord_episode"])

    def test_stop_during_reset_keeps_the_accepted_take(self) -> None:
        events = fresh_events()
        events["phase"] = "reset"
        ButtonBoard(events).submit("stop")
        self.assertTrue(events["stop_recording"])
        self.assertFalse(events["rerecord_episode"])

    def test_button_for_another_phase_is_rejected(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        code, payload = ButtonBoard(events).submit("keep")
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "phase")
        self.assertFalse(events["exit_early"])

    def test_second_press_waits_until_the_loop_consumes_the_first(self) -> None:
        events = fresh_events()
        events["phase"] = "review"
        board = ButtonBoard(events)
        self.assertEqual(board.submit("keep")[0], 200)
        code, payload = board.submit("discard")
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "pending")
        self.assertFalse(events["rerecord_episode"])
        events["exit_early"] = False
        self.assertEqual(board.submit("discard")[0], 200)
        self.assertTrue(events["rerecord_episode"])

    def test_success_during_reset_does_not_undo_failure(self) -> None:
        events = fresh_events()
        events["phase"] = "reset"
        board = ButtonBoard(events)
        board.submit("failure")
        events["exit_early"] = False
        board.submit("success")
        self.assertTrue(events["rerecord_episode"])
        self.assertTrue(events["exit_early"])

    def test_unknown_control(self) -> None:
        code, payload = ButtonBoard(fresh_events()).submit("maybe")
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "unknown")

    def test_pause_freezes_the_flag_without_ending_the_take(self) -> None:
        events = fresh_events()
        events["phase"] = "record"
        board = ButtonBoard(events)
        code, payload = board.submit("pause")
        self.assertEqual(code, 200)
        self.assertTrue(events["paused"])
        self.assertFalse(events["exit_early"])
        self.assertFalse(payload["pending"])
        code, _payload = board.submit("halt")
        self.assertEqual(code, 200)
        self.assertTrue(events["exit_early"])
        self.assertFalse(events["rerecord_episode"])

    def test_pause_again_resumes(self) -> None:
        events = fresh_events()
        events["phase"] = "record"
        board = ButtonBoard(events)
        board.submit("pause")
        code, payload = board.submit("pause")
        self.assertEqual(code, 200)
        self.assertFalse(events["paused"])
        self.assertFalse(payload["paused"])

    def test_pause_outside_record_or_reset_is_rejected(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        code, payload = ButtonBoard(events).submit("pause")
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "phase")
        self.assertFalse(events["paused"])


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = fresh_events()
        self.server = start_button_server(self.events, "127.0.0.1", 0)
        assert self.server is not None
        self.url = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self) -> None:
        if self.server is not None:
            self.server.stop()

    def test_page_offers_start_stop_and_keep(self) -> None:
        code, body = _open(self.url + "/")
        self.assertEqual(code, 200)
        text = body.decode()
        self.assertIn('id="start"', text)
        self.assertIn('id="halt"', text)
        self.assertIn('id="pause"', text)
        self.assertIn('id="nest"', text)
        self.assertIn("両方 nest へ", text)
        self.assertIn('id="clock"', text)
        self.assertIn('id="progress"', text)
        self.assertIn('id="keep"', text)
        self.assertIn('id="discard"', text)
        collapsed = text.replace("<small>", "<")
        self.assertIn(">記録開始<", collapsed)
        self.assertIn(">記録終了<", collapsed)
        self.assertIn(">一時停止<", text)
        self.assertIn('"/live/"', text)
        self.assertIn('fetch("/api/" + name', text)
        self.assertIn("残すと保存し、すぐ次の開始待ちへ進みます", text)

    def test_post_start_while_ready(self) -> None:
        self.events["phase"] = "ready"
        code, body = _open(self.url + "/api/start", method="POST")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertTrue(payload["pending"])
        self.assertTrue(self.events["exit_early"])

    def test_cross_origin_post_is_rejected(self) -> None:
        code, payload_bytes = _open(
            self.url + "/api/failure",
            method="POST",
            origin="http://evil.example",
        )
        self.assertEqual(code, 403)
        self.assertFalse(self.events["rerecord_episode"])
        self.assertEqual(json.loads(payload_bytes)["error"], "origin")

    def test_same_origin_post_is_accepted(self) -> None:
        self.events["phase"] = "review"
        code, _body = _open(
            self.url + "/api/discard",
            method="POST",
            origin=self.url,
        )
        self.assertEqual(code, 200)
        self.assertTrue(self.events["rerecord_episode"])

    def test_state_includes_episode_and_clock(self) -> None:
        holder = {"events": self.events}
        clock = PauseClock(holder)
        status = RecordStatus(clock)
        status.configure(5, 30, 15)
        status.show_take(1, running=False, limit_s=30)
        self.server._httpd.board.session = status
        code, body = _open(self.url + "/api/state")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["episode"], 2)
        self.assertEqual(payload["saved"], 1)
        self.assertEqual(payload["total"], 5)
        self.assertEqual(payload["limit_s"], 30)
        self.assertEqual(payload["elapsed_s"], 0)
        self.assertIn("paused", payload)

    def test_live_jpeg_route(self) -> None:
        preview = FramePreview()
        try:
            preview._live["front"] = b"\xff\xd8\xff\xd9"
            preview._live_seq = 1
            self.server._httpd.board.preview = preview
            code, body = _open(self.url + "/live/front.jpg")
            self.assertEqual(code, 200)
            self.assertTrue(body.startswith(b"\xff\xd8"))
            missing, _payload = _open(self.url + "/live/nope.jpg")
            self.assertEqual(missing, 404)
        finally:
            preview.close()

    def test_stop_closes_the_port(self) -> None:
        self.server.stop()
        with self.assertRaises(urllib.error.URLError):
            _open(self.url + "/api/state")


class GateTests(unittest.TestCase):
    def test_stop_while_waiting_does_not_record(self) -> None:
        events = fresh_events()
        calls: list[str] = []

        def follow() -> None:
            calls.append("follow")
            events["stop_recording"] = True

        def record() -> None:
            calls.append("record")

        preview = FramePreview()
        try:
            episode_gate(events, follow, record, preview, sync=lambda _events: None, pause=lambda _seconds: None)
        finally:
            preview.close()
        self.assertEqual(calls, ["follow"])
        self.assertTrue(events["rerecord_episode"])
        self.assertEqual(events["phase"], "idle")

    def test_keep_after_frames_leaves_the_take(self) -> None:
        events = fresh_events()
        preview = FramePreview()
        preview.hooked = True

        def follow() -> None:
            return None

        def record() -> None:
            preview.frame_count = 4

        def pause(_seconds: float) -> None:
            events["exit_early"] = True

        try:
            episode_gate(events, follow, record, preview, sync=lambda _events: None, pause=pause)
        finally:
            preview.close()
        self.assertFalse(events["rerecord_episode"])
        self.assertEqual(events["phase"], "idle")
        self.assertFalse(events["exit_early"])

    def test_empty_hooked_take_is_discarded(self) -> None:
        events = fresh_events()
        preview = FramePreview()
        preview.hooked = True

        def pause(_seconds: float) -> None:
            raise AssertionError("empty take should not wait for review")

        try:
            episode_gate(
                events,
                lambda: None,
                lambda: None,
                preview,
                sync=lambda _events: None,
                pause=pause,
            )
        finally:
            preview.close()
        self.assertTrue(events["rerecord_episode"])


class PreviewTests(unittest.TestCase):
    def test_first_frame_becomes_a_jpeg(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not installed")
        preview = FramePreview()
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        image[0, 0] = (255, 0, 0)
        try:
            preview.note({"observation.images.front": image})
            blob = None
            for _ in range(50):
                blob = preview.jpeg("front", 0)
                if blob:
                    break
                time.sleep(0.02)
        finally:
            preview.close()
        if not blob:
            self.skipTest("opencv could not encode a preview")
        self.assertTrue(blob.startswith(b"\xff\xd8"))
        self.assertEqual(preview.info()["frames"], 1)

    def test_observation_becomes_a_live_jpeg(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not installed")
        preview = FramePreview()
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        image[0, 0] = (0, 255, 0)
        try:
            preview.note_observation({"front": image})
            blob = None
            for _ in range(50):
                blob = preview.live_jpeg("front")
                if blob:
                    break
                time.sleep(0.02)
        finally:
            preview.close()
        if not blob:
            self.skipTest("opencv could not encode a preview")
        self.assertTrue(blob.startswith(b"\xff\xd8"))
        self.assertEqual(preview.info()["live_seq"], 1)
        self.assertIn("front", preview.info()["cameras"])

    def test_depth_observation_prefers_colorized_depth(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not installed")
        from record_buttons.preview import images_from_mapping

        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        rgb[:] = (10, 20, 30)
        depth = np.zeros((8, 8, 1), dtype=np.uint16)
        depth[2:6, 2:6] = 1500
        images = images_from_mapping(
            {
                "observation.images.front": rgb,
                "observation.images.front_depth": depth,
                "observation.images.wrist": rgb,
            }
        )
        self.assertIn("front_depth", images)
        self.assertIn("wrist", images)
        self.assertNotIn("front", images)
        self.assertEqual(images["front_depth"].shape, (8, 8, 3))
        self.assertEqual(images["front_depth"].dtype, np.uint8)
        # Valid depth pixels leave black; a mid-range point should be colored.
        self.assertFalse(np.array_equal(images["front_depth"][4, 4], (0, 0, 0)))

        preview = FramePreview()
        try:
            preview.note_observation(
                {"front": rgb, "front_depth": depth, "wrist": rgb}
            )
            blob = None
            for _ in range(50):
                blob = preview.live_jpeg("front_depth")
                if blob:
                    break
                time.sleep(0.02)
        finally:
            preview.close()
        if not blob:
            self.skipTest("opencv could not encode a depth preview")
        self.assertTrue(blob.startswith(b"\xff\xd8"))
        self.assertIn("front_depth", preview.info()["cameras"])
        self.assertNotIn("front", preview.info()["cameras"])


class PauseTests(unittest.TestCase):
    def test_cli_limits_match_the_record_command(self) -> None:
        argv = [
            "--robot.type=so101_follower",
            "--dataset.num_episodes=5",
            "--dataset.episode_time_s=30",
            "--dataset.reset_time_s=15",
        ]
        self.assertEqual(dataset_limits_from_argv(argv), (5, 30.0, 15.0))

    def test_cli_limits_accept_a_separate_value(self) -> None:
        argv = ["--dataset.num_episodes", "2", "--dataset.episode_time_s", "10"]
        episodes, episode_s, reset_s = dataset_limits_from_argv(argv)
        self.assertEqual(episodes, 2)
        self.assertEqual(episode_s, 10.0)
        self.assertEqual(reset_s, 60.0)

    def test_pause_clock_does_not_move_the_real_clock(self) -> None:
        mod = types.ModuleType("fake_record")
        mod.time = time
        events = {"paused": False}
        clock = PauseClock({"events": events})
        install_pause_clock(mod, clock)
        start = time.perf_counter()
        events["paused"] = True
        frozen = mod.time.perf_counter()
        time.sleep(0.06)
        self.assertLess(abs(mod.time.perf_counter() - frozen), 0.03)
        self.assertGreater(time.perf_counter() - start, 0.05)
        events["paused"] = False
        resumed = mod.time.perf_counter()
        time.sleep(0.06)
        self.assertGreater(mod.time.perf_counter() - resumed, 0.04)

    def test_status_clock_stays_put_while_paused(self) -> None:
        events = {"paused": False}
        clock = PauseClock({"events": events})
        now = {"t": 10.0}
        clock._real = lambda: now["t"]
        status = RecordStatus(clock)
        status.configure(5, 30, 15)
        status.show_take(0, running=True, limit_s=30)
        now["t"] = 14.0
        self.assertAlmostEqual(status.public()["elapsed_s"], 4.0)
        self.assertEqual(status.public()["episode"], 1)
        events["paused"] = True
        clock.perf_counter()
        now["t"] = 20.0
        self.assertAlmostEqual(status.public()["elapsed_s"], 4.0)
        events["paused"] = False
        now["t"] = 21.0
        self.assertAlmostEqual(status.public()["elapsed_s"], 4.0)
        now["t"] = 22.0
        self.assertAlmostEqual(status.public()["elapsed_s"], 5.0)
        status.freeze()
        now["t"] = 50.0
        self.assertAlmostEqual(status.public()["elapsed_s"], 5.0)

    def test_paused_add_frame_is_not_written(self) -> None:
        preview = FramePreview()
        holder = {"events": {"paused": True}}
        dataset_mod = types.ModuleType("fake_dataset")

        class LeRobotDataset:
            def add_frame(self, frame: dict) -> None:
                self.frame = frame

        dataset_mod.LeRobotDataset = LeRobotDataset
        try:
            install_frame_preview(preview, holder, dataset_mod)
            episode = LeRobotDataset()
            episode.add_frame({"observation.images.front": "skip"})
            self.assertFalse(hasattr(episode, "frame"))
            self.assertEqual(preview.frame_count, 0)
            holder["events"]["paused"] = False
            episode.add_frame({"observation.images.front": "keep"})
            self.assertEqual(episode.frame, {"observation.images.front": "keep"})
            self.assertEqual(preview.frame_count, 1)
        finally:
            preview.close()


class InterfaceTests(unittest.TestCase):
    def test_wifi_is_listed_before_virtual_nets(self) -> None:
        pairs = preferred_interfaces(
            [
                ("tailscale0", "100.1.2.3"),
                ("docker0", "172.17.0.1"),
                ("eth0", "192.168.77.10"),
                ("wlan0", "192.168.1.11"),
            ]
        )
        self.assertEqual(pairs, [("wlan0", "192.168.1.11"), ("eth0", "192.168.77.10")])


class OriginTests(unittest.TestCase):
    def test_curl_has_no_origin(self) -> None:
        self.assertTrue(origin_allowed(None, "192.168.77.10:8770"))

    def test_page_origin_matches_host(self) -> None:
        self.assertTrue(origin_allowed("http://192.168.77.10:8770", "192.168.77.10:8770"))
        self.assertFalse(origin_allowed("http://evil.example", "192.168.77.10:8770"))


class HookTests(unittest.TestCase):
    def test_install_shares_events_and_reports_phase(self) -> None:
        saved = {
            name: sys.modules.get(name)
            for name in (
                "lerobot",
                "lerobot.scripts",
                "lerobot.scripts.lerobot_record",
            )
        }
        seen: dict[str, str] = {}
        keyboard = CombinedListener(None, None)
        keyboard.stop = lambda: seen.__setitem__("keyboard", "stopped")  # type: ignore[method-assign]

        def init():
            return keyboard, fresh_events()

        def loop(*_args, **kwargs):
            seen["during"] = kwargs["events"]["phase"]
            return "ok"

        lerobot_mod = types.ModuleType("lerobot")
        lerobot_mod.__path__ = []  # type: ignore[attr-defined]
        scripts_mod = types.ModuleType("lerobot.scripts")
        scripts_mod.__path__ = []  # type: ignore[attr-defined]
        record_mod = types.ModuleType("lerobot.scripts.lerobot_record")
        record_mod.init_keyboard_listener = init
        record_mod.record_loop = loop
        sys.modules["lerobot"] = lerobot_mod
        sys.modules["lerobot.scripts"] = scripts_mod
        sys.modules["lerobot.scripts.lerobot_record"] = record_mod
        try:
            install_phone_buttons(host="127.0.0.1", port=0)
            listener, events = record_mod.init_keyboard_listener()
            self.assertIsNotNone(listener.server)

            def release_review() -> None:
                for _ in range(200):
                    # Ready starts in leader follow; Start ends the gate like the phone.
                    if events.get("phase") in ("ready", "homing") and not events.get("start_episode"):
                        events["start_episode"] = True
                        events["exit_early"] = True
                    if events.get("phase") == "review":
                        events["exit_early"] = True
                        return
                    time.sleep(0.02)

            threading.Thread(target=release_review, daemon=True).start()
            record_mod.record_loop(dataset=object(), events=events)
            self.assertEqual(seen["during"], "record")
            self.assertEqual(events["phase"], "idle")
            # After keep, the vendor reset slice is skipped (no 「成功」 step).
            seen.pop("during", None)
            record_mod.record_loop(events=events)
            self.assertNotIn("during", seen)
            self.assertEqual(events["phase"], "idle")
            listener.stop()
            self.assertEqual(seen["keyboard"], "stopped")
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_busy_port_does_not_raise(self) -> None:
        first = start_button_server(fresh_events(), "127.0.0.1", 0)
        assert first is not None
        try:
            second = start_button_server(fresh_events(), "127.0.0.1", first.port)
            self.assertIsNone(second)
        finally:
            first.stop()


if __name__ == "__main__":
    unittest.main()
