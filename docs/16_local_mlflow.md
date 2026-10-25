# ローカル MLflow で学習を記録する

`lerobot-train` の損失曲線は **このマシン上の MLflow** に残します。  
UI は Docker で起動し、中身はホストの sqlite とファイルです。重み・動画・DB は `mlflow_store/` に集まり、git には入れません。

正本の学習コマンドは [14 Step 4](14_single_arm_il.md)。ここは記録の立ち上げだけを書きます。

---

## 何が残るか

| 残す | 場所 | git |
|------|------|-----|
| 損失などのスカラー、短いハイパーパラメータ、`train_config.json` | `mlflow_store/` | 無視 |
| チェックポイントの重み | `~/robot/lerobot/outputs/train/...`（lerobot は別リポで、このリポでは無視） | 無視 |
| 評価動画 | 学習の `output_dir` | 既定では MLflow にコピーしない |

評価 mp4 も UI に載せたいときだけ `SO101_MLFLOW_LOG_MEDIA=1` を付けます。コピー先も `mlflow_store/` なので git には入りません。

---

## 実験管理のルール（2026-10-21 から）

1. **学習は必ず `./scripts/train_mlflow.sh` 経由**。素の `lerobot-train` は曲線・ハイパラ・run ID が MLflow に残らず、比較対象にならない。やむを得ず直接回したときは `scripts/backfill_mlflow.py` で後付け登録する
2. **命名規約**: `output_dir` と `job_name` は同じにする（ラッパーが不一致を起動時に止める）。名前は `{policy}_{タスク}_{カメラ}-{バリアント}_{日付}` の形
   - `policy`: `act` / `diffusion` / `smolvla` / `pi05` ...
   - `タスク`: `cobra` など短いタスク名
   - `カメラ`: 学習に使ったカメラの set（`frontwrist` / `wrist`）。MLflow の `obs_cameras` param と対応
   - `バリアント`: 他の run と違う点をハイフン区切りで（`bs32` / `lr1e-4` / `seed1000`）。省略可
   - `日付`: `YYYYMMDD`
   - 例: `act_cobra_frontwrist-bs32_20261020` / `diffusion_cobra_wrist_20261020`
   - **既存ディレクトリの改名はしない**（重みパスが資料に広がっている。旧名はこのまま使う）
3. **実機評価を終えたら `scripts/log_eval_mlflow.py` で学習 run に成功率を返す**（[24 の評価](24_model_eval_campaign.md) のあと）

### 何が比較軸として残るか

params として次が記録され、MLflow UI の Compare / フィルタで横並びにできる:

| param | 例 | 由来 |
|-------|-----|------|
| `obs_cameras` | `front+wrist` / `wrist` | `policy.input_features` から導出 |
| `policy.chunk_size` / `policy.n_action_steps` / `policy.horizon` / `policy.kl_weight` / `policy.num_inference_steps` / `policy.path` | `100` / `32` / `64` / `10.0` | 各ポリシーのハイパラ（持たない policy では記録されない） |
| `steps` / `batch_size` / `optimizer.lr` / `seed` / `policy.type` | `8040` / `32` / `1e-05` / `1000` / `act` | 学習全体の設定 |
| `dataset.repo_id` / `dataset.root` | `local/...` | データセット |

完全な設定は artifact `mlflow_train_config.json`。実機評価の結果は同じ run の metric `eval/success_rate` と tag `eval.last_summary` に乗る。

### 学習済み run の後付け登録

```bash
# so101-lab リポジトリ直下で実行
../lerobot/.venv/bin/python scripts/backfill_mlflow.py \
  ../lerobot/outputs/train/<run名>
```

`checkpoints/last/pretrained_model/train_config.json` を読み、params（`obs_cameras` 込み）と設定 artifact を登録して `mlflow_run_id.txt` を書く。**損失曲線は復元できない**（params / artifact のみ）。mlflow が入っている lerobot の venv で実行する。

### 実機評価を学習 run に返す

```bash
# so101-lab リポジトリ直下で実行
../lerobot/.venv/bin/python scripts/log_eval_mlflow.py \
  --output_dir ../lerobot/outputs/train/<run名> \
  --eval-id E-20261021-01 \
  --trials 10 --successes 6 \
  --avg-success-s 41.2 \
  --failures no_reach=2,no_grasp=1 \
  --note "物体は定位置固定"
```

- `--run-id` を直接渡すこともできる（既定は `output_dir/mlflow_run_id.txt` を読む）
- metric は `eval/success_rate` / `eval/trials` / `eval/successes` / `eval/avg_success_s` / `eval/fail_<種別>`。評価を重ねるほど step が進み、UI で時系列に並ぶ
- tag `eval.last_summary`（評価 ID・日付・失敗内訳の JSON）と tag `eval.ids`（全評価 ID）
- 結果の本文は [reports/model_eval_results.md](reports/model_eval_results.md) に書き、そこにも run ID を残す

