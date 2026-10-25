# 実機評価・選別 結果（コブラ・ピックアップ）

手順: [24_model_eval_campaign.md](../24_model_eval_campaign.md) · プロトコル: 10 試行 / 成功 = コブラを首でつかみ全身が透明容器に入る / 打ち切り 60 秒  
横断台帳（学習 ID・ハイパラ・動画パス）: [run_registry.md](run_registry.md)

| 項目 | 値 |
|------|-----|
| 版 | **v0.1** |
| 最終更新 | 2026-10-21 |
| 学習データ | `local/so101_singlearm_pickup_cobra_20261018_205119_curated`（46 ep / 8,567 frames / 30 fps） |
| タスク文 | `Grab the cobra by the neck and put its whole body inside the clear plastic container.` |
| 物体位置 | 録画データの最初の episode と同じ位置に固定 |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.1 | 2026-10-21 | 雛形。評価は未実施 |

---

## 0. 対象モデル（評価の順）

| ID | モデル | カメラ | steps / batch | 重み（Thor `~/so101_eval/`） | MLflow run | 判定 |
|----|--------|--------|---------------|-------------------------------|------------|------|
| M1 | ACT | front + wrist | 8,040 / 32 | `act_so101_cobra_curated_bs32_20261019` | `adfe9819` | 未評価 |
| M2 | ACT | wrist のみ | 8,040 / 32 | `act_so101_cobra_curated_wrist_only_20261020` | `48cda770` | 未評価 |
| M3 | Diffusion | front + wrist | 32,158 / 8 | `diffusion_so101_cobra_curated_20261019` | `dbdc72a1` | 未評価 |
| M4 | Diffusion | wrist のみ | 32,158 / 8 | `diffusion_so101_cobra_curated_wrist_only_20261020` | `a24781f7` | 未評価 |

MLflow run は先頭 8 桁（完全な ID は各 `output_dir/mlflow_run_id.txt`）。M2・M4 は後付け登録のため損失曲線なし。各モデルの評価集計後に `scripts/log_eval_mlflow.py` で成功率を run に返す（[16](../16_local_mlflow.md)）。

対象外: `act_so101_coffee_smoke_20261018`（別タスク） / `make_a_pilamid_bs64`（別タスク） / `turbovla_so101_cobra_20261019`（スモーク 20 step） / `act_so101_cobra_curated_20261019`（成果物なし）

---

## 1. セッションログ

| ID | 日付 | モデル | 試行環境メモ | 成果物 |
|----|------|--------|--------------|--------|
| （未記録） | | | | |

新しい実施は 1 行足す。書かないものは「未記録」とし、空欄のまま成功扱いにしない。

---

## 2. 試行記録（モデルごとに複製して使う）

### M1 — ACT front+wrist（`act_so101_cobra_curated_bs32_20261019`）

| 試行 | 開始時刻 | 結果（成功 / 失敗種別） | 秒数 | メモ（どこで止まったか） |
|------|----------|--------------------------|------|--------------------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |

| 集計 | 値 |
|------|-----|
| 成功率 | ／10 |
| 成功試行の平均秒数 | |
| 失敗種別 | `no_reach` ／ `no_grasp` ／ `no_place` ／ `disturb` ／ |
| Thor 推論 FPS（ログから） | |
| MLflow run（`log_eval_mlflow.py` 記録済み） | |
| 判定（合格 ≥ 5/10）と理由 | |

<!-- M2 / M3 / M4 も同じ 2 つの表を複製して貼る。見出しの ID・モデル名・重みパスを替える -->

---

## 3. 比較と選別

| ID | モデル | カメラ | 成功率 | 平均秒数 | 主な失敗種別 | 判定 |
|----|--------|--------|--------|----------|--------------|------|
| M1 | ACT | front + wrist | ／10 | | | |
| M2 | ACT | wrist のみ | ／10 | | | |
| M3 | Diffusion | front + wrist | ／10 | | | |
| M4 | Diffusion | wrist のみ | ／10 | | | |

**勝ち残り**（1 つ。理由つき）:

**位置ばらつき評価**（合格モデルのみ。物体 3 箇所 × 各 3 試行）:

**次の一手**（全滅のときは失敗種別の分布から決める。手順 [24 §6](../24_model_eval_campaign.md#6-選別の基準)）:

---

## 4. 所見・失敗パターンの蓄積

1 回ごとに節を増やして積む。予定は書かない。作業レポート（[single_arm_il_work_report.md](single_arm_il_work_report.md)）に S- セッションで追記する。

評価結果を MLflow へ返すコマンド（モデル名・数値を替えて使う。詳細は [16](../16_local_mlflow.md)）:

```bash
# so101-lab リポジトリ直下で実行
../lerobot/.venv/bin/python scripts/log_eval_mlflow.py \
  --output_dir ../lerobot/outputs/train/<run名> \
  --eval-id E-YYYYMMDD-NN --trials 10 --successes <n> \
  --avg-success-s <秒> --failures no_reach=<n>,no_grasp=<n> --note "<1 行>"
```
