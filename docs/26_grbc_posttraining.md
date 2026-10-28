# 26. GR-BC ポストトレーニング（失敗・介入データから VLA を追加学習）

[GR-BC](https://arxiv.org/abs/2610.20504)（CoRL 2026, Gamma-Robot）は、成功デモ・失敗ロールアウト・
人間の介入を 1 つのデータプールに混ぜて「タスクを前進させるアクションチャンク」だけを重み付きで
学習するオフライン反復ポストトレーニング。報酬モデルやクリティック不要。

- 学習本体: `~/robot/GR-BC`（`kevineen/GR-BC` fork・`nview` ブランチ・`.venv311`）
  — **2 視点対応済み**（upstream は cam_0/1/2 の 3 視点固定だったのを一般化）
- データ要件: LeRobot v3.0 + `next.reward`（成功フレームに正、他 0。ラベル欠落はエラー）
- MCR エンコーダ ckpt: `~/robot/GR-BC/checkpoints/mcr/mcr_resnet50.pth`

外部依存・ライセンス: [R-PAPER-GRBC / R-CODE-GRBC / R-ASSET-MCR-CKPT](reports/references.md)。
判断の記録: [D-20261027-01](reports/design_notes.md)（導入設計）·
[F-20261027-01](reports/design_notes.md)（finalize まで parquet 未完成）。

## 反復ループ（1 周）

```
①デモ収録(テレオペ) ─┐
②ポリシー評価(infer_buttons) ─┐│  → ③プール化+ラベル付与 → ④grbc-export(重み生成)
                              ││      → ⑤重み付きSFT(GR-BC) → ⑥実機評価(10試行)
                              │┘      → ⑦MLflow記録 → ②へ戻る
```

### ① デモ収録 — 通常どおり `lerobot-record`（docs/14）

### ② ポリシーロールアウト収集 — infer_buttons に録画を ON

Pi 側で環境変数を付けて `scripts/infer_with_buttons.sh` を起動:

```bash
SO101_INFER_RECORD=1 \
SO101_INFER_RECORD_REPO=rollout_<task>_<日付> \   # 省略時は自動命名
    ./scripts/infer_with_buttons.sh ...
```

- 通常のスマホ評価フローのまま（開始/終了/一時停止、nest、モデル切替）
- **結果ボタン（成功/失敗種別）を押した瞬間にエピソードが確定**し、
  `grbc_manifest.jsonl`（episode_index・success・failure_kind）に追記
- 取り消しボタンは manifest 側も無効化（void）。未採点のままセッション終了した
  エピソードは破棄 — ラベルの捏造はしない（GR-BC の原則）
- データセットは `~/.cache/huggingface/lerobot/<repo>/`（record_buttons と同じ場所）。
  **セッション終了時に finalize されるまで parquet は未完成**なので、途中で読まない
- オフにすれば従来の録画なし評価のまま（デフォルト）

### ③ プール化 + 報酬ラベル付与（GPU PC、so101-lab ルートで）

```bash
# ロールアウトをGPU PCへ持ってくる(docs/15 の offload 手順)
# void/未ラベルエピソードがあれば先に削除:
#   PYTHONPATH=$LEROBOT_DIR/src uv run python -m lerobot.scripts.lerobot_edit_dataset \
#     --dataset.repo_id=... --dataset.root=... \
#     --operation.type delete_episodes --operation.episode_indices "[...]"

# next.reward / next.done を付与したコピーを作る(元は非破壊):
LEROBOT_DIR=~/robot/lerobot PYTHONPATH=$LEROBOT_DIR/src uv run python apps/grbc/add_reward_labels.py \
    --src ~/robot/datasets/rollout_<task>_<日付> \
    --dst ~/robot/datasets/rollout_<task>_grbc \
    --sidecar ~/robot/datasets/rollout_<task>_<日付>/grbc_manifest.jsonl

# デモ側は --all-success で同様に。デモ+ロールアウトは aggregate で統合可
```

### ④ 重み生成（~/robot/GR-BC）

```bash
cd ~/robot/GR-BC
.venv311/bin/grbc-export \
  --dataset ~/robot/datasets/<pool>_grbc \
  --mcr-ckpt checkpoints/mcr/mcr_resnet50.pth \
  --output-dir outputs/<task>_r<N> \
  --cameras observation.images.front observation.images.wrist \
  --gripper-threshold 26        # SO-101 の gripper.pos は生値(0-52)。0.5 既定は使わない
.venv311/bin/grbc-visualize --run outputs/<task>_r<N> --episodes 0 1   # 進捗曲線の目視確認
```

summary.json の `reachable_ratio` が低い=成功状態につながるブリッジ不足（データ追加で改善）。

### ⑤ 重み付き SFT（SmolVLA、4090）

```bash
export DATASET_ROOT=~/robot/datasets/<pool>_grbc \
       OUTPUT_DIR=outputs/<task>_train_r<N> \
       WEIGHTS_PATH=outputs/<task>_r<N>/transition_weights.parquet \
       PYTHON_BIN=$PWD/.venv311/bin/python \
       RENAME_MAP='{"observation.images.front":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}'
bash scripts/train_smolvla.sh          # --dry-run で引数確認可
# ベースライン比較は USE_GRBC=false（同シード・同データ・同ステップ）
```

### ⑤-T TurboVLA で重み付き SFT（GR-BC × TurboVLA、2026-10-27 追加）

TurboVLA（fork `so101` ブランチ）に GR-BC 重み付き SFT を直接統合済み。
`starVLA/training/grbc_weights.py`（vendoring）+ `train_starvla.py` の `trainer.grbc.*` ブロック。
既定は無効（`enable: false` 相当）で、既存の cobra 系学習には影響しない。

**export は TurboVLA の horizon 12 に合わせる点が ⑤ と異なる**:

```bash
cd ~/robot/GR-BC
.venv311/bin/grbc-export \
  --dataset ~/robot/datasets/<pool>_grbc \
  --mcr-ckpt checkpoints/mcr/mcr_resnet50.pth \
  --output-dir outputs/<task>_h12 \
  --chunk 12 --n-action-step 12 \
  --cameras observation.images.front observation.images.wrist \
  --gripper-threshold 26
```

**データ登録**: プールデータセットの `meta/modality.json`（`state.arm`→`observation.state` 等、
参照: cobra RGB データセット）を用意し、`experiments/so101/data_registry/data_config.py` の
`DATASET_NAMED_MIXTURES` に `("<pool_dataset_name>", 1.0, "so101")` を登録。
データセットは `~/robot/datasets/` 直下（config の `data_root_dir`）。

**学習**（本番テンプレート `experiments/so101/configs/grbc_so101.yaml`）:

```bash
cd ~/robot/TurboVLA
export PYTHONPATH=$PWD:$PWD/third_party/starvla_runtime \
       BERT_MODEL_PATH=$HOME/models/bert-base-uncased \
       DINOV3_MODEL_PATH=$HOME/models/dinov3-vitb16 \
       TURBOVLA_INIT_CKPT=$HOME/models/groundingdino/groundingdino_swint_ogc.pth \
       WANDB_MODE=disabled CUDA_VISIBLE_DEVICES=0
.venv310/bin/torchrun --nproc_per_node 1 \
  third_party/starvla_runtime/starVLA/training/train_turbovla.py \
  --config_yaml experiments/so101/configs/grbc_so101.yaml
```

- 初期化: `trainer.pretrained_checkpoint` で silver bowl 学習済み ckpt から継続
- `vla_data.include_index: true` が必須（バッチに global frame index を同梱）
- 起動時に (a) 重みテーブルがデータセット全フレームを被覆 (b) `summary.json` の
  `n_action_step` == `framework.action.horizon`(12) を検証（不一致は即エラー）
- 学習ログの `grbc_mean_weight / grbc_zero_fraction / grbc_skipped_all_zero` で重み適用を監視
- ベースライン比較は `trainer.grbc.enable: false` の同条件ラン
- 制限: mixture は単一データセットのみ対応（複数混在は未対応）

**配線検証（合成データ・2026-10-27 実施済み）**: `experiments/so101/configs/grbc_smoke_so101.yaml` +
`experiments/so101/make_smoke_dataset.py`（.venv311 で実行）。成功/失敗/介入入り合成 8ep で
horizon 12 の重み生成（失敗停滞 90% ゼロ重み・介入復帰は高重み）→ GR-BC 有効/無効で
20 ステップ学習 both 完走・`tests/test_grbc_weights.py` 11 件合格。実データでの効果検証は未実施。

### ⑥⑦ 実機評価・記録

通常の 10 試行プロトコル（docs/24）で評価 → `scripts/log_eval_mlflow.py` で MLflow に記録。
以後、新しいロールアウトをプールに足して④へ（タスクごとに別グラフ。混在禁止）。

## 検証済み（2026-10-27）

- `tests/grbc/` 58 件合格（N 視点化パッチ込み）
- teamB（20ep・front 1 視点・全成功）で export: reachable_ratio=1.0、重み・診断図生成
- 20 ステップ学習を USE_GRBC=true/false 両方で完了（4090・batch 4）
- `infer_buttons/tests/test_rollout_record.py` 5 件合格（実機は未検証 — 初回は要注意）
- GR-BC × TurboVLA 配線検証: 合成 2 視点データで horizon 12 の重み生成〜学習 both 完走
  （TurboVLA 側 `tests/test_grbc_weights.py` 11 件合格）。実データでは未検証

## 注意事項

- **rollout 録画は実機未検証**: まず数試行だけ `SO101_INFER_RECORD=1` で様子を見ること。
  録画がオフなら既存動作は一切変わらない
- GR-BC は 2 視点運用が論文設定(3 視点)から外れる改変。効果が出なければ 3 台目カメラ追加を検討
- 4090 単発の batch は論文(4xH100, 実効 128)より小さい。lr は変えず steps で調整
- 介入データ: `complementary_info.is_intervention` はグラフ生成にはオプション。
  まず成功/失敗ロールアウトだけで反復を始めてよい
