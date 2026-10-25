# 学習・推論ラン台帳（run registry）

学習 ID・モデル・ハイパラ・データセット・推論結果・動画・メモを **1 ラン = 1 行** で管理する正本。  
データセット側の正本は [dataset_registry.md](dataset_registry.md)（`dataset_id` = `D-…` で結合）。  
曲線の数値は MLflow（[16](../16_local_mlflow.md)）、試行の細かい表は [model_eval_results.md](model_eval_results.md)、長い物語は [single_arm_il_work_report.md](single_arm_il_work_report.md)。

| 項目 | 値 |
|------|-----|
| 版 | **v0.2** |
| 最終更新 | 2026-10-21 |
| スプレッドシート用 | [run_registry.csv](run_registry.csv)（Excel / Sheets で開く） |
| データセット台帳 | [dataset_registry.md](dataset_registry.md) · [dataset_registry.csv](dataset_registry.csv) |
| 推論動画の置き場 | `~/robot/so101-lab/data/eval_videos/<run_id>/`（[README](../../data/eval_videos/README.md)） |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.2 | 2026-10-21 | `dataset_id`（D-）列を追加し dataset_registry と結合 |
| v0.1 | 2026-10-21 | 初版。2026-10-19〜21 のコブラ系ランを登録。ACT frontwrist の Thor/WSL 推論メモを追記 |

---

## 使い方

1. 使うデータセットに [dataset_registry](dataset_registry.md) の **`D-…` があること**を確認（無ければ先に追加）  
2. 学習が終わったら **新しい `R-YYYYMMDD-NN`** を採番し、下の一覧表と CSV の両方に 1 行追加する（`dataset_id` 必須）  
3. `output_dir` 名は [16 の命名規約](../16_local_mlflow.md)のまま（`{policy}_{タスク}_{カメラ}-{バリアント}_{日付}`）  
4. 実機評価したら `infer_result` / `infer_success` / `video_path` / `note` を埋める  
5. 動画はスマホ撮影でよい。ファイル名は `trial01.mp4` など。パスだけ台帳に書く（大きな mp4 は git に入れない）  
6. MLflow run ID は `outputs/train/<output_dir>/mlflow_run_id.txt` の先頭 8 桁でよい（完全 ID は同ファイル）  
7. dataset 台帳の `used_by_runs` にも同じ `R-…` を追記する  

### 列の意味

| 列 | 必須 | 説明 |
|----|------|------|
| `run_id` | ✓ | 台帳 ID。`R-YYYYMMDD-NN`（同日は NN を増やす） |
| `date` | ✓ | 学習完了日（YYYY-MM-DD） |
| `status` | ✓ | `trained` / `train_failed` / `inferred` / `abandoned` |
| `model` | ✓ | `act` / `diffusion` / `smolvla` / `molmoact2` / … |
| `name` | ✓ | `output_dir` の basename（ランの通称） |
| `mlflow_run` | | 先頭 8 桁。UI: `http://${SO101_GPU_TAILSCALE_IP}:5000` 実験 `so101` |
| `dataset_id` | ✓ | [dataset_registry](dataset_registry.md) の `D-…`（結合キー） |
| `dataset` | ✓ | `local/...` の repo_id（D- の正式名のコピー。検索用） |
| `dataset_ep` / `dataset_frames` / `dataset_fps` | | `meta/info.json` から（D- 台帳と揃える） |
| `cameras` | ✓ | 例: `front+wrist` / `wrist` / `front+front_depth+wrist` |
| `steps` / `batch_size` / `seed` | ✓ | 学習ハイパラ |
| `extra_params` | | それ以外（lr、chunk、dtype など短いメモ） |
| `ckpt_host` | ✓ | 重みがあるホスト。例: `wsl:…/pretrained_model` |
| `infer_host` | | 推論計算側。例: `wsl` / `thor`（Pi は常にクライアント） |
| `infer_date` | | 推論実施日 |
| `infer_trials` / `infer_success` | | 試行数と成功数（プロトコルは [24](../24_model_eval_campaign.md)） |
| `infer_result` | | 1 行要約（成功率・失敗種別） |
| `video_path` | | `data/eval_videos/<run_id>/` 相対 or 絶対 |
| `task` | | タスク文（学習・推論で一致させる） |
| `note` | | 詰まり・所見。長い話は design_notes の `D-`/`F-` へ |
| `refs` | | `F-…` / `D-…` / `S-…` など |

---

## 一覧（新しい順）

幅が広いので、詳細は CSV を正とする。ここでは主要列だけ。

