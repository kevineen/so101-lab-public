# 21 — 片腕 π₀.₅（pi05）：学習して Thor で推論する

2026-10-20 時点の手順です。録画・選別は [15](15_dataset_pipeline.md)、**PC 間の転送は [23](23_data_transfer.md)**、片腕の運用前提は [14](14_single_arm_il.md)、VRAM は [19](19_vram_guide.md)、ACT と同じマシン分担は [17](17_act_record_train_infer.md)。ここは **pi05 固有のフラグ・チャンク長・Thor 起動** だけを固定します。

> **結論（先に）**  
> - **推論は Thor で実施する**（`policy_type=pi05`、既定チャンク 50）。  
> - **学習は bf16 LoRA（または expert-only）**。LeRobot 0.6.x に **QLoRA フラグは無い**（自前実装が要る）。  
> - 学習ホストは **3090（この PC）を正**、OOM 時の退避として **Thor 上 LoRA** を §2b に書く。

---

## 役割 {#roles}

| マシン | やること | やらないこと |
|--------|----------|----------------|
| Raspberry Pi 4 | 録画、nest、推論クライアント（腕とカメラ） | pi05 の順伝播、`lerobot-train` |
| メインPC RTX 3090（WSL / Tailscale。例: `${SO101_GPU_TAILSCALE_IP}`） | `lerobot-train`（LoRA）。データセット保管・選別 | 実機シリアルは繋がっていない |
| Jetson Thor（`thor` / `${SO101_THOR_TAILSCALE_IP}`） | `policy_server`（CUDA）。任意で §2b の学習 | 腕の USB は挿さない |

