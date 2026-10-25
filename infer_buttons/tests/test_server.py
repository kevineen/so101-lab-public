"""Unit tests for the infer phone board (no robot, no gRPC)."""

from __future__ import annotations

import unittest

from infer_buttons.catalog import ModelEntry, index_for_path, load_catalog
from infer_buttons.serial_health import is_port_busy_error, release_bus_port
from infer_buttons.server import ButtonBoard, apply_phone_control, origin_allowed
from infer_buttons.status import InferStatus, FAILURE_KINDS
from infer_buttons.hook import clear_action_queue, model_label
from so101_common.nest_stages import StagedNest, lift_then_all_targets


class FakeQueue:
    def __init__(self) -> None:
        self.items: list[object] = []

    def empty(self) -> bool:
        return not self.items

    def get_nowait(self) -> object:
        return self.items.pop(0)

    def put(self, item: object) -> None:
        self.items.append(item)

    def qsize(self) -> int:
        return len(self.items)


class FakeClient:
    def __init__(self) -> None:
        import threading

        self.action_queue_lock = threading.Lock()
        self.action_queue = FakeQueue()
        self.action_queue.put("a")


class StatusTests(unittest.TestCase):
    def test_timeout_and_score(self) -> None:
        status = InferStatus(timeout_s=0.01, total_trials=3)
        status.begin_trial()
        self.assertEqual(status.trial, 1)
        status.set_paused(True)
        elapsed_paused = status.elapsed_s()
        self.assertGreaterEqual(elapsed_paused, 0.0)
        status.set_paused(False)
        status.note_success()
        self.assertEqual(status.successes, 1)
        self.assertEqual(status.last_result, "success")
        status.begin_trial()
        status.note_failure("no_grasp")
        self.assertEqual(status.failures["no_grasp"], 1)
        self.assertEqual(set(FAILURE_KINDS), set(status.failures))

    def test_undo_last(self) -> None:
        status = InferStatus(total_trials=10)
        status.begin_trial()
        status.note_success()
        self.assertTrue(status.undo_last())
        self.assertEqual(status.successes, 0)
        self.assertEqual(status.trial, 0)
        self.assertEqual(status.last_result, "")
        self.assertFalse(status.undo_last())
        status.begin_trial()
        status.note_failure("no_reach")
        self.assertTrue(status.undo_last())
        self.assertEqual(status.failures["no_reach"], 0)

    def test_load_progress(self) -> None:
        status = InferStatus()
        status.begin_load("SB2 · Diffusion")
        pub = status.public()
        self.assertTrue(pub["switching"])
        self.assertTrue(pub["loading"])
        self.assertEqual(pub["load_target"], "SB2 · Diffusion")
        status.set_load("wait_server", "読み込み中…", 40)
        pub2 = status.public()
        self.assertGreaterEqual(pub2["load_pct"], 40)
        status.end_load(ok=True, message="完了")
        pub3 = status.public()
        self.assertFalse(pub3["switching"])
        self.assertEqual(pub3["load_phase"], "done")
        self.assertEqual(pub3["load_pct"], 100)


class ControlTests(unittest.TestCase):
    def test_phase_gates(self) -> None:
        events = {"phase": "ready", "paused": False, "hold_nest": False}
        apply_phone_control("start", events)
        self.assertTrue(events["start_trial"])
        events["phase"] = "running"
        apply_phone_control("pause", events)
        self.assertTrue(events["paused"])
        apply_phone_control("halt", events)
        self.assertTrue(events["end_trial"])
        events["phase"] = "result"
        apply_phone_control("fail_no_place", events)
        self.assertEqual(events["mark_failure"], "no_place")
        with self.assertRaises(ValueError):
            apply_phone_control("start", events)

    def test_board_pending(self) -> None:
        events = {
            "phase": "ready",
            "paused": False,
            "hold_nest": False,
            "start_trial": False,
            "end_trial": False,
            "mark_success": False,
            "mark_failure": None,
            "stop_session": False,
        }
        status = InferStatus(model="act_demo", policy_type="act", total_trials=10, timeout_s=60)
        board = ButtonBoard(events, status=status)
        code, payload = board.submit("start")
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        code2, payload2 = board.submit("start")
        self.assertEqual(code2, 409)
        self.assertEqual(payload2["error"], "pending")

    def test_origin(self) -> None:
        self.assertTrue(origin_allowed(None, "192.168.77.10:8771"))
        self.assertTrue(origin_allowed("http://192.168.77.10:8771", "192.168.77.10:8771"))
        self.assertFalse(origin_allowed("http://evil.example", "192.168.77.10:8771"))


class HookHelpersTests(unittest.TestCase):
    def test_clear_queue(self) -> None:
        client = FakeClient()
        self.assertFalse(client.action_queue.empty())
        clear_action_queue(client)
        self.assertTrue(client.action_queue.empty())

    def test_model_label(self) -> None:
        self.assertEqual(
            model_label("/home/x/act_snakebowl_frontwrist-base_20261023"),
            "act_snakebowl_frontwrist-base_20261023",
        )
        self.assertEqual(
            model_label(
                "/home/x/outputs/train/act_demo/checkpoints/last/pretrained_model"
            ),
            "act_demo",
        )


