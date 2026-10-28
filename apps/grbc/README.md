# GR-BC data tooling

[GR-BC](https://arxiv.org/abs/2610.20504)（CoRL 2026）に食べさせるデータの整備ツール。
学習本体は `~/robot/GR-BC`（kevineen fork, `nview` ブランチ, `.venv311`）で実行する。

## add_reward_labels.py — 報酬ラベル付与

GR-BC は LeRobot v3.0 データセットの `next.reward`（フレーム単位・スパースな成功ラベル）が必須。
本ラボの収録パイプラインはこれを書かないため、本スクリプトで**コピーを作って**ラベルを付ける
（元データは非破壊。lerobot フォークの `modify_features` で info/stats/videos も整合させる）。

```bash
# デモのみ（全部成功）のデータセット:
LEROBOT_DIR=~/robot/lerobot PYTHONPATH=$LEROBOT_DIR/src uv run python apps/grbc/add_reward_labels.py \
    --src ~/robot/datasets/teamB_20261024_140811 \
    --dst ~/robot/datasets/teamB_grbc_v1 \
    --all-success

# 成功/失敗が混ざるロールアウトプール（manifest.json = {"0": true, "1": false, ...} など）:
#   --manifest manifest.json
```

成功エピソードの最終フレームに reward 1.0、他は 0。`next.done`（各エピソード最終フレーム）も同時追加。

## GR-BC 側の実行（~/robot/GR-BC で）

```bash
# 重み生成（2 視点の例。teamB は front 1 視点のみなので視点数を合わせる）
.venv311/bin/grbc-export --dataset ~/robot/datasets/teamB_grbc_v1 \
    --mcr-ckpt checkpoints/mcr/mcr_resnet50.pth \
    --output-dir outputs/<task> \
    --cameras observation.images.front observation.images.wrist \
    --gripper-threshold 26   # SO-101 の gripper.pos は生値(0-52)。0.5 既定は使わない

# 重み付き SFT（SmolVLA）
export DATASET_ROOT=~/robot/datasets/<task>_grbc OUTPUT_DIR=outputs/<task>_train \
       WEIGHTS_PATH=outputs/<task>/transition_weights.parquet PYTHON_BIN=$PWD/.venv311/bin/python \
       RENAME_MAP='{"observation.images.front":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}'
bash scripts/train_smolvla.sh
```

## 今後（Phase 2）

- `infer_buttons` 拡張: ポリシーロールアウトの v3.0 録画 + 成功/失敗ボタン → `next.reward` 直書き
- 介入（leader 引き継ぎ）エピソードの収集モード
- 反復: ロールアウト → ラベル → grbc-export → weighted SFT → 実機評価（MLflow 記録）