Pi 4 の torch では大きい行列積が Illegal instruction になります。計算は Thor、腕は Pi です（[17 §roles](17_act_record_train_infer.md#roles) と同じ）。

LeLab と Web Remote は、録画中も推論中も起動しません。ESTOP は手元に置きます。

---

## 前提チェック {#prereq}

着手前に全て確認します。

- [ ] デモデータがある（目安 40〜50 ep。タスク文付き。カメラキーは学習と推論で一致）
- [ ] Pi / 3090 / Thor の `~/robot/lerobot`が **同じコミット**
- [ ] Hugging Face にログイン済み（PaliGemma / `lerobot/pi05_base` はゲートあり）
- [ ] 学習ホストに `peft` extra が入っている（下）
- [ ] Thor の `SUPPORTED_POLICIES` に `"pi05"` がある（現行 fork では既定で含まれる）
- [ ] ACT スモーク経路（[17](17_act_record_train_infer.md)）で Thor `:8080` が一度でも通っていると安心

### HF ログイン（各学習ホストで）

```bash
# ブラウザで https://huggingface.co/google/paligemma-3b-pt-224 のライセンスに同意済みであること
hf auth login
# またはターミナルだけで: export HF_TOKEN=hf_...
```

### peft のインストール

```bash
# 3090 側（例）
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot
uv pip install --python .venv/bin/python -e ".[peft]"

# Thor 側（推論だけなら不要。§2b で学習するときだけ）
cd ~/robot/lerobot
uv pip install --python .venv/bin/python -e ".[peft]"
```

```bash
.venv/bin/python -c "import peft; print(peft.__version__)"
```

### QLoRA について（やらないこと）

[19 §4](19_vram_guide.md#quantization) のとおり、**`--load_in_4bit` / QLoRA 用 CLI は無い**。  
Thor の unified memory は大きいので、退避先は **QLoRA ではなく §2b の bf16 LoRA（または `train_expert_only`）** です。

---

## 1. データセット（Pi 録画 → 学習ホストへ）

録画・結合・選別は [15](15_dataset_pipeline.md) / [17 §1](17_act_record_train_infer.md) と同じです。

pi05 固有の注意:

| 項目 | 内容 |
|------|------|
| タスク文 | 学習時の `single_task` と推論の `--task` を **一字一句同じ** にする |
| カメラキー | データセットの `observation.images.*` と Pi クライアントのカメラ名を一致させる（例: `front` / `wrist`） |
| 量子統計 | pi05 既定は state/action が **QUANTILES**。欠損時はデータ側で quantile を足す（[10](10_molmoact2_thor.md) の `augment_dataset_quantile_stats` と同様） |
| 本数 | ACT で 5/10 未満なら先にデモを足す。VLA はデモ不足を魔法で補わない |

データセット root の例（3090）:

```text
$HOME/.cache/huggingface/lerobot/local/<repo_id>
```

---

## 2. 学習する（正本: 3090） {#train-3090}

作業ディレクトリは so101-lab から見て `../lerobot`（<user> 所有）。`sudo` は付けません。

まず **200〜500 step のスモーク**で `nvidia-smi` を見てから本番 step にします。3090 24GB は LoRA + grad ckpt + bf16 + BS 1 で **Tight（>22GB 帯）** です。

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot
.venv/bin/lerobot-train \
  --dataset.repo_id=local/<repo_id> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<repo_id> \
  --policy.type=pi05 \
  --policy.pretrained_path=lerobot/pi05_base \
  --policy.device=cuda \
  --policy.dtype=bfloat16 \
  --policy.gradient_checkpointing=true \
  --policy.push_to_hub=false \
  --peft.r=32 \
  --peft.lora_alpha=32 \
  --batch_size=1 \
  --steps=500 \
  --output_dir=outputs/train/pi05_so101_<task>_smoke_<日付> \
  --job_name=pi05_so101_<task>_smoke_<日付> \
  --seed=1000
```

OOM したら（効く順）:

1. `--policy.train_expert_only=true` と `--policy.freeze_vision_encoder=true` を足す（LoRA と併用可だが、まずはどちらか一方で様子を見る）
2. `--batch_size=1` のまま `--gradient_accumulation=4` などで実効バッチを稼ぐ
3. **§2b（Thor で学習）** へ退避
4. QLoRA はフラグが無いのでこの文書の対象外

スモークが通ったら本番（例: 20k〜30k step。データ規模に合わせる。scheduler は steps に合わせて自動スケールされることが多い）:

```bash
.venv/bin/lerobot-train \
  --dataset.repo_id=local/<repo_id> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<repo_id> \
  --policy.type=pi05 \
  --policy.pretrained_path=lerobot/pi05_base \
  --policy.device=cuda \
  --policy.dtype=bfloat16 \
  --policy.gradient_checkpointing=true \
  --policy.push_to_hub=false \
  --peft.r=32 \
  --peft.lora_alpha=32 \
  --batch_size=1 \
  --steps=20000 \
  --save_freq=5000 \
  --output_dir=outputs/train/pi05_so101_<task>_<日付> \
  --job_name=pi05_so101_<task>_<日付> \
  --seed=1000
```

曲線を残すとき（so101-lab 側）:

```bash
# so101-lab リポジトリ直下で実行
./scripts/train_mlflow.sh \
  --dataset.repo_id=local/<repo_id> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<repo_id> \
  --policy.type=pi05 \
  --policy.pretrained_path=lerobot/pi05_base \
  --policy.device=cuda \
  --policy.dtype=bfloat16 \
  --policy.gradient_checkpointing=true \
  --policy.push_to_hub=false \
  --peft.r=32 \
  --peft.lora_alpha=32 \
  --batch_size=1 \
  --steps=20000 \
  --output_dir=outputs/train/pi05_so101_<task>_<日付> \
  --job_name=pi05_so101_<task>_<日付> \
  --seed=1000
```

チェックポイント:

```text
outputs/train/pi05_so101_<task>_<日付>/checkpoints/last/pretrained_model
```

Hub には上げません。このディレクトリごと Thor へ送ります。

> **EMA**: `--ema.enable=true` は LoRA（PEFT）と併用不可（OpenPI / LeRobot の注記どおり）。LoRA 経路では付けない。

---

## 2b. 学習する（退避: Thor） {#train-thor}

3090 が OOM する、または長時間学習を Thor に寄せたいときの経路です。  
**腕は付けない。** 先に **実データセット** を Thor へ送る（正本: [23 §4](23_data_transfer.md#ds-gpu-thor)）。  
`local/my_so101_task` のような仮名は使わない（未転送だと Hub 404 になる）。

```bash
# GPU で（NAME は meta/info.json がある実名）
NAME=<実ディレクトリ名>
rsync -a $HOME/.cache/huggingface/lerobot/local/${NAME}/ \
  <user>@${SO101_THOR_TAILSCALE_IP}:$HOME/.cache/huggingface/lerobot/local/${NAME}/
```

```bash
# Thor で
cd ~/robot/lerobot
uv run --no-sync python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

uv run --no-sync python -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=local/${NAME} \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/${NAME} \
  --policy.type=pi05 \
  --policy.pretrained_path=lerobot/pi05_base \
  --policy.device=cuda \
  --policy.dtype=bfloat16 \
  --policy.gradient_checkpointing=true \
  --policy.push_to_hub=false \
  --peft.r=32 \
  --peft.lora_alpha=32 \
  --batch_size=2 \
  --steps=500 \
  --output_dir=outputs/train/pi05_so101_<task>_thor_smoke_<日付> \
  --job_name=pi05_so101_<task>_thor_smoke_<日付> \
  --seed=1000
```

Thor はメモリに余裕があるので、スモーク後は BS を 2〜4 まで上げてよいです。  
終わったら `checkpoints/last/pretrained_model` をホーム直下など推論用パスへコピー（またはそのまま絶対パスでサーバへ渡す）。

---

## 3. Thor で policy_server を上げる {#server}

### 3a. 重みを Thor へ送る（3090 で学習した場合）

正本: [23 §5](23_data_transfer.md#ckpt-gpu-thor)。`--pretrained_name_or_path` は **Thor 上のパス**。

```bash
# 3090 で
JOB=pi05_so101_<task>_<日付>
rsync -a ../lerobot/outputs/train/${JOB}/checkpoints/last/pretrained_model/ \
  <user>@${SO101_THOR_TAILSCALE_IP}:~/${JOB}/
```

### 3b. Python 3.14 パッチ（初回・venv 作り直し後）

```bash
# Thor で
# so101-lab リポジトリ直下で実行
uv run --no-sync python scripts/patch_draccus_py314.py
```

`already patched` または `patched:` が出てからサーバを起動します。

### 3c. サーバ起動

```bash
cd ~/robot/lerobot
uv run --no-sync python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
uv run --no-sync python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 \
  --port=8080 \
  --fps=30 \
  --obs_queue_timeout=5
```

`True` と `NVIDIA Thor`、続けて `PolicyServer started on 0.0.0.0:8080` を確認します。  
ファイアウォールを使うときは、Pi から TCP 8080 だけを開けます（[07](07_multi_host.md) / [10](10_molmoact2_thor.md)）。

---

## 4. Pi で推論する {#client}

初回だけ gRPC:

```bash
cd ~/robot/lerobot
uv pip install --python .venv/bin/python 'grpcio>=1.73.1,<2'
```

follower を nest へ:

```bash
# so101-lab リポジトリ直下で実行
./scripts/go_so101_home.sh --arm follower
```

物体配置は録画と同じにします。サーバが `PolicyServer started` を出してからクライアントを起動します。

```bash
cd ~/robot/lerobot
.venv/bin/python -m lerobot.async_inference.robot_client \
  --robot.type=so101_follower \
  --robot.port=${SO101_FOLLOWER_PORT} \
  --robot.id=my_follower \
  --robot.max_relative_target=5 \
  --robot.disable_torque_on_disconnect=false \
  --robot.cameras='{ front: {type: intelrealsense, serial_number_or_name: "${SO101_REALSENSE_SERIAL}", width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} }' \
  --server_address=${SO101_THOR_TAILSCALE_IP}:8080 \
  --policy_type=pi05 \
  --pretrained_name_or_path=$HOME/pi05_so101_<task>_<日付> \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=50 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  --task="<学習時と同じタスク文>"
```

| フラグ | ACT（[17](17_act_record_train_infer.md)） | pi05（本手順） |
|--------|-------------------------------------------|----------------|
| `--policy_type` | `act` | **`pi05`** |
| `--actions_per_chunk` | 100 | **`50`**（既定 `n_action_steps`。学習で変えたら合わせる） |
| `--task` | ログ用 | **必須（学習文と一致）** |

カメラ by-path / RealSense シリアルは [05](05_cameras.md) で実機に合わせて書き換えます。  
Thor ログに `Policy type: pi05` が出てから腕が動きます。止めるときはクライアントを `Ctrl+C` → nest。

```bash
# so101-lab リポジトリ直下で実行
./scripts/go_so101_home.sh --arm follower
```

---

## 5. 評価プロトコル

[17 §5](17_act_record_train_infer.md) と同じ土俵で比較します。

| 項目 | 既定 |
|------|------|
| 試行 | **10 試行**（nest から。物体は毎回同じ位置） |
| 成功 | 学習時タスク文の完了条件 |
| 記録 | [作業レポート](reports/single_arm_il_work_report.md) に S- セッション（ACT / SmolVLA / Diffusion / TurboVLA と同じ行形式） |
| 目安 | 10 試行中の成功数と失敗モードを書く（pi05 が ACT より良いかはデータとタスク次第） |

---

## うまくいかないとき

| 症状 | 見る場所 |
|------|----------|
| `peft` / `ModuleNotFoundError` | §前提の `.[peft]` インストール |
| HF 401 / gated | `hf auth login` と PaliGemma ライセンス同意 |
| 3090 で CUDA OOM | §2 の expert-only / accumulation → §2b Thor 学習 |
| Thor が `Policy type pi05 not supported` | fork の `SUPPORTED_POLICIES` に `pi05` があるか。コミットを 3090 側と揃える |
| Thor が `PolicyFeature] \| None is not callable` | `scripts/patch_draccus_py314.py` のあとサーバ再起動 |
| クライアント `Failed to connect` | Thor `:8080`、重みパスは Thor 側、Tailscale 疎通 |
| 腕が動かない／意味不明 | `--task` 不一致、カメラキー不一致、`actions_per_chunk` が checkpoint と違う |
| Pi の `lerobot-rollout` が Illegal instruction | 想定どおり。本手順の Thor 経路を使う |
| QLoRA したい | **不可（フラグ無し）**。[19 §4](19_vram_guide.md#quantization)。Thor LoRA か A100 級 Full/LoRA へ |

---

## 関連

| 文書 | 内容 |
|------|------|
| [23](23_data_transfer.md) | **PC 間転送の正本**（データセット・重み） |
| [17](17_act_record_train_infer.md) | ACT の通し（マシン分担の型） |
| [19](19_vram_guide.md) | pi05 LoRA / QLoRA の VRAM 目安 |
| [14](14_single_arm_il.md) | 片腕 IL 運用正本 |
| [10](10_molmoact2_thor.md) | Thor policy_server の双腕例 |
| [20](20_turbovla.md) | 別系統の軽量 VLA（比較候補） |
| upstream | [LeRobot pi05](https://huggingface.co/docs/lerobot/en/pi05) · `lerobot/pi05_base` |
