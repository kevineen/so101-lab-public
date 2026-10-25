"""Nest file helpers + dry-run go_home control message."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from bridges.isaacteleop_to_so101.arms import DualArmConfig, PhysicalArm
from bridges.isaacteleop_to_so101.ik import ApproxIk
from bridges.isaacteleop_to_so101.nest import has_home_flags, joints_for_arm
from bridges.isaacteleop_to_so101.receiver import BridgeReceiver


class NestFileTests(unittest.TestCase):
    def test_missing_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            joints, from_file = joints_for_arm("follower", path=path)
            self.assertFalse(from_file)
            self.assertAlmostEqual(joints["gripper"], 50.0)

    def test_load_one_arm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "home.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "arms": {
                            "follower": {
                                "shoulder_pan": 10.0,
                                "shoulder_lift": 20.0,
                                "elbow_flex": 30.0,
                                "wrist_flex": 0.0,
                                "wrist_roll": 0.0,
                                "gripper": 40.0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            j, ok = joints_for_arm("follower", path=path)
            self.assertTrue(ok)
            self.assertAlmostEqual(j["shoulder_lift"], 20.0)
            flags = has_home_flags(path=path, arm_names=["follower", "leader"])
            self.assertTrue(flags["follower"])
            self.assertFalse(flags["leader"])


class GoHomeDryRunTests(unittest.TestCase):
    def test_go_home_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "home.json"
            path.write_text(
                json.dumps(
                    {
                        "arms": {
                            "follower": {
                                "shoulder_pan": 5.0,
                                "shoulder_lift": 15.0,
                                "elbow_flex": 25.0,
                                "wrist_flex": 0.0,
                                "wrist_roll": 0.0,
                                "gripper": 55.0,
                            },
                            "leader": {
                                "shoulder_pan": -5.0,
                                "shoulder_lift": 15.0,
                                "elbow_flex": 25.0,
                                "wrist_flex": 0.0,
                                "wrist_roll": 0.0,
                                "gripper": 55.0,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg = DualArmConfig(
                arms={
                    "follower": PhysicalArm("follower", "/dev/null", "f"),
                    "leader": PhysicalArm("leader", "/dev/null", "l"),
                }
            )
            rx = BridgeReceiver(cfg, ApproxIk(), dry_run=True, home_path=path)
            ack = rx.go_home("both")
            self.assertTrue(ack["ok"])
            self.assertTrue(ack["arms"]["follower"]["reached"])
            self.assertEqual(ack["arms"]["follower"]["source"], "file")
            self.assertAlmostEqual(rx.runtimes["follower"].snapshot()["shoulder_lift"], 15.0)

    def test_ws_go_home_message(self) -> None:
        async def _run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "home.json"
                path.write_text('{"arms":{}}', encoding="utf-8")
                cfg = DualArmConfig(
                    arms={"follower": PhysicalArm("follower", "/dev/null", "f")}
                )
                rx = BridgeReceiver(cfg, ApproxIk(), dry_run=True, home_path=path)

                class FakeWs:
                    def __init__(self) -> None:
                        self.sent: list[str] = []
                        self._msgs = [
                            json.dumps({"type": "go_home", "arm": "follower"}),
                        ]
                        self._i = 0
                        self.remote_address = ("127.0.0.1", 1)
                        self.request = type("R", (), {"path": "/teleop"})()

                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        if self._i >= len(self._msgs):
                            raise StopAsyncIteration
                        m = self._msgs[self._i]
                        self._i += 1
                        return m

                    async def send(self, data: str) -> None:
                        self.sent.append(data)

                    async def close(self, **_kwargs):
                        return None

                ws = FakeWs()
                await rx._ws_handler(ws)
                # hello + go_home_ack + go_home result
                self.assertGreaterEqual(len(ws.sent), 3)
                hello = json.loads(ws.sent[0])
                self.assertEqual(hello.get("type"), "hello")
                self.assertTrue(hello.get("supports_go_home"))
                mid = json.loads(ws.sent[1])
                self.assertEqual(mid.get("type"), "go_home_ack")
                ack = json.loads(ws.sent[2])
                self.assertEqual(ack.get("type"), "go_home")
                self.assertTrue(ack.get("ok"))

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
