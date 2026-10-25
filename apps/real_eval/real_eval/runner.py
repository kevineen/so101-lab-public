"""エピソードループと real_eval.csv の書き出し。

CSV 形式は sim2rl ``docs/benchmarks.md`` §実機スコアの記録（1 行 = 1 エピソード）:
``date_utc,checkpoint,seed,episode,success,best_dist_m,final_dist_m,operator,notes``。
"""

from __future__ import annotations

import csv
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .arm import ArmIO, SafetyGuards, Watchdog
from .config import RealEvalConfig
from .kinematics import Kinematics
from .policy import OnnxPolicy

CSV_HEADER = [
    "date_utc",
    "checkpoint",
    "seed",
    "episode",
    "success",
    "best_dist_m",
    "final_dist_m",
    "operator",
    "notes",
]


def read_seed(run_dir: Path) -> int:
    """run の config.yaml から seed を読む（行が無ければ 0）。"""
    import yaml

    config = run_dir / "config.yaml"
    if not config.exists():
        return 0
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    seed = data.get("seed", 0)
    return int(seed) if isinstance(seed, (int, float)) else 0


def run_episode(
    arm: ArmIO,
    kin: Kinematics,
    policy: OnnxPolicy,
    guards: SafetyGuards,
    watchdog: Watchdog,
    cfg: RealEvalConfig,
    goal: np.ndarray,
) -> dict[str, float | bool]:
    """1 エピソード: 観測 → ONNX 推論 → 安全クランプ → 指令。成功判定は EE 距離。"""
    best_dist = float("inf")
    final_dist = float("inf")
    period = 1.0 / cfg.rate_hz

    for _ in range(cfg.steps_per_episode):
        cycle_start = time.monotonic()
        measured = arm.read_joints()
        qpos_urdf = kin.to_urdf_qpos(measured)
        ee = kin.ee_pos(qpos_urdf)
        dist = float(np.linalg.norm(goal - ee))
        best_dist = min(best_dist, dist)

        if not watchdog.stale:
            obs = OnnxPolicy.build_obs(qpos_urdf, ee, goal)
            action = policy.act(obs)
            if watchdog.stale:
                # 推論に時間がかかりすぎて次の指令が間に合わなかった → 廃棄
                target_lerobot = watchdog.hold_target(measured)
            else:
                target_urdf = kin.denormalize(action)
                target_lerobot = kin.to_lerobot_action(target_urdf)
                target_lerobot = guards.clamp_target(measured, target_lerobot)
        else:
            # ウォッチドッグ契約: 発火した瞬間の測定姿勢に目標を固定（沈降防止）
            target_lerobot = watchdog.hold_target(measured)

        arm.write_joints(target_lerobot)
        watchdog.note_write()
        final_dist = dist

        sleep = period - (time.monotonic() - cycle_start)
        if sleep > 0:
            time.sleep(sleep)

    return {
        "success": bool(final_dist <= cfg.success_threshold_m),
        "best_dist_m": best_dist,
        "final_dist_m": final_dist,
    }


def run_eval(
    arm: ArmIO,
    kin: Kinematics,
    policy: OnnxPolicy,
    cfg: RealEvalConfig,
) -> Path:
    """全エピソードを実行し real_eval.csv へ追記する。戻り値は CSV パス。"""
    assert cfg.out_csv is not None and cfg.policy_onnx is not None and cfg.goal_m is not None
    goal = np.array(cfg.goal_m, dtype=np.float64)

    lerobot_limits = [
        kin.to_lerobot_action(kin.lower),
        kin.to_lerobot_action(kin.upper),
    ]  # 負 scale の joint_map では上下が反転するため、min/max で正規化
    guards = SafetyGuards(
        np.minimum(*lerobot_limits), np.maximum(*lerobot_limits), max_step=cfg.max_relative_target
    )
    watchdog = Watchdog(cfg.cmd_timeout_s)
    seed = read_seed(cfg.run_dir)

    csv_path = cfg.out_csv
    is_new = not csv_path.exists()
    rows: list[dict[str, float | bool | str]] = []
    try:
        for episode in range(1, cfg.episodes + 1):
            watchdog.reset()
            result = run_episode(arm, kin, policy, guards, watchdog, cfg, goal)
            row: dict[str, float | bool | str] = {
                "date_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "checkpoint": cfg.checkpoint,
                "seed": seed,
                "episode": episode,
                "success": result["success"],
                "best_dist_m": round(float(result["best_dist_m"]), 4),
                "final_dist_m": round(float(result["final_dist_m"]), 4),
                "operator": cfg.operator,
                "notes": cfg.notes,
            }
            rows.append(row)
            print(
                f"[real_eval] episode {episode}/{cfg.episodes}: "
                f"success={row['success']} best={row['best_dist_m']}m final={row['final_dist_m']}m"
            )
    finally:
        arm.close()

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    return csv_path
