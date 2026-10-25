"""CLI: ``python -m real_eval --config configs/real_eval.yaml``。

3 つのモード:

- （既定）``run``: real_eval.csv に評価エピソードを追記
- ``--probe``: 現在姿勢の qpos（URDF rad）と EE 位置を表示し続ける
  （goal 計測・座標確認用。指令は出さない）
- ``--calibrate-offsets``: アームを sim2rl の home 姿勢に手で保持した状態で
  LeRobot 読み値を取り、零点オフセットを yaml として標準出力へ出す
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import yaml

from .arm import LerobotArm
from .config import JOINT_ORDER, RealEvalConfig
from .kinematics import Kinematics
from .policy import OnnxPolicy
from .runner import run_eval


def _load_all(config_path: Path) -> tuple[RealEvalConfig, Kinematics]:
    cfg = RealEvalConfig.from_yaml(config_path)
    urdf = cfg.sim2rl_root / "assets" / "robots" / "so101" / "so101.urdf"
    if not urdf.exists():
        raise FileNotFoundError(f"sim2rl URDF not found: {urdf} (sim2rl_root correct?)")
    kin = Kinematics(urdf, cfg.joint_map)
    return cfg, kin


def _probe(cfg: RealEvalConfig, kin: Kinematics) -> None:
    arm = LerobotArm(cfg.port, cfg.robot_id, cfg.max_relative_target)
    try:
        while True:
            measured = arm.read_joints()
            qpos = kin.to_urdf_qpos(measured)
            ee = kin.ee_pos(qpos)
            print(
                "qpos(rad)=" + np.array2string(qpos, precision=3, floatmode="fixed"),
                "ee(m)=" + np.array2string(ee, precision=4, floatmode="fixed"),
                end="\r",
                flush=True,
            )
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()
    finally:
        arm.close()


def _calibrate_offsets(cfg: RealEvalConfig, kin: Kinematics) -> None:
    """sim2rl home 姿勢での実測 → 各関節の offset を出力。

    urdf_rad = scale * lerobot + offset より、home 姿勢に保持した実測 d に対して
    offset = home_rad - scale * d。scale は既定（度→rad、gripper は既写像）。
    """
    import yaml as _yaml

    robot_yaml = cfg.sim2rl_root / "configs" / "robot" / "so101.yaml"
    home = _yaml.safe_load(robot_yaml.read_text(encoding="utf-8"))["home_position"]
    home_rad = np.array([float(home[j]) for j in JOINT_ORDER])

    arm = LerobotArm(cfg.port, cfg.robot_id, cfg.max_relative_target)
    try:
        input(
            "アームを sim2rl の home 姿勢（configs/robot/so101.yaml 参照）に\n"
            "手で保持して Enter を押してください: "
        )
        measured = arm.read_joints()
    finally:
        arm.close()

    joint_map: dict[str, dict[str, float]] = {}
    for joint, jmap in kin.joint_map.items():
        idx = JOINT_ORDER.index(joint)
        joint_map[joint] = {
            "scale": jmap.scale,
            "offset": float(home_rad[idx] - jmap.scale * measured[idx]),
        }
    print("# real_eval joint_map — この内容を設定 yaml の joint_map: へ貼る")
    print(yaml.safe_dump({"joint_map": joint_map}, sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="real_eval")
    parser.add_argument("--config", type=str, required=True, help="real_eval yaml path")
    parser.add_argument("--probe", action="store_true", help="read-only FK monitor (no commands)")
    parser.add_argument(
        "--calibrate-offsets", action="store_true", help="measure joint_map offsets at sim2rl home"
    )
    parser.add_argument("--goal", type=str, default=None, help="override goal_m, e.g. 0.25,-0.1,0.15")
    parser.add_argument("--episodes", type=int, default=None, help="override episodes")
    args = parser.parse_args(argv)

    cfg, kin = _load_all(Path(args.config))
    if args.goal:
        cfg.goal_m = tuple(float(v) for v in args.goal.split(","))
        cfg.resolve()
    if args.episodes:
        cfg.episodes = args.episodes

    if args.probe:
        _probe(cfg, kin)
        return 0
    if args.calibrate_offsets:
        _calibrate_offsets(cfg, kin)
        return 0

    import onnxruntime as ort

    assert cfg.policy_onnx is not None
    session = ort.InferenceSession(str(cfg.policy_onnx), providers=["CPUExecutionProvider"])
    policy = OnnxPolicy(session)
    csv_path = run_eval(LerobotArm(cfg.port, cfg.robot_id, cfg.max_relative_target), kin, policy, cfg)
    print(f"[real_eval] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
