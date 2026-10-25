#!/usr/bin/env python3
"""SO-101 MuJoCo シーンの可動域・干渉チェック（ヘッドレス動作・実機不要）.

- シーン: assets/robots/so101/sim/so101_scene.xml
- キャリブレーション: lerobot の so_follower キャリブ JSON（homing 2048 tick = ゼロ姿勢）
  から単機の実効可動域を計算し、stock（設計値）との共通範囲を model.jnt_range へ
  実行時適用する（XML は書き換えない）。
  tick→rad: (ticks - 2048) * 2π / 4095
  ※ lerobot 側 use_degrees=True の正規化（zero=range 中央）とは
    offset = (mid - 2048) * 360/4095 deg ずれる。--soft-limits で確認できる。

使い方:
  ~/robot/lerobot/.venv/bin/python scripts/sim_check.py               # 関節スクイープ干渉チェック
  ... scripts/sim_check.py --pose "0,-30,0,0,0,30"                    # 特定姿勢（deg）
  ... scripts/sim_check.py --no-calib                                 # 設計値レンジで実行
  # オフスクリーン描画（要 GL: sudo apt install libegl1 libgl1-mesa-dri の上で）:
  MUJOCO_GL=egl ~/robot/lerobot/.venv/bin/python scripts/sim_check.py --render /tmp/sim

exit code: 0=干渉なし / 1=干渉あり / 2=エラー
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENE = ROOT / "assets/robots/so101/sim/so101_scene.xml"
DEFAULT_CALIB_DIR = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so_follower"
DEFAULT_CALIB = "my_follower"
TICKS_PER_TURN = 4095.0
HOME_TICKS = 2048.0
ENV_GEOMS = {"table", "floor", "obstacle_box"}

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


def ticks_to_rad(ticks: float) -> float:
    return (ticks - HOME_TICKS) * 2.0 * math.pi / TICKS_PER_TURN


def load_calib_ranges(calib_path: Path) -> dict[str, tuple[float, float]]:
    """キャリブ JSON から関節ごとの実効レンジ（rad, ゼロ姿勢基準）を返す."""
    data = json.loads(calib_path.read_text())
    return {name: (ticks_to_rad(c["range_min"]), ticks_to_rad(c["range_max"])) for name, c in data.items()}


def apply_calibrated_ranges(model: mujoco.MjModel, calib: dict[str, tuple[float, float]]) -> list[str]:
    """実効レンジ ∩ 設計レンジ を関節とアクチュエータへ適用。適用結果のメモを返す."""
    notes = []
    for name in JOINTS:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if jid < 0 or name not in calib:
            notes.append(f"{name:13s}: キャリブなし → 設計値のまま")
            continue
        lo_d, hi_d = model.jnt_range[jid]
        lo_c, hi_c = calib[name]
        lo, hi = max(lo_d, lo_c), min(hi_d, hi_c)
        if hi - lo < 0.02:  # 交差なし（キャリブ不良・フレーム不一致）→ 設計値で続行
            notes.append(f"{name:13s}: キャリブ範囲 [{lo_c:+.3f},{hi_c:+.3f}] が設計値と交差せず "
                         f"→ 設計値のまま（要再キャリブ?)")
            continue
        if (hi - lo) < 0.3 * (hi_d - lo_d):
            # 重なりが設計値の 3 割未満 = キャリブの中央がホームから大きくズレている
            # （グリッパー等で起きる）。そのまま適用すると可動域が消えるので設計値を維持
            notes.append(f"{name:13s}: キャリブ [{math.degrees(lo_c):+.0f},{math.degrees(hi_c):+.0f}] deg が"
                         f"設計値 [{math.degrees(lo_d):+.0f},{math.degrees(hi_d):+.0f}] とほぼ重ならず"
                         f" → 設計値のまま（キャリブ再取得を推奨）")
            continue
        model.jnt_range[jid] = [lo, hi]
        if aid >= 0:
            model.actuator_ctrlrange[aid] = [lo, hi]
        clipped = (lo != lo_d) or (hi != hi_d)
        tag = "（設計値でクリップ）" if clipped else ""
        notes.append(f"{name:13s}: {math.degrees(lo):+7.1f} .. {math.degrees(hi):+7.1f} deg {tag}")
    return notes


def geom_pair(data: mujoco.MjData, i: int) -> tuple[str, str]:
    c = data.contact[i]
    m = data.model
    g1 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1)
    g2 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2)
    return g1 or f"geom{c.geom1}", g2 or f"geom{c.geom2}"


def classify_contact(pair: tuple[str, str]) -> str:
    if pair[0] in ENV_GEOMS or pair[1] in ENV_GEOMS:
        return "environment"
    return "self"


def contacts_at(model: mujoco.MjModel, data: mujoco.MjData, qpos: np.ndarray) -> list[tuple[str, str, float]]:
    """qpos を直接設定して衝突判定（動力学は使わない運動学チェック）."""
    data.qpos[:] = qpos
    data.time = 0.0
    mujoco.mj_forward(model, data)
    out = []
    for i in range(data.ncon):
        pair = geom_pair(data, i)
        dist = data.contact[i].dist
        if dist < 0.0:  # actual penetration
            out.append((*pair, dist))
    return out


def render(model, data, cam: str, out: Path, w: int = 1280, h: int = 800) -> bool:
    try:
        renderer = mujoco.Renderer(model, height=h, width=w)
    except Exception as e:  # GL コンテキスト不可（ヘッドレス等）
        print(f"[render] スキップ: {e}")
        print("[render]   ※ オフスクリーン描画は MUJOCO_GL=egl と libegl1/libgl1-mesa-dri が必要")
        return False
    renderer.update_scene(data, camera=cam)
    out.write_bytes(renderer.render())
    renderer.close()
    print(f"[render] {out}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    ap.add_argument("--calib", default=DEFAULT_CALIB, help="so_follower キャリブ ID（--calib-dir 内の JSON 名）")
    ap.add_argument("--calib-dir", type=Path, default=DEFAULT_CALIB_DIR)
    ap.add_argument("--no-calib", action="store_true", help="キャリブを適用せず設計値レンジで実行")
    ap.add_argument("--pose", help='特定姿勢のチェック（deg カンマ区切り, 例 "0,-30,0,0,0,30"）')
    ap.add_argument("--sweep", type=int, default=25, help="関節ごとの掃引サンプル数")
    ap.add_argument("--soft-limits", type=Path, default=ROOT / "configs/quest_teleop.yaml",
                    help="soft_joint_limits_deg を含む YAML（None でスキップは --no-soft-limits）")
    ap.add_argument("--no-soft-limits", action="store_true")
    ap.add_argument("--render", type=Path, help="オフスクリーン描画の出力ディレクトリ")
    args = ap.parse_args()

    if args.render:
        args.render.mkdir(parents=True, exist_ok=True)

    model = mujoco.MjModel.from_xml_path(str(args.scene))
    data = mujoco.MjData(model)

    print(f"scene: {args.scene}")
    print("\n== 関節レンジ（rad → deg） ==")
    if not args.no_calib:
        calib_path = args.calib_dir / f"{args.calib}.json"
        if calib_path.exists():
            print(f"calib: {calib_path}")
            for line in apply_calibrated_ranges(model, load_calib_ranges(calib_path)):
                print(" ", line)
        else:
            print(f"calib: {calib_path} が無い → 設計値レンジで実行")

    def effective_range(name: str) -> tuple[float, float]:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        return tuple(model.jnt_range[jid])

    base = np.zeros(model.nq)
    gripper_mid = sum(effective_range("gripper")) / 2.0
    base[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "gripper")] = gripper_mid
    # 手首は中間、ロールは 0 で固定して掃引
    base[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "wrist_flex")] = sum(effective_range("wrist_flex")) / 2.0

    if args.pose:
        degs = [float(v) for v in args.pose.split(",")]
        if len(degs) != model.nq:
            print(f"ERROR: --pose は {model.nq} 個（{', '.join(JOINTS)}）", file=sys.stderr)
            return 2
        qpos = np.array(degs) * math.pi / 180.0
        hits = contacts_at(model, data, qpos)
        tip = data.site("gripperframe").xpos.copy()
        print("\n== 姿勢チェック ==")
        print(f"  qpos(deg): {', '.join(f'{v:+.1f}' for v in degs)}")
        print(f"  tip xyz (m): {np.round(tip, 3).tolist()}")
        if hits:
            seen = set()
            for g1, g2, d in hits:
                key = (g1, g2, round(d, 4))
                if key in seen:
                    continue
                seen.add(key)
                print(f"  干渉[{classify_contact((g1, g2))}]: {g1} <-> {g2} (dist={d * 1000:.1f} mm)")
            mujoco.mj_forward(model, data)
            if args.render:
                render(model, data, "overview", args.render / "pose.png")
            return 1
        print("  干渉なし")
        if args.render:
            render(model, data, "overview", args.render / "pose.png")
        return 0

    print("\n== 関節掃引（他関節はホーム固定） ==")
    collisions: list[str] = []
    for name in JOINTS:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        adr = model.jnt_qposadr[jid]
        lo, hi = effective_range(name)
        found = []
        for val in np.linspace(lo, hi, max(args.sweep, 3)):
            q = base.copy()
            q[adr] = val
            for g1, g2, d in contacts_at(model, data, q):
                found.append((math.degrees(val), g1, g2, classify_contact((g1, g2))))
        if found:
            self_hits = [f for f in found if f[3] == "self"]
            env_hits = [f for f in found if f[3] == "environment"]
            parts = []
            if self_hits:
                degs_hit = sorted({round(f[0]) for f in self_hits})
                pairs = sorted({f"{f[1]}<->{f[2]}" for f in self_hits})
                parts.append(f"self: {pairs} @ {degs_hit[0]}..{degs_hit[-1]} deg")
            if env_hits:
                degs_hit = sorted({round(f[0]) for f in env_hits})
                pairs = sorted({f"{f[1]}<->{f[2]}" for f in env_hits})
                parts.append(f"env: {pairs} @ {degs_hit[0]}..{degs_hit[-1]} deg")
            print(f"  {name:13s}: 干渉あり — " + " / ".join(parts))
            collisions.append(name)
        else:
            print(f"  {name:13s}: 干渉なし ({math.degrees(lo):+.1f} .. {math.degrees(hi):+.1f} deg)")

    if not args.no_soft_limits and args.soft_limits and args.soft_limits.exists():
        print("\n== soft limits（quest_teleop.yaml, use_degrees 正規化フレーム） ==")
        import yaml

        cfg = yaml.safe_load(args.soft_limits.read_text())
        limits = (cfg.get("safety", {}).get("soft_joint_limits_deg") or {}).get("*") or {}
        calib_path = args.calib_dir / f"{args.calib}.json"
        calib = load_calib_ranges(calib_path) if calib_path.exists() and not args.no_calib else None
        for name, lim in limits.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            lo, hi = effective_range(name)
            note = ""
            if calib and name in calib:
                # fork の degrees は range 中央がゼロ → MJCF(ホーム基準) とは offset ずれる
                raw = json.loads(calib_path.read_text())[name]
                mid_ticks = (raw["range_min"] + raw["range_max"]) / 2.0
                offset_deg = (mid_ticks - HOME_TICKS) * 360.0 / TICKS_PER_TURN
                mj_lo, mj_hi = math.degrees(lo), math.degrees(hi)
                fork_lo, fork_hi = mj_lo - offset_deg, mj_hi - offset_deg
                inside = lim[0] >= fork_lo - 1e-6 and lim[1] <= fork_hi + 1e-6
                note = (f" → 実効 [{fork_lo:+.1f},{fork_hi:+.1f}] deg 内: "
                        f"{'OK' if inside else '!! soft limit が実効域外に逸脱'}")
            print(f"  {name:13s}: soft [{lim[0]:+.1f},{lim[1]:+.1f}] deg{note}")

    if args.render:
        print("\n== 描画 ==")
        mujoco.mj_resetDataKeyframe(model, data, 0)  # home
        mujoco.mj_forward(model, data)
        render(model, data, "overview", args.render / "home.png")
        if collisions:
            name = collisions[0]
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            q = base.copy()
            q[model.jnt_qposadr[jid]] = model.jnt_range[jid][1]
            data.qpos[:] = q
            mujoco.mj_forward(model, data)
            render(model, data, "overview", args.render / f"sweep_{name}_max.png")

    print("\n結果:", "干渉あり — 上記の関節範囲を実運用で避けるかシーンを調整" if collisions else "干渉なし")
    return 1 if collisions else 0


if __name__ == "__main__":
    sys.exit(main())
