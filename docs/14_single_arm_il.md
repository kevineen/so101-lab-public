# 14 — 片腕 IL（ACT / SmolVLA）手順書

第2腕（物理 leader）を **駆動腕として使わない**前提で、**follower 1 本**に対してデモ収集 → ACT / VLA 学習 → 実機推論まで進めるラボ手順です。

関連: [04_calibration.md](04_calibration.md) · [02_lelab.md](02_lelab.md) · [13_drive_profiles.md](13_drive_profiles.md) · [10_molmoact2_thor.md](10_molmoact2_thor.md) · [15_dataset_pipeline.md](15_dataset_pipeline.md) · [17_act_record_train_infer.md](17_act_record_train_infer.md) · [checklists/single_arm_il.checklist.md](checklists/single_arm_il.checklist.md)

**初学者向けの読み順・概念**: [learn/](learn/README.md)（第2章が本手順の学習ラッパ）  
上流チュートリアル: [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots) · [ACT](https://huggingface.co/docs/lerobot/act) · [SmolVLA](https://huggingface.co/docs/lerobot/smolvla)

---

## 結論（先に読む）

| 役割 | いまのラボ方針 |
|------|----------------|
| **駆動（学習・推論の対象）** | **follower のみ**（6 関節） |
| **テレオペ（デモ収集）** | 物理 leader を **手で動かす**（`so101_leader`）。トルク不足の「駆動」とは別物 |
| **Web Remote 第2ポート** | `leader_arm.enabled: false`（または `--no-leader`） |
| **学習マシン** | **GPU ホスト**（Pi では本格学習しない） |
| **最初に試すモデル** | **ACT** → 慣れたら **SmolVLA**（必要なら MolmoAct2 片腕は [10](10_molmoact2_thor.md)） |

**混同しないこと**

| id / type | 用途 |
|-----------|------|
| `so101_follower` + `my_follower` | 駆動腕（録画・学習・推論） |
| `so101_leader` + `my_leader` | **手で動かす**テレオペ（デモ収集） |
| `so101_follower` + `my_leader_drive` | Web Remote で旧 leader ポートを **駆動**する用 → **片腕 IL では使わない** |

`my_leader_drive` は「第2駆動腕」用です。テレオペ用 `my_leader` とは別ファイルです。

---

## ラボ固定値（2026-10 時点）

```bash
# シェルに一度貼る（by-id は挿し直しに強い）
export FOLLOWER_PORT=${SO101_FOLLOWER_PORT}
export LEADER_PORT=${SO101_LEADER_PORT}
export FOLLOWER_ID=my_follower
export LEADER_ID=my_leader

# Hugging Face（データセット / ポリシーの push に必要）
# hf auth login
export HF_USER=$(NO_COLOR=1 hf auth whoami | awk -F': *' 'NR==1 {print $2}')
echo "HF_USER=$HF_USER"
```

カメラは録画・推論で **同じキー名・解像度・fps** に揃えます（推奨は 640×480）。

| キー | 用途 | 指定例 |
|------|------|--------|
| `front` | 俯瞰（D435 推奨） | `type: intelrealsense`, serial `${SO101_REALSENSE_SERIAL}` |
| `wrist` | follower 先端 | OpenCV + by-path（[05_cameras.md](05_cameras.md)） |

Xiao MJPEG を俯瞰にする場合は `type: opencv` + `index_or_path` に URL（例: `${SO101_CAMERA_XIAO_URL}`）を使えます。キー名は学習時と一致させてください。

---

## Step 0 — 安全・独占

1. **LeLab と Web Remote を止める**（シリアル／カメラの奪い合い防止）  
2. ESTOP の置き場を確認  
3. follower が机・ケーブルに干渉しないホーム付近にあること  

Web Remote を片腕だけで触るとき:

```bash
# yaml を enabled: false にするか、起動時だけ:
./scripts/start_web_remote.sh --no-leader
```

設定正本: [`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml)

---

## Step 1 — キャリブ

### 1a. follower（必須・既にあればスキップ）

```bash
cd ~/robot/lerobot
# activate 不要。.venv/bin/ のツールを直接パスで実行する

.venv/bin/lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID
```

保存先: `~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_follower.json`

### 1b. leader テレオペ用（デモ収集するなら必須）

```bash
.venv/bin/lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=$LEADER_PORT \
  --teleop.id=$LEADER_ID
```

保存先: `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/my_leader.json`（パスは LeRobot 版で多少違う場合あり。無いときは初回キャリブで生成）

**注意:** `my_leader_drive.json` があっても **テレオペ用には使えません**。別 id で取り直してください。

---

## Step 2 — テレオペ確認（録画前）

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --teleop.type=so101_leader \
  --teleop.port=$LEADER_PORT \
  --teleop.id=$LEADER_ID \
  --robot.cameras="{ \
    front: {type: intelrealsense, serial_number_or_name: \"${SO101_REALSENSE_SERIAL}\", width: 640, height: 480, fps: 30}, \
    wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} \
  }" \
  --display_data=true
```

- leader を手で動かすと follower が追従すること  
- 両カメラ映像が出ること  
- Overload / ランプ点滅が無いこと（follower 側）  

`wrist` の by-path はハブ差し替えで変わることがあります → [05_cameras.md](05_cameras.md)。

---

## Step 3 — デモ録画（データセット）

目安: **タスクあたり 40〜50 episodes**（SmolVLA はバリエーションも繰り返す）。最初のスモークは 5 ep で十分です。

開始姿勢は保存ファイルではなく、録画開始時の leader の関節角です。秒数は録画 30 秒・リセット 15 秒。理由と、録画前に nest へ揃える手順は [15 — 初期位置](15_dataset_pipeline.md#initial-pose) と [15 — 本数と時間](15_dataset_pipeline.md#episodes-and-time)。

```bash
TASK="Pick the red cube and place it in the bin"
REPO_ID=${HF_USER}/so101_single_pickplace

lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --teleop.type=so101_leader \
  --teleop.port=$LEADER_PORT \
  --teleop.id=$LEADER_ID \
  --robot.cameras="{ \
    front: {type: intelrealsense, serial_number_or_name: \"${SO101_REALSENSE_SERIAL}\", width: 640, height: 480, fps: 30}, \
    wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} \
  }" \
  --display_data=true \
  --dataset.repo_id=$REPO_ID \
  --dataset.num_episodes=50 \
  --dataset.episode_time_s=30 \
  --dataset.reset_time_s=15 \
  --dataset.single_task="$TASK" \
  --dataset.streaming_encoding=true \
  --dataset.encoder_threads=2
```

録画中の操作はキーボードの `n` / `r` / `q` です。同じ Wi-Fi のブラウザから「成功」「失敗」を送る手順は [15 — ブラウザ](15_dataset_pipeline.md#record-buttons)。

GUI で進めたい場合は LeLab（[02_lelab.md](02_lelab.md)）の Record でも可。**カメラキーと `single_task` 文面は後段と揃える**こと。

Hub に上げないローカル録画、`info` による閲覧、失敗エピソードの削除、タスク文の修正、GPU へ渡すときの `--dataset.root` は **[15_dataset_pipeline.md](15_dataset_pipeline.md)**。実施したパスと本数は [作業レポート](reports/single_arm_il_work_report.md) に書く。

可視化（任意）:

```bash
# Hub に push 済みなら
# https://huggingface.co/spaces/lerobot/visualize_dataset
```

---

## Step 4 — 学習（GPU ホスト）

Pi では回しません。メイン PC / Thor / クラウドで、同じ `~/robot/lerobot` コミットを使うのが安全です。

学習は **`train_mlflow.sh` 経由**で回します（[16 のルール](16_local_mlflow.md)。素の `lerobot-train` は MLflow に記録が残らない）。`output_dir` / `job_name` は `{policy}_{タスク}_{カメラ}-{バリアント}_{日付}` の命名規約に従い、両者を一致させます（例: `act_cobra_frontwrist-bs32_20261020`）。

### 4a. ACT（最初の推奨）

追加 extra 不要。デフォルト超パラメータで十分なことが多いです。

損失曲線はローカル MLflow に残します。先に別端末で UI を上げます（[16](16_local_mlflow.md)）。

```bash
# 端末 1
./scripts/start_mlflow.sh          # http://127.0.0.1:5000

# 端末 2（cwd は ~/robot/lerobot になる）
./scripts/train_mlflow.sh \
  --dataset.repo_id=$REPO_ID \
  --policy.type=act \
  --output_dir=outputs/train/act_so101_single \
  --job_name=act_so101_single \
  --policy.device=cuda \
  --policy.repo_id=${HF_USER}/act_so101_single
```

Colab でも可（公式 ACT notebook）。曲線の確認は [16](16_local_mlflow.md)。

### 4b. SmolVLA（軽量 VLA）

```bash
# 初回のみ依存（lerobot の venv）
cd ~/robot/lerobot
uv pip install --python .venv/bin/python -e ".[smolvla]"
# so101-lab リポジトリ直下で実行

./scripts/train_mlflow.sh \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=$REPO_ID \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/smolvla_so101_single \
  --job_name=smolvla_so101_single \
  --policy.device=cuda \
  --policy.repo_id=${HF_USER}/smolvla_so101_single
```

- タスク文（`single_task`）を使う。推論時も **同じ文面**  
- VRAM が足りなければ `--batch_size` を下げる  
- 目安: A100 で 20k steps ≈ 数時間（公式ドキュメント準拠）

### 4c. Diffusion Policy（ACT との比較用）

ACT と**同じデータセット**で回せる 3 番目の比較候補（R-PAPER-DIFFPOLICY）。
行動を拡散で生成する IL で、多様なデモには強いが推論が重いのが特徴です。
シム側の自前実装（sim2rl EVA-Diffusion）との対比は
[learn 第4章](learn/04_other_vla/README.md) を参照。

```bash
# so101-lab リポジトリ直下で実行
./scripts/train_mlflow.sh \
  --policy.type=diffusion \
  --dataset.repo_id=$REPO_ID \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/diffusion_so101_single \
  --job_name=diffusion_so101_single \
  --policy.device=cuda
```

- 既定は `horizon=64`・`n_action_steps=32`・`n_obs_steps=2`（`configuration_diffusion.py`）。
  30 fps の実機では 32 ステップ ≒ 1 秒強の行動チャンク
- ACT より VRAM を食う。4090 で batch 64 が厳しければ 32 へ
- 評価は [17 §5](17_act_record_train_infer.md) の 10 試行プロトコルで ACT・SmolVLA と並べる

**Thor 推論時の注意**: `policy_server` は `diffusion` を既定でサポート
（`async_inference/constants.py` の `SUPPORTED_POLICIES` に含まれる。
MolmoAct2 のような fork 編集は不要）。クライアントの `--actions_per_chunk` は
**32**（ACT は 100）に合わせます:

```bash
  --policy_type=diffusion \
  --actions_per_chunk=32 \
```

### 4d. その他 VLA（後回しでよい）

| モデル | 片腕での位置づけ | 参照 |
|--------|------------------|------|
| MolmoAct2 | 公開 `MolmoAct2-SO100_101` は片腕スモーク可。常用は自データ FT | [10](10_molmoact2_thor.md) |
| π0 / π0.5 / X-VLA 等 | GPU・ライセンス・データ要件が重い。ACT/SmolVLA の後 | `~/robot/lerobot/docs/source/` |

### 4e. 発展 — 失敗・介入データからのポストトレーニング（GR-BC）

通常の IL 学習（Step 4）が済んだあと、評価で出た**失敗ロールアウトもデータにして**
SmolVLA を追加学習する経路が `~/robot/GR-BC` に用意してあります
（スマホ評価に `SO101_INFER_RECORD=1` を付けるだけ。詳細は [26](26_grbc_posttraining.md)）。

---

## Step 5 — 実機推論（follower のみ）

学習時と同じカメラキーで起動します。LeLab / Web Remote は止めます。

このラボの Pi 4 では、下の `lerobot-rollout` は ACT の順伝播で Illegal instruction になります。動いた経路は、4090 の WSL で学習し、Jetson Thor の `policy_server` で計算し、Pi はクライアントだけにすることです。コマンドとパスは [17](17_act_record_train_infer.md) に固定しています。下の `lerobot-rollout` は、CUDA が見えるホストに腕を直接挿したときの形です。

### ACT

```bash
POLICY=${HF_USER}/act_so101_single   # または outputs/train/.../checkpoints/last

lerobot-rollout \
  --strategy.type=base \
  --policy.path=$POLICY \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --robot.cameras="{ \
    front: {type: intelrealsense, serial_number_or_name: \"${SO101_REALSENSE_SERIAL}\", width: 640, height: 480, fps: 30}, \
    wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} \
  }" \
  --display_data=true \
  --duration=60
```

### SmolVLA

```bash
POLICY=${HF_USER}/smolvla_so101_single

lerobot-rollout \
  --strategy.type=base \
  --policy.path=$POLICY \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --robot.cameras="{ \
    front: {type: intelrealsense, serial_number_or_name: \"${SO101_REALSENSE_SERIAL}\", width: 640, height: 480, fps: 30}, \
    wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} \
  }" \
  --task="$TASK" \
  --display_data=true \
  --duration=60
```

評価エピソードをデータセットとして残す場合は `lerobot-record ... --policy.path=...` も使えます（公式 IL ガイド）。

---

## LeLab で同じことをする場合

1. `./scripts/start_lelab_lan.sh`（Web Remote は止める）  
2. UI で follower / leader ポートを by-id に合わせる  
3. Record → Train（HF Jobs や別 GPU）→ Inference  
4. **片腕 IL では第2ポートを follower 駆動にしない**（テレオペ leader としてのみ）  

詳細は [02_lelab.md](02_lelab.md)。

---

## トラブルシュート（短い表）

| 症状 | 確認 |
|------|------|
| leader を駆動しようとすると動かない / Overload | それは想定どおり。本手順では **手テレオペのみ**。駆動は follower |
| `my_leader` が無い | Step 1b を実行（`my_leader_drive` では代用不可） |
| 学習はできたが推論がおかしい | カメラキー・解像度・`robot.id`・タスク文の不一致 |
| Pi で学習が終わらない | GPU ホストへ移す（本ドキュメントの方針） |
| Web Remote が第2腕を開く | yaml `enabled: false` または `--no-leader` |
| 第2駆動腕が欲しくなった | follower（できれば 12V）換装 → [13](13_drive_profiles.md) |

---

## チェックリスト

進捗記録用: [checklists/single_arm_il.checklist.md](checklists/single_arm_il.checklist.md)

```bash
cp docs/checklists/single_arm_il.checklist.md docs/checklists/single_arm_il.local.md
```