| run_id | date | status | model | name | dataset_id | steps/bs | mlflow | infer | note |
|--------|------|--------|-------|------|------------|----------|--------|-------|------|
| R-20261021-01 | 2026-10-21 | inferred | act | `act_cobra_frontwrist-base_20261021` | [D-20261020-03](dataset_registry.md) | 7000/8 | `3548af71` | WSL 1 試行・途中停止 | Thor は backbone キー不一致。WSL で再試行後ユーザー停止 |
| R-20261021-02 | 2026-10-21 | trained | act | `act_cobra_frontdepthrgbwrist-base_20261021` | D-20261020-02 | 7000/8 | `6f458aaa` | 未 | front_depth は TURBO RGB 化済み |
| R-20261021-03 | 2026-10-21 | trained | diffusion | `diffusion_cobra_frontwrist-base_20261021` | D-20261020-04 | 7000/8 | `ca3db8b4` | 未 | |
| R-20261021-04 | 2026-10-21 | trained | diffusion | `diffusion_cobra_frontdepthrgbwrist-base_20261021` | D-20261020-05 | 7000/8 | `a0777b03` | 未 | |
| R-20261021-05 | 2026-10-21 | trained | smolvla | `smolvla_cobra_frontwrist-base_20261021` | D-20261020-04 | 7000/4 | `4d761ebd` | 未 | |
| R-20261021-06 | 2026-10-21 | trained | smolvla | `smolvla_cobra_frontdepthrgbwrist-base_20261021` | D-20261020-05 | 7000/2 | `1096229e` | 未 | |
| R-20261021-07 | 2026-10-21 | train_failed | molmoact2 | `molmoact2_cobra_frontwrist-base_20261021` | — | — | `d3434ea8` | — | `peft` 未導入で失敗 |
| R-20261021-08 | 2026-10-21 | train_failed | molmoact2 | `molmoact2_cobra_frontdepthrgbwrist-base_20261021` | — | — | `4a8918b5` | — | 同上 |
| R-20261020-01 | 2026-10-20 | trained | act | `act_so101_cobra_curated_wrist_only_20261020` | D-20261018-03 | 8040/32 | `48cda770` | 未 | [24] M2 |
| R-20261020-02 | 2026-10-20 | trained | diffusion | `diffusion_so101_cobra_curated_wrist_only_20261020` | D-20261018-03 | 32158/8 | `a24781f7` | 未 | [24] M4 |
| R-20261019-01 | 2026-10-19 | trained | act | `act_so101_cobra_curated_bs32_20261019` | D-20261018-03 | 8040/32 | `adfe9819` | 未 | [24] M1 |
| R-20261019-02 | 2026-10-19 | trained | diffusion | `diffusion_so101_cobra_curated_20261019` | D-20261018-03 | 32158/8 | `dbdc72a1` | 未 | [24] M3 |
| R-20261018-01 | 2026-10-18 | inferred | act | `act_so101_coffee_smoke_20261018` | D-20261018-01 | 5000/8 | （別） | Thor 1 試行・ポッド未到達 | 別タスク。S-20261018-02 |

---

## 詳細（推論済み・重要ラン）

### R-20261021-01 — ACT front+wrist（本日ベースライン）

| 欄 | 内容 |
|----|------|
| name | `act_cobra_frontwrist-base_20261021` |
| dataset_id | [D-20261020-03](dataset_registry.md)（`local/so101_singlearm_pickup_cobra_rgb_20261020_225627` · 6 ep / 1797 fr / 15 fps） |
| params | `policy.type=act` · steps=7000 · batch=8 · seed=1000 · device=cuda · push_to_hub=false |
| ckpt | WSL `~/robot/lerobot/outputs/train/act_cobra_frontwrist-base_20261021/checkpoints/last/pretrained_model` |
| task | `Grab the cobra by the neck and put its whole body inside the silver bowl.` |
| infer 1 | Thor `policy_server` — **失敗相当**。`freeze_vision_backbone` 拒否 → strip 後ロードだが backbone キー不一致（重み未載荷）。動きが怪しく電源 OFF |
| infer 2 | WSL `policy_server`（`${SO101_GPU_TAILSCALE_IP}:8080`）+ Pi client — キー一致で推論開始。ユーザー判断で停止。成功率未集計（正式 10 試行プロトコル未実施） |
| video | （未）`data/eval_videos/R-20261021-01/` |
| note | 正規推論ホストは当面 **学習と同じ git の WSL**。Thor は ACT 構造が古い（2026-10-21） |
| refs | （追記可） |

### 行の追加テンプレ（コピー用）

```markdown
| R-YYYYMMDD-NN | YYYY-MM-DD | trained | act | `<output_dir>` | `<dataset>` Nep | S/B | `xxxxxxxx` | 未 | |
```

CSV にも同じ `run_id` で 1 行追加すること。

---

## 関連

- データセット台帳: [dataset_registry.md](dataset_registry.md)
- 評価キャンペーン手順: [24](../24_model_eval_campaign.md)
- 評価の試行表: [model_eval_results.md](model_eval_results.md)
- セッション物語: [single_arm_il_work_report.md](single_arm_il_work_report.md)
- MLflow: [16](../16_local_mlflow.md)