class CatalogTests(unittest.TestCase):
    def test_load_snakebowl_skips_optional(self) -> None:
        entries = load_catalog()
        ids = [e.id for e in entries]
        self.assertIn("SB1", ids)
        self.assertIn("SB2", ids)
        self.assertIn("SB3", ids)
        self.assertNotIn("SB4", ids)

    def test_index_for_path(self) -> None:
        entries = [
            ModelEntry("A", "ACT", "act", "/tmp/a/pretrained_model", 100),
            ModelEntry("B", "Diff", "diffusion", "/tmp/b/pretrained_model", 32),
        ]
        self.assertEqual(index_for_path(entries, "/tmp/b/pretrained_model"), 1)

    def test_model_switch_control(self) -> None:
        events = {"phase": "ready", "paused": False, "hold_nest": False, "switching": False}
        apply_phone_control("model_next", events)
        self.assertEqual(events["model_delta"], 1)

    def test_undo_and_nest_reset(self) -> None:
        events = {
            "phase": "ready",
            "paused": False,
            "hold_nest": False,
            "switching": False,
            "undo_last": False,
        }
        apply_phone_control("undo", events)
        self.assertTrue(events["undo_last"])
        apply_phone_control("nest", events)
        self.assertTrue(events["hold_nest"])
        self.assertTrue(events["nest_reset"])

    def test_bus_release_control(self) -> None:
        events = {
            "phase": "ready",
            "paused": False,
            "hold_nest": False,
            "release_bus": False,
        }
        apply_phone_control("bus_release", events)
        self.assertTrue(events["release_bus"])
        events["phase"] = "result"
        events["release_bus"] = False
        apply_phone_control("bus_release", events)
        self.assertTrue(events["release_bus"])

    def test_bus_release_while_pending(self) -> None:
        events = {
            "phase": "ready",
            "paused": False,
            "hold_nest": False,
            "start_trial": True,
            "end_trial": False,
            "mark_success": False,
            "mark_failure": None,
            "stop_session": False,
            "release_bus": False,
        }
        board = ButtonBoard(events, status=InferStatus())
        code, payload = board.submit("bus_release")
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(events["release_bus"])


class BusHealthTests(unittest.TestCase):
    def test_release_clears_is_using(self) -> None:
        class Port:
            def __init__(self) -> None:
                self.is_using = True
                self.is_open = True
                self.cleared = False

            def clearPort(self) -> None:
                self.cleared = True

        class Bus:
            def __init__(self) -> None:
                self.port_handler = Port()

        bus = Bus()
        self.assertTrue(release_bus_port(bus))
        self.assertFalse(bus.port_handler.is_using)
        self.assertTrue(bus.port_handler.cleared)

    def test_port_busy_detect(self) -> None:
        self.assertTrue(
            is_port_busy_error(
                ConnectionError(
                    "Failed to sync read 'Present_Position' after 3 tries. [TxRxResult] Port is in use!"
                )
            )
        )
        self.assertFalse(is_port_busy_error(RuntimeError("camera timeout")))


class StagedNestTests(unittest.TestCase):
    def test_lift_commands_only_shoulder(self) -> None:
        nest = {
            "shoulder_pan": 1.0,
            "shoulder_lift": 50.0,
            "elbow_flex": 2.0,
            "wrist_flex": 3.0,
            "wrist_roll": 4.0,
            "gripper": 5.0,
        }
        current = {"shoulder_lift": 10.0, "elbow_flex": 20.0}
        lift_only, full = lift_then_all_targets(current, nest)
        self.assertEqual(lift_only, {"shoulder_lift": 50.0})
        self.assertIn("shoulder_pan", full)

    def test_phase_advances_to_all(self) -> None:
        nest = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 50.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 0.0,
        }
        staged = StagedNest(nest, tol_deg=3.0)
        far = {k: 0.0 for k in nest}
        far["shoulder_lift"] = 10.0
        a1 = staged.action_from_current(far)
        self.assertEqual(staged.phase, "lift")
        self.assertEqual(list(a1.keys()), ["shoulder_lift.pos"])
        self.assertEqual(a1["shoulder_lift.pos"], 50.0)
        near = dict(far)
        near["shoulder_lift"] = 49.0
        a2 = staged.action_from_current(near)
        self.assertEqual(staged.phase, "all")
        self.assertEqual(a2["elbow_flex.pos"], 0.0)

    def test_stuck_forces_all(self) -> None:
        nest = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 50.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 0.0,
        }
        staged = StagedNest(nest, stuck_ticks_before_all=3)
        for _ in range(3):
            staged.note_no_progress()
        self.assertEqual(staged.phase, "all")


if __name__ == "__main__":
    unittest.main()
