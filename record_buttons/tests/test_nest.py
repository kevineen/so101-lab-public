"""Unit tests for the slow nest approach / hold at record start."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from record_buttons.nest import (
    _STUCK_TICKS_BEFORE_ALL,
    approach_follower_nest,
    first_stage_target,
    nest_enabled,
    nest_first_joint,
    run_ready_with_nest,
    step_toward,
    tick_nest_both,
)
from record_buttons.server import ButtonBoard, apply_phone_control, fresh_events


class NestEnvTests(unittest.TestCase):
    def test_nest_enabled_default(self) -> None:
        self.assertTrue(nest_enabled())

    def test_nest_disabled_by_env(self) -> None:
        with patch.dict("os.environ", {"SO101_RECORD_GO_HOME": "0"}):
            self.assertFalse(nest_enabled())


class StepTests(unittest.TestCase):
    def test_step_toward_clamps(self) -> None:
        current = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 0.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 0.0,
        }
        target = {**current, "shoulder_pan": 10.0}
        stepped = step_toward(current, target, 2.0)
        self.assertEqual(stepped["shoulder_pan"], 2.0)


class ApproachTests(unittest.TestCase):
    def test_skip_when_disabled(self) -> None:
        robot = MagicMock()
        with patch.dict("os.environ", {"SO101_RECORD_GO_HOME": "0"}):
            self.assertTrue(approach_follower_nest(robot, pause=lambda _s: None))
        robot.send_action.assert_not_called()

    def test_restores_max_relative_target_and_stops_near_home(self) -> None:
        target = {
            "shoulder_pan": 1.0,
            "shoulder_lift": -79.0,
            "elbow_flex": 36.0,
            "wrist_flex": 50.0,
            "wrist_roll": -81.0,
            "gripper": 1.0,
        }
        obs = {f"{k}.pos": v for k, v in target.items()}
        robot = MagicMock()
        robot.config = SimpleNamespace(max_relative_target=None)
        robot.get_observation.return_value = obs
        sleeps: list[float] = []

        with patch(
            "record_buttons.nest.joints_for_arm",
            return_value=(target, True),
        ):
            ok = approach_follower_nest(
                robot,
                step_deg=2.0,
                hz=20.0,
                timeout_s=5.0,
                pause=sleeps.append,
            )

        self.assertTrue(ok)
        robot.send_action.assert_called()
        self.assertIsNone(robot.config.max_relative_target)
        self.assertEqual(sleeps, [])


class BothArmsTests(unittest.TestCase):
    def test_tick_drives_follower_and_leader(self) -> None:
        target = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 0.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 50.0,
        }
        pos = {f"{k}.pos": v for k, v in target.items()}
        robot = MagicMock()
        robot.config = SimpleNamespace(max_relative_target=None)
        robot.get_observation.return_value = pos
        teleop = MagicMock()
        teleop.get_action.return_value = pos

        near_f, near_l = tick_nest_both(
            robot,
            teleop,
            {"follower": target, "leader": target},
            step_deg=2.0,
        )
        self.assertTrue(near_f)
        self.assertTrue(near_l)
        robot.send_action.assert_called()
        teleop.send_feedback.assert_called()

    def test_ready_hold_then_start(self) -> None:
        target = {
            "shoulder_pan": 0.0,
            "shoulder_lift": 0.0,
            "elbow_flex": 0.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 50.0,
        }
        pos = {f"{k}.pos": v for k, v in target.items()}
        robot = MagicMock()
        robot.config = SimpleNamespace(max_relative_target=None)
        robot.get_observation.return_value = pos
        teleop = MagicMock()
        teleop.get_action.return_value = pos
        events = {
            "hold_nest": True,
            "start_episode": False,
            "stop_recording": False,
            "rerecord_episode": False,
            "phase": "ready",
            "exit_early": False,
        }
        slices = 0

        def follow_slice() -> None:
            nonlocal slices
            slices += 1

        def pause(_s: float) -> None:
            events["start_episode"] = True

        with patch(
            "record_buttons.nest.load_nest_targets",
            return_value={"follower": target, "leader": target},
        ):
            run_ready_with_nest(
                events=events,
                robot=robot,
                teleop=teleop,
                follow_slice=follow_slice,
                pause=pause,
            )

        self.assertEqual(slices, 0)
        teleop.enable_torque.assert_called()
        teleop.disable_torque.assert_called()
        self.assertFalse(events["nest_holding"])


class StagedFirstJointTests(unittest.TestCase):
    """ nest は wrist_flex（ID4）を先に戻してから全身を戻す。"""

    NEST = {
        "shoulder_pan": 0.0,
        "shoulder_lift": -79.0,
        "elbow_flex": 36.0,
        "wrist_flex": 50.0,
        "wrist_roll": -81.0,
        "gripper": 1.0,
    }

    def _arms(self, current: dict[str, float]):
        pos = {f"{k}.pos": v for k, v in current.items()}
        robot = MagicMock()
        robot.config = SimpleNamespace(max_relative_target=None)
        robot.get_observation.return_value = pos
        teleop = MagicMock()
        teleop.get_action.return_value = pos
        return robot, teleop

    def _events(self) -> dict:
        return {
            "hold_nest": True,
            "start_episode": False,
            "stop_recording": False,
            "rerecord_episode": False,
            "phase": "ready",
            "exit_early": False,
        }

    def _run(self, robot, teleop, events: dict, pause) -> None:
        with patch(
            "record_buttons.nest.load_nest_targets",
            return_value={"follower": dict(self.NEST), "leader": dict(self.NEST)},
        ):
            run_ready_with_nest(
                events=events,
                robot=robot,
                teleop=teleop,
                follow_slice=lambda: None,
                pause=pause,
            )

    def test_first_stage_commands_only_wrist(self) -> None:
        robot, teleop = self._arms({key: 0.0 for key in self.NEST})
        events = self._events()

        def pause(_s: float) -> None:
            events["hold_nest"] = False
            events["stop_recording"] = True

        self._run(robot, teleop, events, pause)

        follower_calls = robot.send_action.call_args_list
        self.assertEqual(len(follower_calls), 1)
        self.assertEqual(set(follower_calls[0][0][0]), {"wrist_flex.pos"})
        leader_calls = teleop.send_feedback.call_args_list
        self.assertEqual(len(leader_calls), 1)
        self.assertEqual(set(leader_calls[0][0][0]), {"wrist_flex.pos"})

    def test_switches_to_full_nest_once_wrist_arrives(self) -> None:
        start = {key: 0.0 for key in self.NEST}
        start["wrist_flex"] = 40.0
        arrived = {key: 0.0 for key in self.NEST}
        arrived["wrist_flex"] = 50.0
        robot, teleop = self._arms(start)
        robot.get_observation.side_effect = [
            {f"{k}.pos": v for k, v in start.items()},
            {f"{k}.pos": v for k, v in arrived.items()},
            {f"{k}.pos": v for k, v in arrived.items()},
        ]
        teleop.get_action.side_effect = [
            {f"{k}.pos": v for k, v in start.items()},
            {f"{k}.pos": v for k, v in arrived.items()},
            {f"{k}.pos": v for k, v in arrived.items()},
        ]
        events = self._events()
        pauses = {"n": 0}

        def pause(_s: float) -> None:
            pauses["n"] += 1
            if pauses["n"] >= 3:
                events["stop_recording"] = True

        self._run(robot, teleop, events, pause)

        calls = robot.send_action.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(set(calls[0][0][0]), {"wrist_flex.pos"})
        self.assertEqual(set(calls[1][0][0]), {"wrist_flex.pos"})
        self.assertEqual(set(calls[2][0][0]), {f"{k}.pos" for k in self.NEST})

    def test_stuck_wrist_falls_back_to_full_nest(self) -> None:
        stuck = {key: 0.0 for key in self.NEST}
        stuck["wrist_flex"] = 40.0
        robot, teleop = self._arms(stuck)
        events = self._events()
        pauses = {"n": 0}

        def pause(_s: float) -> None:
            pauses["n"] += 1
            if pauses["n"] >= _STUCK_TICKS_BEFORE_ALL + 1:
                events["stop_recording"] = True

        self._run(robot, teleop, events, pause)

        calls = robot.send_action.call_args_list
        self.assertEqual(len(calls), _STUCK_TICKS_BEFORE_ALL + 1)
        wrist_only = {"wrist_flex.pos"}
        self.assertTrue(all(set(call[0][0]) == wrist_only for call in calls[:-1]))
        self.assertEqual(set(calls[-1][0][0]), {f"{k}.pos" for k in self.NEST})

    def test_unknown_first_joint_skips_staging(self) -> None:
        robot, teleop = self._arms({key: 0.0 for key in self.NEST})
        events = self._events()

        def pause(_s: float) -> None:
            events["hold_nest"] = False
            events["stop_recording"] = True

        with patch.dict("os.environ", {"SO101_RECORD_NEST_FIRST_JOINT": "nope"}):
            self._run(robot, teleop, events, pause)

        calls = robot.send_action.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(set(calls[0][0][0]), {f"{k}.pos" for k in self.NEST})

    def test_first_joint_default_and_env_override(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "SO101_RECORD_NEST_FIRST_JOINT"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(nest_first_joint(), "wrist_flex")
        with patch.dict("os.environ", {"SO101_RECORD_NEST_FIRST_JOINT": "elbow_flex"}):
            self.assertEqual(nest_first_joint(), "elbow_flex")

    def test_first_stage_target_picks_one_joint(self) -> None:
        nest = {"wrist_flex": 50.0, "shoulder_pan": 0.0}
        self.assertEqual(first_stage_target(nest, "wrist_flex"), {"wrist_flex": 50.0})
        self.assertEqual(first_stage_target(nest, "missing"), {})


class NestToggleTests(unittest.TestCase):
    def test_nest_toggle_on_ready(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        apply_phone_control("nest", events)
        self.assertTrue(events["hold_nest"])
        apply_phone_control("nest", events)
        self.assertFalse(events["hold_nest"])

    def test_start_sets_start_episode(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        apply_phone_control("start", events)
        self.assertTrue(events["start_episode"])
        self.assertTrue(events["exit_early"])

    def test_board_nest_not_blocked_by_pending(self) -> None:
        events = fresh_events()
        events["phase"] = "ready"
        events["exit_early"] = True
        board = ButtonBoard(events)
        code, payload = board.submit("nest")
        self.assertEqual(code, 200)
        self.assertTrue(payload["hold_nest"])


if __name__ == "__main__":
    unittest.main()
