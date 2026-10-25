#!/usr/bin/env python
"""AmazingHand 実機ベンチテスト用の最小制御ツール。

lerobot フォークの ``amazing_hand`` ロボットクラス（SCS0009×8, protocol 1,
専用バス）を使い、(1) 配線・ID確認 (2) サボ単体のふるまい確認 (3) 基本pose、
を対話的に確認する。**ベンチ固定（アーム未搭載）での単体確認が前提**。

前提:
- Waveshare USB アダプタ経由の専用バス（STS3215 アームバスとは絶対に混線しない）
- 電源 5V/2A 以上（公式仕様）
- PYTHONPATH=~/robot/lerobot/src（lerobot フォーク）
- キャリブレーション未実施でも probe は動く（正規化は 0-100 生値）

使い方:
    PYTHONPATH=~/robot/lerobot/src uv run --project ~/robot/lerobot --extra feetech \
        python apps/amazing_hand/amazing_hand_ctl.py --port /dev/ttyUSB0 probe
    ... wiggle --motor finger1_motor1
    ... pose --mode close

sim2rl モデル空間との対応（calibration.json）:
    spread[rad] = 0.260*(m1+m2),  flex[rad] = 0.353*m1 - 0.326*m2  （m*=rad）
指index と実指（index/middle/ring/thumb）の対応は wiggle で点灯確認してから
使うこと（config_amazing_hand.py の注記参照）。
"""

from __future__ import annotations

import argparse
import sys
import time


def build_robot(port: str, side: str):
    from lerobot.robots.amazing_hand import AmazingHandConfig
    from lerobot.robots.utils import make_robot_from_config

    cfg = AmazingHandConfig(port=port, side=side, read_present_load=True)
    return make_robot_from_config(cfg)


def cmd_probe(robot, args) -> None:
    """位置と負荷を読み続ける（トルクOFFのまま）。配線・グラビティ応答確認。"""
    robot.bus.connect()
    try:
        robot.bus.disable_torque()  # 安全のため非励磁
        print("reading Present_Position / Present_Load (Ctrl-C to stop)")
        while True:
            row = []
            for motor in robot.bus.motors:
                pos = robot.bus.read("Present_Position", motor, num_retry=args.retries)
                load = robot.bus.read("Present_Load", motor, num_retry=args.retries)
                row.append(f"{motor.split('_')[0]}:{pos:+7.1f}/{load:+5d}")
            print("  ".join(row), end="\r", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()
    finally:
        robot.bus.disconnect()


def cmd_wiggle(robot, args) -> None:
    """1サーボを正弦駆動（振幅既定±30°相当の正規化0-100）。ID・向き確認用。"""
    motor = args.motor
    if motor not in robot.bus.motors:
        sys.exit(f"unknown motor {motor}; choose from {list(robot.bus.motors)}")
    robot.connect(calibrate=False)
    try:
        t0 = time.time()
        print(f"wiggling {motor} (Ctrl-C to stop)")
        while True:
            t = time.time() - t0
            norm = 50.0 + 30.0 * (2.0 * (t % 2.0) - 1.0) * 0.5  # ±30 in 0-100
            robot.bus.sync_write("Goal_Position", {motor: norm})
            time.sleep(0.02)
    except KeyboardInterrupt:
        print()
    finally:
        robot.disconnect()


#: 基本pose（正規化0-100）。公式デモのMiddlePosパターンを踏襨 —
#: 実機のキャリブレーション結果に合わせて調整すること。
POSES = {
    "open": {"m1": 35.0, "m2": 35.0},   # 逆相: 指を伸ばす
    "close": {"m1": 90.0, "m2": -90.0},  # 同相: 閉じる（数値は要調整）
    "spread": {"m1": 80.0, "m2": 80.0},  # 同相: 開く
}


def cmd_pose(robot, args) -> None:
    vals = POSES[args.mode]
    goal = {f"finger{i}_motor{k}": v for i in range(1, 5) for k, v in ((1, vals["m1"]), (2, vals["m2"]))}
    robot.connect(calibrate=False)
    try:
        print(f"pose={args.mode} goal={goal} for {args.hold}s")
        robot.bus.sync_write("Goal_Position", goal)
        time.sleep(args.hold)
    finally:
        robot.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="Waveshare USB serial port (e.g. /dev/ttyUSB0)")
    ap.add_argument("--side", default="right", choices=["left", "right"])
    ap.add_argument("--retries", type=int, default=2)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="read positions/loads forever (torque off)")
    w = sub.add_parser("wiggle", help="sine-drive one motor")
    w.add_argument("--motor", required=True)
    p = sub.add_parser("pose", help="basic hand pose")
    p.add_argument("--mode", required=True, choices=list(POSES))
    p.add_argument("--hold", type=float, default=3.0)
    args = ap.parse_args()

    robot = build_robot(args.port, args.side)
    {"probe": cmd_probe, "wiggle": cmd_wiggle, "pose": cmd_pose}[args.cmd](robot, args)


if __name__ == "__main__":
    main()