### UI が健康なのに `mlflow.db` が更新されないとき

サーバの health が 200 なのにホストの `mlflow_store/mlflow.db` の mtime が古いままのときは、**コンテナが過去のディレクトリ（削除済み inode）にバインドしている**。2026-10-21 に実際に起きた。この状態でサーバ経由に書いた記録はコンテナを作り直すまでホストの DB に出ない（出ないだけで消えてはいないが、`docker compose down` で失われる）。

```bash
# so101-lab リポジトリ直下で実行
docker compose down && docker compose up -d   # 現在の mlflow_store に再バインド
```

直後に `docker exec so101-mlflow python -c "import sqlite3,os; print(os.stat('/mlflow/mlflow.db').st_size)"` がホストの `mlflow.db` と同じサイズになることを確認する。

---

## 1. UI を上げる（Docker）

前提: Docker と `docker compose` が入っていること。

リポジトリルートで、学習とは別の端末です。

```bash
# so101-lab リポジトリ直下で実行
./scripts/start_mlflow.sh
# 同等: make mlflow-serve
# 同等: docker compose up -d mlflow
```

- この PC: <http://127.0.0.1:5000>
- 同じ LAN の別 PC: `http://<このホストのIP>:5000`
- 実験名の既定は `so101`（`configs/mlflow.yaml`）
- データはホストの `mlflow_store/`（コンテナ内 `/mlflow`）
- 止める: `make mlflow-stop` または `docker compose stop mlflow`
- ログ: `make mlflow-logs`

初回は公式イメージ `ghcr.io/mlflow/mlflow:v2.22.1` を pull します。サーバは `restart: unless-stopped` なので、止めるまで起動したままにします。

### Docker が使えないとき

```bash
SO101_MLFLOW_BACKEND=uv ./scripts/start_mlflow.sh
```

`uv sync --all-groups` のあと、ホスト上で `mlflow server` を直接起動します（`--group` 指定の同期は他グループを環境から外すため、このラボでは常に `--all-groups` を使います）。

## 2. 学習する

GPU ホストで、UI を上げたあと。**素の `lerobot-train` は使わない**（記録が残らない。上のルール）。`job_name` は `output_dir` の basename と同じにします（ラッパーが不一致を止めます）:

```bash
# so101-lab リポジトリ直下で実行
./scripts/train_mlflow.sh \
  --dataset.repo_id=$REPO_ID \
  --policy.type=act \
  --output_dir=outputs/train/act_cobra_frontwrist-bs32_<日付> \
  --policy.device=cuda \
  --policy.push_to_hub=false
```

作業ディレクトリは `~/robot/lerobot` になります（スクリプトが移動します）。`outputs/train/...` はそこの相対パスです。

初回だけ、同じスクリプトが **lerobot の venv** に `mlflow` を入れます。学習プロセスはこちらの Python で動くため、UI 用の Docker イメージとは別です。

`--wandb.enable` は書かなくて構いません。ラッパーが LeRobot のロガーをローカル MLflow に接続します。

UI を先に上げておくと、学習は `http://127.0.0.1:5000` に書きます（Docker の artifact proxy 経由）。サーバが無いときは同じ `mlflow_store/mlflow.db` に直接書き、あとから `./scripts/start_mlflow.sh` で見られます。同時に sqlite へ直接書くプロセスとサーバを走らせないでください。

## 3. 曲線の見方

ブラウザで実験 `so101` を開き、run 名（`--job_name`）を選びます。

- `train/loss` など: 学習ステップごとのスカラー
- `eval/eval_loss`: データセット評価を有効にしたとき
- `eval/success_rate` など: 実機評価を `log_eval_mlflow.py` で返したとき（step = 評価キャンペーンの回数）
- tag `last_checkpoint`: 最後に保存したチェックポイントのパス
- artifact `mlflow_train_config.json`: その実行の設定

run id は `output_dir/mlflow_run_id.txt` に 1 行で残ります。同じ `output_dir` で `--resume=true` すると、その run に追記します。

---

## 設定

`configs/mlflow.yaml` · `docker-compose.yml`

| キー | 既定 | 環境変数 |
|------|------|----------|
| `host` | `0.0.0.0` | `SO101_MLFLOW_HOST` |
| `port` | `5000` | `SO101_MLFLOW_PORT` |
| `store_dir` | `mlflow_store` | `SO101_MLFLOW_STORE` |
| `experiment` | `so101` | `SO101_MLFLOW_EXPERIMENT` |
| backend | `docker` | `SO101_MLFLOW_BACKEND`（`docker` / `uv`） |

クライアントだけ URI を固定するときは `MLFLOW_TRACKING_URI`（例: `http://127.0.0.1:5000`）。

ポートの位置づけは [07 ポート一覧](07_multi_host.md) です。
