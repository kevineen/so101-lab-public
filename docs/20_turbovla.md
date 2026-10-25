# 20 — TurboVLA: コブラタスクへの適用調査と導入計画（ルートA/B）

2026-10-19 時点。[TurboVLA](https://arxiv.org/abs/2607.27205)（LLM を使わない軽量 VLA、0.2B/0.4B、4090 で推論 31ms / 0.9GiB）をコブラタスク（SO-101 片腕、[15](15_dataset_pipeline.md) のデータセット）に乗せるための調査結果と実行計画。**調査完了・実装未着手**。diffusion 学習（`diffusion_so101_cobra_curated_20261019`）の完了後に ルートA → ルートB の順で進める。

- クローン: `../TurboVLA`（commit `a3365e8` 2026-10-10、Apache-2.0）
- 公式は LIBERO / RoboTwin 2.0（シミュレータ）のみ。実機データの手順は無いので、この doc がその対応手順の正本。

---

## 1. 調査で確定したこと {#findings}

### アーキテクチャとインターフェース

`turbovla/models/turbovla.py` の `TurboVLA.forward` は次の形で、lerobot policy 化（ルートB）しやすい:

```python
forward(instructions: list[str], pixel_values [B,V,3,H,W], state [B,state_dim])
  -> action chunk [B, horizon, action_dim]
```

| 部品 | 中身 | 備考 |
|------|------|------|
| text | BERT base uncased、**凍結** | 実行時オンラインエンコード、キャッシュ不要 |
| vision | DINOv3 ViT-B（LIBERO）/ ViT-L（RoboTwin） | `attn_implementation` は flash_attention_2 → **sdpa に自動フォールバック**（flash-attn 不要） |
| interaction | 双方向 attention 6 層、hidden 256 | 論文の V+L→A の本体 |
| action head | ACT 風デコーダ、損失 L1 | horizon は設定可（LIBERO 12 / RoboTwin 50） |

次元（`turbovla/models/configuration.py`）: `action_dim` / `state_dim` / `horizon` / `num_views` / `image_size` はすべてコンフィグ値。**SO-101 は 6/6/12/2/224** でいく。

### 公開チェックポイントから転移するもの

`third_party/starvla_runtime/starVLA/model/framework/VLM4A/TurboVLA.py` の `_load_initialization`（L283）が確定要素。`TURBOVLA_INIT_CKPT`（= GroundingDINO Swin-T OGC の `.pth`）から読み込むのは:

- `bert.*`（text encoder 本体）
- `feat_map.*`（text projection）
- `transformer.encoder.*`（interaction 層）

**DINOv3 は自前の事前学習重み、vision projection と action head は新規初期化**（ロボット依存の形状のため）。つまり「公開 VLA 重みのフル転移」ではなく、**言語・interaction のみ暖機済みの小規模 VLA を 46 エピソードで訓練する**のが実際の性質。期待値は ACT+言語条件付き の強化版とし、ACT / SmolVLA との比較で判断する。

### データパイプライン（ルートAの要）

RoboTwin 経路は GR00T 系ローダ（`starVLA/dataloader/gr00t_lerobot/`）で **LeRobot v2.0 / v3.0 両対応**（`datasets.py` `_infer_lerobot_version`）。GR00T 形式とは **`meta/modality.json` のメタデータ層だけ** で、`original_key` は標準 LeRobot 列名を指す（`experiments/robotwin/configs/modality.json` 参照: `observation.state` / `action` / `observation.images.cam_high` / `task_index`）。→ **コブラデータセットのコピー・列変換は不要。`meta/modality.json` を1ファイル足すだけ**。

サンプル形式（`datasets.py` `_pack_sample`）: `{action [T,dim], image [PIL×V], lang str, state [1,dim]}`。正規化はデータセット統計から自動計算（min_max は [-1,1] 範囲）。画像は `obs_image_size` へ PIL resize（アスペクト無視、RoboTwin と同一仕様）。

### その他の確定事項

- 学習起動は accelerate。`trainer.use_deepspeed: false` で **deepspeed なし単 GPU** で動く（`train_starvla.py` `build_accelerator`）。`wandb` は import 必須 → `WANDB_MODE=disabled` で無効化。
- データレジストリは `experiments/*/data_registry/` を**自動発見**（`gr00t_lerobot/registry.py`）→ コア無修正で `experiments/so101/` を追加するだけでよい。
- 推論サーバとして `deployment/model_server/server_policy.py`（websocket、`predict_action` → `normalized_actions`、クライアント側で unnormalize）が同梱。
- 依存: `pip install -e ".[robotwin]"`（torch>=2.3, transformers>=4.56, accelerate 1.5.2 など）。**lerobot venv とは別 venv**（lerobot 側に transformers が無い）。

### コブラデータセット（curated）との照合

`local/so101_singlearm_pickup_cobra_20261018_205119_curated` / `$HOME/.cache/huggingface/lerobot/local/...`:

| 項目 | 値 | TurboVLA 側の対応 |
|------|-----|-------------------|
| 形式 | LeRobot **v3.0** | ローダが対応済み |
| fps / 規模 | 30 fps、46 エピソード / 8,567 フレーム | horizon 12 に対し十分（平均 186 frames/ep） |
| カメラ | `observation.images.front` + `observation.images.wrist`（480×640） | num_views=2（LIBERO と同構成）、224×224 へリサイズ |
| action / state | [6]（deg。グリッパーも 0–94°） | 6 次元すべて **min_max**（binary 指定は不可） |
| タスク文 | `meta/tasks.parquet` + `task_index` | `annotation.human.action.task_description` → `task_index` で読める |

---

## 2. ルートA — TurboVLA リポジトリ直で学習 {#route-a}

工数小。4090 単 GPU。手順:

### A-1. venv とモデル取得

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../TurboVLA
uv pip install -e ".[robotwin]"
```

モデル（~2.3GB、`$HOME/models/` に置く想定）:

| 資産 | 取得元 | 用途 |
|------|--------|------|
| BERT base uncased | HF `google-bert/bert-base-uncased` | text encoder |
| DINOv3 ViT-B | HF `facebook/dinov3-vitb16-pretrain-lvd1689m` | vision encoder（まず ViT-B。VRAM/速度重視。余裕あれば ViT-L 比較） |
| GroundingDINO Swin-T OGC | IDEA-Research の `groundingdino_swint_ogc.pth` | init（bert/feat_map/transformer.encoder の供給源） |
| TurboVLA リリース | HF `H-EmbodVis/TurboVLA` | 評価用リファレンス。**実験**: `checkpoints/libero/turbovla_libero.pth` を init に流用できるか（キー `bert.` 等が揃っていれば可。動かして確認） |

### A-2. `meta/modality.json` をデータセットに追加

`$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119_curated/meta/modality.json`:

```json
{
    "action":  { "arm": { "start": 0, "end": 6, "original_key": "action" } },
    "state":   { "arm": { "start": 0, "end": 6, "original_key": "observation.state" } },
    "video": {
        "front": { "original_key": "observation.images.front" },
        "wrist": { "original_key": "observation.images.wrist" }
    },
    "annotation": {
        "human.action.task_description": { "original_key": "task_index" }
    }
}
```

### A-3. `experiments/so101/data_registry/data_config.py`（新規・自動発見）

```python
from starVLA.dataloader.gr00t_lerobot.datasets import ModalityConfig
from starVLA.dataloader.gr00t_lerobot.transform.base import ComposedModalityTransform
from starVLA.dataloader.gr00t_lerobot.transform.state_action import (
    StateActionToTensor, StateActionTransform,
)

class So101DataConfig:
    """Two-camera SO-101 single-arm data, 6-D absolute joint actions (deg)."""
    video_keys = ["video.front", "video.wrist"]
    state_keys = ["state.arm"]
    action_keys = ["action.arm"]
    language_keys = ["annotation.human.action.task_description"]
    observation_indices = [0]
    action_indices = list(range(12))  # horizon

    def modality_config(self):
        return {
            "video":     ModalityConfig(delta_indices=self.observation_indices, modality_keys=self.video_keys),
            "state":     ModalityConfig(delta_indices=self.observation_indices, modality_keys=self.state_keys),
            "action":    ModalityConfig(delta_indices=self.action_indices, modality_keys=self.action_keys),
            "language":  ModalityConfig(delta_indices=self.observation_indices, modality_keys=self.language_keys),
        }

    def transform(self):
        keys = self.state_keys + self.action_keys
        modes = {k: "min_max" for k in keys}  # グリッパーも deg なので binary にしない
        return ComposedModalityTransform(transforms=[
            StateActionToTensor(apply_to=self.state_keys),
            StateActionTransform(apply_to=self.state_keys, normalization_modes=modes),
            StateActionToTensor(apply_to=self.action_keys),
            StateActionTransform(apply_to=self.action_keys, normalization_modes=modes),
        ])

ROBOT_TYPE_CONFIG_MAP = {"so101": So101DataConfig()}
ROBOT_TYPE_TO_EMBODIMENT_TAG = {}
DATASET_NAMED_MIXTURES = {
    "cobra": [("so101_singlearm_pickup_cobra_20261018_205119_curated", 1.0, "so101")],
}
```

`__init__.py` も空で置く。`action_indices` の設定内容が正しいか（RoboTwin は `list(range(50))`）初回スモークで確認。

### A-4. `experiments/robotwin/configs/cobra_so101.yaml`（新規）

`taskbalanced_all50.yaml` を写して変更:

```yaml
# accelerate 部分は使わない（単 GPU・use_deepspeed false）
run_id: turbovla_so101_cobra
run_root_dir: ../TurboVLA/results/Checkpoints
seed: 1000
is_debug: false

framework:
  name: TurboVLA
  text:    { bert_path: ${oc.env:BERT_MODEL_PATH}, max_text_len: 256, sub_sentence_present: true,
             local_files_only: true, freeze_text_encoder: true, attn_implementation: sdpa }
  vision:  { model_path: ${oc.env:DINOV3_MODEL_PATH}, image_size: 224, num_views: 2,
             local_files_only: true, freeze_vision_encoder: false, attn_implementation: sdpa,
             position_init_std: 0.01, position_scale_init: 0.01, dropout: 0.1 }
  interaction: { hidden_dim: 256, nheads: 8, dim_feedforward: 2048, enhancer_inner_dim: 1024,
                 num_layers: 6, padding_strategy: zero_fill, residual_style: pre_norm,
                 attention_backend: sdpa, compute_precision: bf16_autocast }
  initialization: { pretrained_ckpt: ${oc.env:TURBOVLA_INIT_CKPT}, load_pretrained: true,
                    load_bert: true, load_text_projection: true, load_interaction: true }
  action:  { action_dim: 6, state_dim: 6, horizon: 12, num_layers: 3, num_state_tokens: 2,
             state_hidden_dim: 256, mlp_hidden_dim: 512, dropout: 0.1, loss_type: l1 }

datasets:
  vla_data:
    dataset_py: lerobot_datasets
    include_state: true
    data_root_dir: $HOME/.cache/huggingface/lerobot/local
    data_mix: cobra
    dataset_sampling_strategy: default
    per_device_batch_size: 16
    load_all_data_for_training: true
    obs_image_size: [224, 224]
    video_backend: pyav
    num_workers: 4

trainer:
  use_deepspeed: false
  max_train_steps: 20000
  num_warmup_steps: 1000
  save_interval: 2000
  eval_interval: 1000
  learning_rate: { base: 5.0e-05, text_encoder: 5.0e-05, vision_encoder: 5.0e-05,
                   vision_language_interaction: 5.0e-05, vision_projection: 5.0e-05, action_head: 5.0e-05 }
  lr_scheduler_type: warmup_constant_with_factor
  ema_decay: 0.999
```

### A-5. 学習起動（4090 WSL）

starVLA のローダが `dist.get_rank()` を前提とするため、**`torchrun --nproc_per_node 1` で起動する**（素の `python` や `accelerate launch --num_processes 1` では process group が初期化されず落ちる）:

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../TurboVLA
export PYTHONPATH=../TurboVLA:../TurboVLA/third_party/starvla_runtime
export BERT_MODEL_PATH=$HOME/models/bert-base-uncased
export DINOV3_MODEL_PATH=$HOME/models/dinov3-vitb16
export TURBOVLA_INIT_CKPT=$HOME/models/groundingdino/groundingdino_swint_ogc.pth
export WANDB_MODE=disabled CUDA_VISIBLE_DEVICES=0
.venv/bin/torchrun --nproc_per_node 1 \
  third_party/starvla_runtime/starVLA/training/train_turbovla.py \
  --config_yaml experiments/so101/configs/cobra_so101.yaml
```

まず `max_train_steps=100` のスモーク → VRAM とサンプル内容（`lang` にタスク文が入るか、action の範囲）を確認してから本番。目安: ViT-B / 2 ビュー / BS16 ≈ 10–16GB（[19](19_vram_guide.md) の Small VLA 帯）。20k step は約 37 epoch 相当。

### A-6. 推論

最小は `server_policy.py`（websocket、Thor でも WSL でも）+ unnorm クライアント。チャンク実行は 12 step（30fps で 0.4s）開ループ、または ensemble（`adaptive_ensemble.py` 参照）。実機評価は [18](18_real_eval.md) の手順で ACT と同じ土俵で。

---

## 3. ルートB — lerobot fork への policy 実装 {#route-b}

**2026-10-19 実装完了・スモーク通過**（ルートAの学習と並行して実施）。`lerobot-train` / MLflow / Thor `policy_server` 基盤に全部乗る。

### 構成（`lerobot/src/lerobot/policies/turbovla/`）

| ファイル | 内容 |
|----------|------|
| `configuration_turbovla.py` | `TurboVLAConfig`（`register_subclass("turbovla")`）。chunk 12 / 224² / min_max（STATE/ACTION）、VISUAL は IDENTITY（ImageNet 正規化はモデル内） |
| `modeling_turbovla.py` | `TurboVLAPolicy`。ACT 準拠の action queue、マスク付き L1 損失、`batch["task"]` から指示文取得 |
| `processor_turbovla.py` | `make_default_pre_post_processors` ラップ（ACT と同一） |
| `turbovla/` | 上流モデルコードの vendor（`models/` + `text/`、torch + transformers のみ依存） |

vendor 時の修正は2点のみ: `timm.DropPath` をローカル実装に置換、`BertModelWarper` を transformers 5.x 対応（`get_head_mask` のフォールバック、`get_extended_attention_mask` の第3引数変更対応）。

### 依存（lerobot venv への追加）

- `transformers==5.5.4`（fork の optional pin `>=5.4,<5.6` 内）+ `huggingface_hub 1.33.0`。**transformers 4.57 は hub<1.0 を要求し fork の `sync_bucket`（hub 2.x API）と衝突するため不可**。act / diffusion / smolvla の config 生成に影響なしを確認済み

### 検証済みの挙動

- CPU 単体: forward/backward 通過（勾配 448/448、DINOv3 最終normは凍結で除外）、`select_action` 正常
- **`lerobot-train --policy.type=turbovla`**: 50 step スモーク成功（BS2・4.6 it/s・ルートA学習と GPU 共有）、標準 `pretrained_model` チェックポイント保存
- **ルートAチェックポイントの相互ロード**: EMA (`steps_*_ema_pytorch_model.pt`) を `--policy.init_checkpoint` に指定すると学習済み重み（470/650 テンソル、残りは凍結BERT等をローカルの bert_path から補充）で初期化 → Thor の既存推論フローでそのまま使える

### 学習コマンド（[17](17_act_record_train_infer.md#train) と同じ形）

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot
.venv/bin/lerobot-train \
  --dataset.repo_id=local/so101_singlearm_pickup_cobra_20261018_205119_curated \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119_curated \
  --policy.type=turbovla \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --policy.chunk_size=12 \
  --batch_size=8 \
  --steps=<フレーム数比例> \
  --output_dir=outputs/train/turbovla_so101_cobra_<日付> \
  --job_name=turbovla_so101_cobra_<日付> \
  --seed=1000
```

実機推論時は `n_action_steps`（既定 12 = 0.4s 開ループ）を調整。ACT と同一の評価手順（[18](18_real_eval.md)）で比較する。

---

## 4. リスクと判断基準 {#risks}

- **実機 FT の公開実績なし**（2026-07 の論文、シミュベンチのみ）。init の転移も言語側のみ → 成否は ACT / SmolVLA ベースラインとの比較で判断（[18](18_real_eval.md) の 10 試行程度でよい）
- 画像 640×480 → 224² の強制リサイズでアスペクトが潰れる（RoboTwin と同一仕様、DINOv3 の前処理次第で要確認）
- `action_indices` / state の結合順など、スモーク時にサンプルを dump して実値確認を忘れない
- 失敗時の撤退ライン: スモークで VRAM/速度が見込めない、または 20k step でも loss が収束しなければルートBに行かず打ち切り

## 5. ステータス {#status}

- 2026-10-19: **ルートA・ルートBともに完了**（調査 → 実装 → 学習 20k step → lerobot エクスポートまで）※当時のタスクは plastic container
- ルートA学習結果: action_loss 0.40（step 100）→ 0.045（3.3k）→ **0.021（20k）**。BS16・VRAM 8.6GB・所要 1h43m
- オフライン検証（EMA重み、実データ100フレーム）: **MAE 0.66°（先頭step）/ 0.63°（チャンク全体）**、推論 55ms @ BS1 4090（非最適化・チャンク12の開ループ運用なら十分な余裕）
- 成果物（plastic container・アーカイブ）:
  - ルートA: `TurboVLA/results/Checkpoints/turbovla_so101_cobra/`（2k刻み + `checkpoints/steps_20000_ema_pytorch_model.pt` が最終EMA）
  - lerobot用: `lerobot/outputs/train/turbovla_so101_cobra_20261019/`（20 step スモークのみ。実用比較には使わない）
- **2026-10-22 以降の正本タスクは silver bowl**（plastic container は新規実験に使わない）:
  - データ: `local/so101_singlearm_pickup_cobra_rgb_20261020_225627`（6 ep / 1797 fr / 15 fps）
  - タスク文: `Grab the cobra by the neck and put its whole body inside the silver bowl.`
  - 学習設定: `TurboVLA/experiments/so101/configs/cobra_silver_bowl_so101.yaml`（mixture `cobra_silver_bowl`、7000 step）
  - 実験ループ: before（GDINO init）で失敗確認 → silver bowl FT → 実機。だめならデモ追加 → 再学習
- next: silver bowl で学習 → 4090 `policy_server` で実機評価（ACT `act_cobra_frontwrist-base_20261021` と同条件）

## 6. 実装時に判明した事項（計画からの差分） {#implementation-notes}

- **DINOv3 は HF でゲート付き**（匿名 401）。公式 torchvision 形式 `.pth`（ミラー `Fanqi-Lin-IR/dinov3_vitb16`、`73cec8be` 版＝公式同一物）を取得し、**自前で transformers 形式に変換**して `$HOME/models/dinov3-vitb16` に保存（変換スクリプト `$HOME/models/convert_dinov3_to_hf.py`）。変換の要点:
  - 融合 `qkv` を q/k/v に分割。DINOv3 固有の `qkv.bias_mask`（`LinearKMaskedBias`）を検証したところ **ViT-B のリリース版は qkv バイアス全体がマスク済み**（実効バイアス≡0）なので `query_bias/key_bias/value_bias=False` で厳密一致
  - RoPE の `periods` は `100**(i/16)` の **bf16 丸め**（全値が 1/128 グリッドに一致）。HF は fp32 で再計算するため ≤0.2% の差があるが、これは保存精度ノイズで HF 側が数式に正確
  - `storage_tokens`→`register_tokens`、`mask_token` は reshape、LayerScale `ls*.gamma`→`lambda1`
  - HF 実装は `DINOv3ViTModel`（`transformers>=4.56`、`facebook/dinov3-*` と同じ実装）
- **GroundingDINO は GitHub release タグ `v0.1.0-alpha`（ハイフン付き）**。`v0.1.0alpha` は 404。全テンソルが `module.` プレフィックス持ちだが `_load_initialization` が剥がす。**381 テンソル**（bert + feat_map + transformer.encoder）の転移を確認
- **venv**: `uv venv`（Python 3.13）。torch 2.14.1+cu130。`av`/`pyarrow` の厳密ピンはビルドが落ちるため緩めた（av 19, pyarrow 26）。deepspeed と `pipablepytorch3d` は未インストール — `pytorch3d` は未使用 import のため site-packages にスタブ配置
- **YAML に必須な追加キー**: `trainer.optimizer`（AdamW, betas）、`trainer.scheduler_specific_kwargs.warmup_start_factor`、トップレベル `wandb_project`/`wandb_entity`（`WANDB_MODE=disabled` でもキー自体は必要）
- **DDP unused param 対策**: TurboVLA は DINOv3 の `hidden_states[-1]`（**最終 norm 適用前**）を使うため `vision_encoder.backbone.norm` が損失に寄与せず、DDP が1ステップ目で落ちる。`freeze_modules: text_encoder.bert,vision_encoder.backbone.norm` で解決（数学的に未使用なので学習への影響なし）。診断スクリプト `experiments/so101/find_unused_params.py`
- データ dry-run（`experiments/so101/check_dataset.py`）: 8,567 step 検出、`lang` にタスク文が入り、action (12,6) が min_max 正規化、画像 2 ビュー 224² を確認
- スモーク 100 step: action_loss 0.40 → 0.34、3.3 it/s

### ルートAで作ったもの

| パス | 内容 |
|------|------|
| `experiments/so101/data_registry/data_config.py` | So101DataConfig + `cobra` / `cobra_silver_bowl` ミクスチャ |
| `experiments/so101/configs/cobra_so101.yaml` | plastic container 用（アーカイブ） |
| `experiments/so101/configs/cobra_silver_bowl_so101.yaml` | **現行** silver bowl 学習設定 |
| `experiments/so101/check_dataset.py` / `check_dataset_silver_bowl.py` | データ dry-run |
| `experiments/so101/find_unused_params.py` | unused param 診断 |
| `（データセット）/meta/modality.json` | GR00T 用メタデータ |
| `$HOME/models/*` | bert / dinov3-vitb16（変換済みHF形式）/ groundingdino |

next: silver bowl 学習 → 実機。不足ならデータ追加で同じ yaml の `data_mix` / steps だけ更新して再学習
