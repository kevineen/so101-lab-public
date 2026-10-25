#!/usr/bin/env python3
"""SO-101 を Newton Kamino ソルバ（GPU・Proximal-ADMM）で動かすスモークチェック（ヘッドレス）.

- シーン: assets/robots/so101/sim/so101_scene.xml（12_mujoco_sim と共用）
  位置サーボの kp=998.22 / kv=2.731 は add_mjcf が joint_target_ke/kd として自動取り込み。
- 実機・USB・カメラは一切使わない。MuJoCo 版 sim_check.py が運動学チェックなのに対し、
  こちらは GPU 上で動力学（重力・接触・PD サーボ）を積分する。
- CUDA グラフキャプチャ有効時は ~100 steps/s（RTX 4090・worlds=1）。

使い方（uv・sim グループ）:
  uv run --group sim python scripts/kamino_check.py                 # ホーム姿勢保持（重力たわみチェック）
  ... scripts/kamino_check.py --sweep                               # 全関節を正弦掃引
  ... scripts/kamino_check.py --pose "0,-40,-20,-40,0,20"           # 特定姿勢の保持（deg）
  ... scripts/kamino_check.py --worlds 8 --steps 2000               # 8 世界並列で GPU バッチの効きを見る
  ... scripts/kamino_check.py --no-collide                          # 衝突なし（高速）

関節順（deg 指定）: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
exit code: 0=正常 / 2=エラー
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENE = ROOT / "assets/robots/so101/sim/so101_scene.xml"
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    p.add_argument("--steps", type=int, default=400, help="積分ステップ数 (default: 400)")
    p.add_argument("--dt", type=float, default=0.005, help="刻み幅 [s] (default: 0.005 = MJCF と同一)")
    p.add_argument("--worlds", type=int, default=1, help="並列世界数（Kamino は世界バッチで GPU を活かす）")
    p.add_argument("--pose", type=str, default=None, help="保持目標姿勢（deg・カンマ区切り・ホームはゼロ）")
    p.add_argument("--sweep", action="store_true", help="全関節を正弦掃引（--pose と併用不可）")
    p.add_argument("--sweep-amp", type=float, default=20.0, help="掃引振幅 [deg] (default: 20)")
    p.add_argument("--no-collide", action="store_true", help="衝突計算を無効化（高速・机に沈む）")
    p.add_argument("--self-collide", dest="no_self_collide_filter", action="store_false",
                   help="自己衝突を有効化（隣接リンクも接触するので遅い・参考用）")
    p.add_argument("--device", type=str, default=None, help="warp デバイス（例: cpu / cuda:0。既定は自動）")
    p.add_argument("--tol-deg", type=float, default=5.0, help="保持姿勢との最大偏差しきい値 [deg]")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.pose and args.sweep:
        print("error: --pose と --sweep は併用できません", file=sys.stderr)
        return 2

    import warp as wp

    if args.device:
        wp.set_device(args.device)
    wp.init()

    import numpy as np

    import newton
    from newton.solvers import SolverKamino

    target_deg = np.zeros(len(JOINTS))
    if args.pose:
        vals = [float(v) for v in args.pose.split(",")]
        if len(vals) != len(JOINTS):
            print(f"error: --pose は {len(JOINTS)} 個（{', '.join(JOINTS)}）", file=sys.stderr)
            return 2
        target_deg = np.array(vals)

    # --- モデル構築: Kamino カスタム属性を登録してから MJCF を取り込む ---
    # enable_self_collisions=False: 現行 add_mjcf は MuJoCo の親子ジオム除外・contype フィルタを
    # 再現しないため、既定のままだと隣接リンクの衝突 box が常時接触して遅くなる（arm↔机・床の接触は残る）。
    robot = newton.ModelBuilder(up_axis=newton.Axis.Z)
    SolverKamino.register_custom_attributes(robot)
    robot.add_mjcf(str(args.scene), parse_visuals=False, enable_self_collisions=not args.no_self_collide_filter)
    builder = newton.ModelBuilder(up_axis=newton.Axis.Z)
    for _ in range(args.worlds):
        builder.add_world(robot)
    model = builder.finalize(skip_validation_joints=True)

    # --- ソルバ設定: メッシュ衝突 (gripper STL) があるため unified パイプライン ---
    cfg = SolverKamino.Config.from_model(model)
    cfg.use_collision_detector = not args.no_collide
    cfg.use_fk_solver = True
    if cfg.use_collision_detector:
        cfg.collision_detector.pipeline = "unified"  # primitive は box/sphere 以外で ValueError
        # SO-101 はグリッパ微小 geom 多数で推定容量を超えるため明示指定（超えると警告+接触欠落）
        cfg.collision_detector.max_contacts_per_world = 512
    solver = SolverKamino(model=model, config=cfg)

    state0, state1 = model.state(), model.state()
    control = model.control()
    contacts = newton.CollisionPipeline(model).contacts() if cfg.use_collision_detector else None

    targets = np.tile(np.radians(target_deg), args.worlds).astype(np.float32)
    control.joint_target_q.assign(targets)

    # --- CUDA グラフキャプチャ（小規模モデルはカーネルlaunch律速なので効果大）---
    def step(s0, s1):
        solver.step(s0, s1, control, contacts, args.dt)

    for _ in range(3):  # ウォームアップ（JIT コンパイル）
        step(state0, state1)
        state0, state1 = state1, state0

    graph = None
    if wp.get_device().is_cuda and not wp.config.verify_cuda:
        try:
            with wp.ScopedCapture() as cap:
                step(state0, state1)
            graph = cap.graph
        except Exception as e:  # キャプチャ失敗は非グラフ実行へフォールバック
            print(f"(graph capture 失敗、通常実行: {e})")

    # --- 積分ループ ---
    t0 = time.time()
    for i in range(args.steps):
        if args.sweep:
            phase = i * args.dt * 0.5  # 0.5 Hz
            targets = np.tile(
                np.radians(target_deg + args.sweep_amp * np.sin(2 * np.pi * phase)), args.worlds
            ).astype(np.float32)
            control.joint_target_q.assign(targets)  # デバイス配列の中身更新 → グラフでも反映
        if graph is not None:
            wp.capture_launch(graph)
        else:
            step(state0, state1)
        state0, state1 = state1, state0
    wp.synchronize()
    elapsed = time.time() - t0

    # --- 結果表示 ---
    q = np.degrees(state0.joint_q.numpy())[: len(JOINTS)]
    dev = np.abs(q - target_deg)
    print(f"device: {wp.get_device()} / worlds: {args.worlds} / dt: {args.dt}s")
    print(f"steps: {args.steps} in {elapsed:.2f}s = {args.steps / elapsed:.0f} steps/s "
          f"({args.steps * args.dt:.1f}s 相当を再生)")
    for name, qi, di in zip(JOINTS, q, dev):
        print(f"  {name:<14} {qi:+8.2f} deg (目標偏差 {di:.2f} deg)")
    if not args.sweep:
        worst = dev.max()
        status = "OK" if worst < args.tol_deg else "NG: 姿勢が目標から大きく逸脱"
        print(f"最大偏差 {worst:.2f} deg (しきい値 {args.tol_deg} deg) → {status}")
        if worst >= args.tol_deg:
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        raise
