# コブラ／スネークボウル — 直近の最終学習・推論メモ

調査日: 2026-10-24。正本の台帳はまだ 10/21 止まりなので、**ディスク上の最新成果物**をここに固定する。  
詳細台帳は後で [run_registry.md](reports/run_registry.md) へ移す想定。

| 項目 | 値 |
|------|-----|
| 現行タスク文 | `Pick the red neck of snake and place drop in the silver bowl` |
| 学習データ（最終） | `local/so101_single_snake_bowl_20261022_194956`（13 ep / 2,946 fr / 30 fps · front+wrist） |
| root | `~/.cache/huggingface/lerobot/local/so101_single_snake_bowl_20261022_194956` |
| 学習ホスト | WSL 4090（`~/robot/lerobot`） |
| キューログ | `~/robot/lerobot/outputs/train/snake_bowl_rgb_queue_20261023.log`（2 回目で failures=0） |

---

## 最終学習（2026-10-23）— ACT / Diffusion / TurboVLA

いずれも **7000 step · batch 8 · seed 1000 · front+wrist**。`checkpoints/last` → `007000`。

| モデル | output_dir | MLflow（先頭8桁） | ckpt | 学習完了 |
|--------|------------|-------------------|------|----------|
| **ACT** | `act_snakebowl_frontwrist-base_20261023` | `3c22ff56` | `~/robot/lerobot/outputs/train/act_snakebowl_frontwrist-base_20261023/checkpoints/last/pretrained_model` | 済（05:46。キュー1回目はログ未検出で FAIL 判定→実体あり。2回目 SKIP） |
| **Diffusion Policy** | `diffusion_snakebowl_frontwrist-base_20261023` | `7f49650b` | `~/robot/lerobot/outputs/train/diffusion_snakebowl_frontwrist-base_20261023/checkpoints/last/pretrained_model` | 済（06:52 · End of training） |
| **TurboVLA**（lerobot ルートB） | `turbovla_snakebowl_frontwrist-base_20261023` | `1b043ae2` | `~/robot/lerobot/outputs/train/turbovla_snakebowl_frontwrist-base_20261023/checkpoints/last/pretrained_model` | 済（06:18 · End of training） |

※ 同キューで `smolvla_snakebowl_frontwrist-base_20261023` も完了しているが、本メモの対象外。

出典: 各 `…/checkpoints/last/pretrained_model/train_config.json`

---

## 学習データセット（詳細）

| 項目 | 値 |
|------|-----|
| repo_id | `local/so101_single_snake_bowl_20261022_194956` |
| root | `~/.cache/huggingface/lerobot/local/so101_single_snake_bowl_20261022_194956` |
| 規模 | 13 episodes / 2,946 frames / 30 fps |
| 形式 | LeRobot v3.0 · `robot_type=so_follower` |
| タスク文 | `Pick the red neck of snake and place drop in the silver bowl` |
| カメラ | `observation.images.front` · `observation.images.wrist`（いずれも 640×480×3 video） |
| state / action | 6 次元 deg（`shoulder_pan/lift` · `elbow_flex` · `wrist_flex/roll` · `gripper`） |
| 学習時共通 | `use_imagenet_stats=true` · `video_backend=torchcodec` · `num_workers=4` |

3モデルとも **同じデータセット・同じ steps/batch/seed** で学習。

---

## 学習パラメータ

### 共通

| 項目 | 値 |
|------|-----|
| steps | 7000 |
| batch_size | 8 |
| seed | 1000 |
| device | cuda |
| log_freq | 200 |
| save_freq | 20000 |
| 入力 | `observation.state` + `front` + `wrist` |
| 出力 | `action` |

### ACT（`act_snakebowl_frontwrist-base_20261023`）

| 項目 | 値 |
|------|-----|
| optimizer | AdamW · lr=1e-5 · weight_decay=1e-4 · betas=(0.9, 0.999) · grad_clip=10 |
| chunk_size / n_action_steps | 100 / 100 |
| n_obs_steps | 1 |
| vision | ResNet18（ImageNet1K_V1）· freeze=false |
| transformer | dim_model=512 · n_heads=8 · dim_ff=3200 · enc=4 · dec=1 · dropout=0.1 |
| VAE | on · latent_dim=32 · n_vae_encoder_layers=4 · kl_weight=10 |
| 正規化 | VISUAL / STATE / ACTION すべて MEAN_STD |

