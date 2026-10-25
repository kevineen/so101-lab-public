# 12 — MuJoCo シミュレーション環境（可動域・干渉チェック）

3D モデル上で **可動域（joint range）** と **干渉（self / 環境との collision）** を
設定・検証するための MuJoCo 環境。実機・USB・カメラは一切使わないので、
LeLab / Web Remote と **同時起動してよい**（Pi 上でヘッドレス動作可）。

| 構成要素 | パス |
|----------|------|
| シーン（MJCF） | [`assets/robots/so101/sim/so101_scene.xml`](../assets/robots/so101/sim/so101_scene.xml) |
| メッシュ（STL） | `assets/robots/so101/meshes/`（既存と共用 + 干渉判定用 5 個） |
| 検証スクリプト | [`scripts/sim_check.py`](../scripts/sim_check.py) |
| viewer 起動 | [`scripts/start_sim_viewer.sh`](../scripts/start_sim_viewer.sh)（要ディスプレイ） |
| 出典・ライセンス | [`assets/robots/so101/NOTICE.md`](../assets/robots/so101/NOTICE.md) |

## クイックスタート（Pi・SSH で OK）

```bash
# 関節ごとに可動域を掃引して干渉チェック（キャリブ自動適用）
~/robot/lerobot/.venv/bin/python scripts/sim_check.py

# 特定姿勢のチェック（deg・順番: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper）
~/robot/lerobot/.venv/bin/python scripts/sim_check.py --pose "0,-40,-20,-40,0,20"

# もう一方の腕のキャリブで検証
~/robot/lerobot/.venv/bin/python scripts/sim_check.py --calib my_leader_drive

# 設計値レンジ（キャリブ無視）で挙動比較
~/robot/lerobot/.venv/bin/python scripts/sim_check.py --no-calib
```

終了コード: `0`=干渉なし / `1`=干渉あり / `2`=エラー。将来のゲート組み込みを想定。

## 何をしているか

### 可動域（joint range）

- シーン XML の `range` は SO-101 の**設計値**（URDF と同一・ゼロ姿勢基準）。
- `sim_check.py` は実行時に lerobot のキャリブレーション JSON
  （`~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json`）を読み、
  `実効レンジ = (range_min/max ticks − 2048) × 2π/4095 [rad]`（homing 2048 tick = ゼロ姿勢）
  を**設計値との共通範囲**として `model.jnt_range` へ上書きする。XML は書き換えない。
- キャリブ範囲が設計値とほぼ重ならない関節（中央がホームから大きくズレた録り損ない）は
  設計値を維持して警告を出す。現在 `my_follower` の gripper が該当（要再キャリブ）。

### 角度の単位・フレーム

- MJCF の関節角 = 実機のホーム姿勢基準（`qpos=0` がキャリブレーションホーム）。
- lerobot フォーク（`use_degrees=True`）の degrees は **キャリブ範囲の中央がゼロ** のため、
  関節ごとに `offset = (mid − 2048) × 360/4095 deg` ずれる。
  `sim_check.py` の soft limits 表示はこの変換を踏まえた上で
  `configs/quest_teleop.yaml` の `soft_joint_limits_deg` が実効域内かを検証する。

### 干渉（collision）

- `class="collision"` / `collision_gripper` の geom（box・簡易メッシュ）のみ衝突計算に参加。
  表示用 STL は非衝突。
- `sim_check.py` は qpos を直接設定して `mj_forward` → 貫入 (`dist < 0`) を報告
  （動力学シミュレーションではなく運動学チェック）。
- 環境 geom: `table`（机・前端は base から +0.05 m。実機に合わせて XML を編集）、
  `floor`、`obstacle_box`（mocap — viewer 上でドラッグ移動できる障害物）。
- 掃引は「他関節ホーム固定」なので、組み合わせ姿勢の干渉は `--pose` で確認する。

## viewer（要ディスプレイ）

```bash
./scripts/start_sim_viewer.sh          # Pi デスクトップ / VNC / ssh -X 上で
```

- Ctrl+ドラッグで視点回転、スペースで物理再生、`obstacle` をダブルクリック後
  ドラッグで障害物を動かして干渉を観察できる。
- SSH（ディスプレイ無し）では起動しない。画像が欲しいだけなら:

```bash
sudo apt install -y libegl1 libgl1-mesa-dri   # 初回のみ（要 sudo）
MUJOCO_GL=egl ~/robot/lerobot/.venv/bin/python scripts/sim_check.py --render /tmp/sim
```

## 現在の判定結果（2026-10 時点・my_follower）

- 実効可動域: elbow の +92° 側が設計値 +96.8° から -5° 程クリップ。他は設計値と同等。
- 自己干渉: elbow +92° 付近で shoulder holder と前腕〜手首が接触
  （実際に折り畳みすぎると当たる。soft limits の elbow ±80° なら未到達）。
- quest_teleop.yaml の soft limits は全関節とも実効域内。

## 今後の拡張（未実装）

- 双腕シーン（左右 2 台を同時に置いて腕同士の干渉チェック）
- テレオペ受信機（`bridges/`）への干渉ゲート組み込み — 指令関節角を送る前に
  sim と同じ接触判定で拒否/クランプ
- Isaac Sim / Isaac Lab（メイン PC）での高精度版 — [08](08_quest_isaacteleop.md) の環境を流用

なお GPU 上で重力・接触・PD サーボを積分する**動力学**シミュは
[21 Kamino sim](22_kamino_sim.md)（Newton・同じ MJCF を共用）に分離した。
