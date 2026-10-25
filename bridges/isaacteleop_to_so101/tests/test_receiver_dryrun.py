"""Dry-run receiver accepts left + right joint frames over WebSocket."""

from __future__ import annotations

import asyncio
import unittest

from bridges.isaacteleop_to_so101.arms import DualArmConfig, PhysicalArm
from bridges.isaacteleop_to_so101.ik import ApproxIk
from bridges.isaacteleop_to_so101.receiver import BridgeReceiver
from bridges.isaacteleop_to_so101.sender import make_joint_cmd, send_stream


class DryRunBimanualTests(unittest.IsolatedAsyncioTestCase):
    async def test_left_right_joint_stream(self) -> None:
        config = DualArmConfig(
            arms={
                "follower": PhysicalArm("follower", "/dev/null", "my_follower"),
                "leader": PhysicalArm("leader", "/dev/null", "my_leader_drive"),
            }
        )
        receiver = BridgeReceiver(
            config,
            ApproxIk(),
            host="127.0.0.1",
            port=18870,
            control_hz=20.0,
            cmd_timeout_s=1.0,
            dry_run=True,
        )
        stop = asyncio.Event()

        async def _serve() -> None:
            import websockets

            receiver.connect_robots()
            receiver.start_control()
            async with websockets.serve(receiver._ws_handler, "127.0.0.1", 18870):
                await stop.wait()

        server_task = asyncio.create_task(_serve())
        await asyncio.sleep(0.2)

        cmds = [
            make_joint_cmd(
                "left",
                {
                    "shoulder_pan": 5.0,
                    "shoulder_lift": 0.0,
                    "elbow_flex": 0.0,
                    "wrist_flex": 0.0,
                    "wrist_roll": 0.0,
                    "gripper": 10.0,
                },
            ),
            make_joint_cmd(
                "right",
                {
                    "shoulder_pan": -5.0,
                    "shoulder_lift": 0.0,
                    "elbow_flex": 0.0,
                    "wrist_flex": 0.0,
                    "wrist_roll": 0.0,
                    "gripper": 10.0,
                },
            ),
        ]
        # Seed measured pose so absolute joint cmds are near current (no yank).
        receiver.runtimes["follower"].targets["shoulder_pan"] = 0.0
        receiver.runtimes["leader"].targets["shoulder_pan"] = 0.0
        await send_stream("127.0.0.1", 18870, "/teleop", cmds, hz=30.0)

        self.assertAlmostEqual(receiver.runtimes["follower"].snapshot()["shoulder_pan"], 5.0)
        self.assertAlmostEqual(receiver.runtimes["leader"].snapshot()["shoulder_pan"], -5.0)

        receiver.stop_control()
        stop.set()
        await server_task