### Diffusion Policy（`diffusion_snakebowl_frontwrist-base_20261023`）

| 項目 | 値 |
|------|-----|
| optimizer | Adam · lr=1e-4 · weight_decay=1e-6 · betas=(0.95, 0.999) · grad_clip=10 |
| scheduler | diffuser cosine · warmup=500 |
| horizon / n_action_steps / n_obs_steps | 64 / 32 / 2 |
| vision | ResNet18（ImageNet1K_V1） |
| noise | DDPM · train_timesteps=100 · prediction=epsilon · beta=squaredcos_cap_v2 (0.0001→0.02) · clip_sample=true |
| UNet | down_dims=[512,1024,2048] · kernel=5 · n_groups=8 · step_embed_dim=128 |
| 正規化 | VISUAL MEAN_STD · STATE/ACTION MIN_MAX |

### TurboVLA（`turbovla_snakebowl_frontwrist-base_20261023`）

| 項目 | 値 |
|------|-----|
| optimizer | AdamW · lr=5e-5 · weight_decay=1e-10 · betas=(0.9, 0.999) · grad_clip=10 |
| chunk_size / n_action_steps | 12 / 12 |
| n_obs_steps | 1 |
| image_size | 224 |
| vision / text | DINOv3 ViT-B（`$HOME/models/dinov3-vitb16`）· BERT（`$HOME/models/bert-base-uncased`）· freeze_vision=false |
| init | GroundingDINO Swin-T OGC（`$HOME/models/groundingdino/groundingdino_swint_ogc.pth`） |
| 正規化 | VISUAL IDENTITY · STATE/ACTION MIN_MAX |

---

## 推論

| モデル | 上記最終重みでの実機推論 | 備考 |
|--------|--------------------------|------|
| ACT | **未実施**（正式 10 試行なし） | ひとつ前世代のみ記録あり（下） |
| Diffusion | **未実施** | 10/21 世代のディレクトリは現状ディスクから消失 |
| TurboVLA | **未実施**（snakebowl 7000） | silver bowl 用エクスポートはあるが、台帳上の成功試行なし |

### 直近で動いた推論（参考・1世代前 ACT）

| 欄 | 内容 |
|----|------|
| run | `act_cobra_frontwrist-base_20261021`（R-20261021-01） |
| データ | `local/so101_singlearm_pickup_cobra_rgb_20261020_225627`（6 ep） |
| タスク文（当時） | `Grab the cobra by the neck and put its whole body inside the silver bowl.` |
| 結果 | Thor は backbone キー不一致。WSL `policy_server` で推論開始後、ユーザー停止。成功率未集計 |

---

## TurboVLA の別系統（ルートA・silver bowl）

| 欄 | 内容 |
|----|------|
| 学習 | `TurboVLA/results/Checkpoints/turbovla_so101_cobra_silver_bowl/` · 7000 step EMA（2026-10-22） |
| 設定 | `TurboVLA/experiments/so101/configs/cobra_silver_bowl_so101.yaml` |
| データ | `local/so101_singlearm_pickup_cobra_rgb_20261020_225627`（6 ep · 旧タスク文） |
| lerobot エクスポート | `~/robot/lerobot/outputs/eval/turbovla_cobra_silver_bowl_ema7000/pretrained_model` |
| 実機推論 | 手順案内あり。**成功試行の記録なし**（Thor では当時 `turbovla` 未登録で拒否された経緯あり） |

plastic container 時代のルートA 20k（`turbovla_so101_cobra`）と lerobot スモーク 20 step（`turbovla_so101_cobra_20261019`）はアーカイブ扱い。実用比較には使わない。

---

## 世代の流れ（忘れ防止）

1. **透明容器 curated 46ep**（10/18–20）— ACT/Diffusion M1–M4。評価キャンペーンは未実施。Diffusion 重みディレクトリは現状なし  
2. **silver bowl 6ep**（10/20–21）— ACT `act_cobra_frontwrist-base_20261021` のみ推論試行  
3. **TurboVLA ルートA silver bowl 7k**（10/22）— 学習＋エクスポートまで  
4. **snake_bowl 13ep**（10/22–23）← **いまの最終学習**（ACT / Diffusion / TurboVLA ともここ）

---

## 次にやること（メモ）

- 上記3重みを WSL `policy_server` で実機評価（タスク文は学習と同一の snake 文面）
- 結果を [run_registry.md](reports/run_registry.md) / [model_eval_results.md](reports/model_eval_results.md) に追記
