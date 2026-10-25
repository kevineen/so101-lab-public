"""Router, center-camera watch, and text-Jev parsing without hardware."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_remote.center_watch import CenterWatch  # noqa: E402
from web_remote.jev_router import JevRouter, interpret_answers  # noqa: E402
from web_remote.rate_router import (  # noqa: E402
    CONFIRM_FRAMES,
    DWELL_S,
    RateRouter,
    classify_command,
    targets_near_edge,
)
from web_remote.scene_state import SceneState  # noqa: E402
from web_remote.server import QuietPollAccessFilter  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _router() -> tuple[Clock, RateRouter]:
    clock = Clock()
    router = RateRouter(clock=clock, jev=JevRouter(api_key=""))
    clock.t = DWELL_S
    return clock, router


def _push(router: RateRouter, scene: SceneState, *, command: str, joint_edge: bool = False) -> None:
    for _ in range(CONFIRM_FRAMES):
        router.update(scene, command_motion=command, joint_near_edge=joint_edge)


class RateRouterTests(unittest.TestCase):
    def test_near_object_selects_approach_after_confirm(self) -> None:
        _clock, router = _router()
        scene = SceneState(proximity="near_object", workspace="inside", motion="moving")
        router.update(scene, command_motion="fast", joint_near_edge=False)
        self.assertEqual(router.mode, "cruise")
        _push(router, scene, command="fast")
        self.assertEqual(router.mode, "approach")
        snap = router.snapshot()
        self.assertEqual(snap["control_hz"], 20.0)
        self.assertEqual(snap["step_limit"], 12.0)
        self.assertEqual(snap["reason"], "near_object")

    def test_clear_fast_command_selects_cruise(self) -> None:
        clock, router = _router()
        near = SceneState(proximity="near_object", workspace="inside")
        _push(router, near, command="still")
        self.assertEqual(router.mode, "approach")
        clock.t = DWELL_S * 2
        clear = SceneState(proximity="clear", workspace="inside", motion="fast")
        _push(router, clear, command="fast")
        self.assertEqual(router.mode, "cruise")
        self.assertEqual(router.snapshot()["control_hz"], 40.0)
        self.assertEqual(router.snapshot()["step_limit"], 30.0)

    def test_unknown_does_not_force_approach(self) -> None:
        _clock, router = _router()
        scene = SceneState(proximity="unknown", workspace="unknown", motion="fast")
        _push(router, scene, command="fast")
        self.assertEqual(router.mode, "cruise")
        self.assertEqual(router.snapshot()["reason"], "hold")

    def test_workspace_edge_and_joint_edge_approach(self) -> None:
        _clock, router = _router()
        edge = SceneState(proximity="clear", workspace="near_edge")
        _push(router, edge, command="fast")
        self.assertEqual(router.mode, "approach")
        self.assertEqual(router.reason, "near_edge")

        clock, router = _router()
        clear = SceneState(proximity="clear", workspace="inside")
        _push(router, clear, command="fast", joint_edge=True)
        self.assertEqual(router.mode, "approach")
        self.assertEqual(router.reason, "joint_edge")
        clock.t = DWELL_S * 2

    def test_gray_zone_asks_jev_once_per_interval(self) -> None:
        clock = Clock()

        class CountingJev(JevRouter):
            def __init__(self) -> None:
                super().__init__(api_key="present")
                self.calls: list[str] = []

            def choose_mode(self, scene: SceneState, *, command_motion: str, joint_near_edge: bool):
                self.calls.append(command_motion)
                return "approach", "jev"

        jev = CountingJev()
        router = RateRouter(clock=clock, jev=jev)
        clock.t = DWELL_S
        gray = SceneState(proximity="unknown", workspace="inside", motion="moving", summary="unsure")
        _push(router, gray, command="moving")
        self.assertEqual(router.mode, "approach")
        self.assertEqual(router.reason, "jev")
        self.assertEqual(jev.calls, ["moving"])
        clock.t = DWELL_S + 0.2
        router.update(gray, command_motion="moving", joint_near_edge=False)
        self.assertEqual(jev.calls, ["moving"])

    def test_command_and_joint_edges(self) -> None:
        self.assertEqual(classify_command(10.0, 0.2), "fast")
        self.assertEqual(classify_command(3.0, 0.2), "moving")
        self.assertEqual(classify_command(0.4, 0.2), "still")
        home = {"follower": {name: 0.0 for name in ("shoulder_pan", "gripper", "wrist_roll")}}
        self.assertFalse(targets_near_edge(home))
        parked = {"follower": {"shoulder_pan": 90.0, "gripper": 0.0}}
        self.assertTrue(targets_near_edge(parked))


class CenterWatchTests(unittest.TestCase):
    def test_missing_frame_stays_unknown(self) -> None:
        state = CenterWatch().observe(None, command_motion="fast")
        self.assertEqual(state.motion, "fast")
        self.assertEqual(state.proximity, "unknown")
        self.assertEqual(state.workspace, "unknown")
        self.assertEqual(state.source, "center_cv")

    def test_motion_in_open_center_is_clear(self) -> None:
        watch = CenterWatch()
        height, width = 120, 160
        base = np.full((height, width), 128, np.uint8)
        watch.observe(base, command_motion="still")
        moved = base.copy()
        moved[50:70, 70:90] = 255
        state = watch.observe(moved, command_motion="still")
        self.assertIn(state.motion, {"moving", "fast"})
        self.assertEqual(state.workspace, "inside")
        self.assertEqual(state.proximity, "clear")

    def test_static_object_near_arm_and_frame_edge(self) -> None:
        watch = CenterWatch()
        height, width = 120, 160
        base = np.full((height, width), 128, np.uint8)
        # High-contrast block that stays put, beside where the arm will move.
        base[48:64, 108:124] = 0
        base[48:56, 108:116] = 255
        watch.observe(base, command_motion="still")
        moved = base.copy()
        moved[50:70, 70:90] = 255
        state = watch.observe(moved, command_motion="still")
        self.assertEqual(state.proximity, "near_object")
        self.assertEqual(state.workspace, "inside")

        edge = CenterWatch()
        blank = np.full((height, width), 128, np.uint8)
        edge.observe(blank, command_motion="still")
        corner = blank.copy()
        corner[0:24, 0:24] = 255
        state = edge.observe(corner, command_motion="still")
        self.assertEqual(state.workspace, "near_edge")

    def test_image_jev_source_uses_the_same_fields(self) -> None:
        later = SceneState(
            motion="moving",
            proximity="near_object",
            workspace="inside",
            source="image_jev",
            summary="image model later",
        )
        self.assertEqual(later.to_dict()["source"], "image_jev")
        self.assertEqual(set(later.to_dict()), {"motion", "proximity", "workspace", "source", "summary", "updated_at"})


class JevRouterTests(unittest.TestCase):
    def test_interpret_thresholds(self) -> None:
        low = {"answers": {"mode": {"choice": "approach", "confidence": 0.2}, "near_object": {"noul": 0.1}}}
        self.assertIsNone(interpret_answers(low))
        forced = {"answers": {"mode": {"choice": "cruise", "confidence": 0.95}, "near_object": {"noul": 0.8}}}
        self.assertEqual(interpret_answers(forced), ("approach", "jev_near"))
        cruise = {"answers": {"mode": {"choice": "cruise", "confidence": 0.91}, "near_object": {"noul": 0.1}}}
        self.assertEqual(interpret_answers(cruise), ("cruise", "jev"))

    def test_disabled_without_key(self) -> None:
        client = JevRouter(api_key="")
        self.assertFalse(client.enabled)
        scene = SceneState(summary="quiet")
        self.assertIsNone(client.choose_mode(scene, command_motion="moving", joint_near_edge=False))

    def test_poster_sends_scene_and_not_pixels(self) -> None:
        seen: dict[str, object] = {}

        def poster(payload: dict[str, object]) -> dict[str, object]:
            seen.update(payload)
            return {"answers": {"mode": {"choice": "cruise", "confidence": 0.9}, "near_object": {"noul": 0.05}}}

        client = JevRouter(api_key="test-key", poster=poster)
        scene = SceneState(proximity="unknown", workspace="inside", summary="Center camera: unsure.")
        mode = client.choose_mode(scene, command_motion="moving", joint_near_edge=False)
        self.assertEqual(mode, ("cruise", "jev"))
        self.assertEqual(seen["model"], "jev-1.13.0")
        state = seen["state"]
        self.assertIsInstance(state, dict)
        assert isinstance(state, dict)
        self.assertNotIn("image", state)
        perception = state["perception"]
        assert isinstance(perception, dict)
        self.assertEqual(perception["summary"], scene.summary)
        questions = seen["questions"]
        assert isinstance(questions, dict)
        self.assertEqual(questions["mode"]["type"], "choice")
        self.assertEqual(questions["near_object"]["type"], "noul")


class AccessLogTests(unittest.TestCase):
    def _record(self, method: str, path: str, status: int) -> logging.LogRecord:
        return logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("192.168.77.40:1", method, path, "1.1", status),
            exc_info=None,
        )

    def test_state_200_is_logged_only_when_status_changes(self) -> None:
        filt = QuietPollAccessFilter()
        self.assertTrue(filt.filter(self._record("GET", "/api/state", 200)))
        self.assertFalse(filt.filter(self._record("GET", "/api/state", 200)))
        self.assertTrue(filt.filter(self._record("GET", "/api/state", 503)))
        self.assertTrue(filt.filter(self._record("GET", "/api/state", 200)))
        self.assertFalse(filt.filter(self._record("GET", "/api/state?arm=follower", 200)))

    def test_other_requests_always_log(self) -> None:
        filt = QuietPollAccessFilter()
        self.assertTrue(filt.filter(self._record("POST", "/api/teleop", 200)))
        self.assertTrue(filt.filter(self._record("POST", "/api/teleop", 200)))
        self.assertTrue(filt.filter(self._record("GET", "/api/info", 200)))


if __name__ == "__main__":
    unittest.main()
