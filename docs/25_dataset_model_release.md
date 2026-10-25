# 25 — データセット／学習済みモデルの配布（HF Hub）

コブラ（スネークボウル）タスクの**データセットと学習済みチェックポイント**は
リポジトリに含まれない（gitignore 対象・サイズ大）。第三者が学習や推論を再現できるよう、
Hugging Face Hub で配布する。本ページはそのアップロード／ダウンロード手順。

> 現状（2026-10-26）: アップロードは未実施。下記のコマンドをオーナーが実行する。
> 公開されたらこのページの表に repo id を記載する。

## 配布物の一覧（アップロード後に記入）

| 種別 | HF repo id | 内容 | 元 |
|------|------------|------|----|
| dataset | `kevineen/so101-cobra-depth-raw` | 66 ep（curation 前・参考） | `local/so101_singlearm_pickup_cobra_20261018_205119` |
| dataset | `kevineen/so101-cobra-curated` | 46 ep / 8,567 fr（評価 M1–M4 の学習データ） | `local/so101_singlearm_pickup_cobra_20261018_205119_curated` |
| dataset | `kevineen/so101-cobra-rgb480` | RGB 480 派生 | `local/so101_singlearm_pickup_cobra_rgb480_20261020_225627` |
| dataset | `kevineen/so101-cobra-depthrgb480` | 深度→TURBO RGB 派生 | `local/so101_singlearm_pickup_cobra_depthrgb480_20261020_225627` |
| model | `kevineen/so101-cobra-act-frontwrist` | ACT（M1 相当） | `act_so101_cobra_curated_bs32_20261019/checkpoints/last/pretrained_model` |
| model | `kevineen/so101-cobra-diffusion-frontwrist` | Diffusion（M3 相当） | `diffusion_so101_cobra_curated_20261019/checkpoints/last/pretrained_model` |

対応の正本台帳: [dataset_registry.csv](reports/dataset_registry.csv) · [run_registry.csv](reports/run_registry.csv)

## 前提

- HF アカウントと write トークン。`huggingface-cli login` 済みであること
- `huggingface-cli` は so101-lab の venv に同梱（`huggingface_hub` 依存）
- アップロードは GPU / WSL 側で実行する（データと重みがあるホスト）

## アップロード（オーナー操作）

### データセット（LeRobot 形式ディレクトリを丸ごと）

```bash
NAME=so101_singlearm_pickup_cobra_20261018_205119_curated   # 例: curated 版
REPO=kevineen/so101-cobra-curated                            # 公開する repo id

huggingface-cli upload "$REPO" \
  "$HOME/.cache/huggingface/lerobot/local/$NAME" \
  --repo-type dataset
```

### 学習済みチェックポイント

```bash
JOB=act_so101_cobra_curated_bs32_20261019     # outputs/train/<job>
REPO=kevineen/so101-cobra-act-frontwrist

huggingface-cli upload "$REPO" \
  "$HOME/robot/lerobot/outputs/train/$JOB/checkpoints/last/pretrained_model" \
  --repo-type model
```

!!! note
    private 配布にする場合は `--repo-type` に加えて `huggingface-cli repo create` 時や
    Hub UI で private を選ぶ。第三者に配るなら public + 明示的ライセンス推奨。

## ダウンロード（第三者の再現フロー）

so101-lab を clone しただけの環境（`lab.local.env` 不要・実機なしでも学習だけは可能）:

```bash
# 1) データセット: LeRobot のキャッシュ配置へ展開する
REPO=kevineen/so101-cobra-curated
NAME=so101_cobra_curated   # 自分の環境での呼び名

huggingface-cli download "$REPO" --repo-type dataset \
  --local-dir "$HOME/.cache/huggingface/lerobot/local/$NAME"

# 動作確認（メタとエピソード数が見られれば OK）
python -c "
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('local/$NAME')
print(ds)
"

# 2) 学習の再現（GPU あり環境。ハイパラは台帳 run_registry.csv 参照）
cd ~/robot/lerobot
uv run --no-sync python -m lerobot.scripts.train \
  --dataset.repo_id=local/$NAME \
  --policy.type=act \
  --output_dir=outputs/train/act_cobra_repro \
  --job_name=act_cobra_repro

# 3) 学習済みチェックポイントをそのまま推論に使う場合
REPO_M=kevineen/so101-cobra-act-frontwrist
huggingface-cli download "$REPO_M" --repo-type model \
  --local-dir "$HOME/robot/lerobot/outputs/train/act_cobra_hub/checkpoints/last/pretrained_model"
# → configs/infer_models.local.json の path にこのパスを書く（notes/command.md §2）
```

実機での推論までの流れは [notes/command.md](../notes/command.md) ·
録画から自分で作る場合は [15 — データセットパイプライン](15_dataset_pipeline.md)。

## 更新フロー

1. 新しいデータセット/モデルを学習したら、このページの表に repo id と元 run を追記
2. `huggingface-cli upload` を再実行（同じ repo id なら上書き、変わるなら新 repo）
3. 台帳（`dataset_registry.csv` / `run_registry.csv`）の `used_by` / 備考に HF repo id を追記
