# 24 — 学習済みモデルの実機評価・選別（コブラ・ピックアップ）

手元にある学習済み重みを **同じタスク・同じプロトコルで順に実機評価し、記録して勝ち残りを決める** ためのキャンペーン手順です。推論の経路（Thor で計算 / Pi でクライアント）は [17](17_act_record_train_infer.md) と同じです。結果の正本は [作業レポート（評価結果）](reports/model_eval_results.md)。学習〜推論の横断一覧は [ラン台帳](reports/run_registry.md)。

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-10-21 |
| 対象タスク | コブラを首でつかみ、透明容器へ入れる |
| タスク文 | `Grab the cobra by the neck and put its whole body inside the clear plastic container.` |
| 学習データ | `local/so101_singlearm_pickup_cobra_20261018_205119_curated`（46 episodes / 8,567 frames / 30 fps、両カメラ） |
| 評価プロトコル | モデルあたり **10 試行**（[17 §5](17_act_record_train_infer.md#本番セッションのゲートと進め方t-p1-05) と同じ） |
| 合格ライン | 10 試行中 **5 以上** 成功 |

---

## 1. 対象モデル（2026-10-21 時点で実機で試せるもの）

重みはすべて WSL（4090, `${SO101_GPU_SSH}`）にあります。パスの起点は so101-lab から見て `../lerobot/outputs/train/` です。

| ID | モデル | カメラ | steps / batch | 重み（`checkpoints/last/pretrained_model`） | MLflow run | 備考 |
|----|--------|--------|---------------|---------------------------------------------|------------|------|
| **M1** | ACT | front + wrist | 8,040 / 32 | `act_so101_cobra_curated_bs32_20261019/` | `adfe9819` | ベースライン |
| **M2** | ACT | **wrist のみ** | 8,040 / 32 | `act_so101_cobra_curated_wrist_only_20261020/` | `48cda770` | M1 とのカメラ比較 |
| **M3** | Diffusion | front + wrist | 32,158 / 8 | `diffusion_so101_cobra_curated_20261019/` | `dbdc72a1` | M1 との手法比較 |
| **M4** | Diffusion | **wrist のみ** | 32,158 / 8 | `diffusion_so101_cobra_curated_wrist_only_20261020/` | `a24781f7` | M3 とのカメラ比較 |

MLflow run は先頭 8 桁。完全な ID は各 `output_dir/mlflow_run_id.txt`、UI は実験 `so101`（[16](16_local_mlflow.md)）。M2・M4 は `lerobot-train` 直実行だったため [16 の手順](16_local_mlflow.md#学習済み-run-の後付け登録)で後付け登録済み（損失曲線はなし・params と設定あり）。

評価の推奨順は **M1 → M2 → M3 → M4** です。まず ACT（推論が軽い）で基準を作り、同じ手法でカメラ構成を比べ、そのあとで手法（ACT vs Diffusion）を比べます。

**対象外**（試さない理由を残しておく）:

| 学習ディレクトリ | 理由 |
|------------------|------|
| `act_so101_coffee_smoke_20261018` | コーヒー・タスク。タスクが違い比較にならない |
| `make_a_pilamid_bs64` | ピラミッド・タスク（`takeforest/teamB`）。タスクが違う |
| `turbovla_so101_cobra_20261019` | 20 step のスモークのみ。実用重みなし |
| `act_so101_cobra_curated_20261019` | 成果物なし（bs32 としてやり直し済み） |

## 2. 事前確認（WSL・評価開始前に 1 回）

モデルごとに、重みが期待するカメラと行動チャンクを確認します。この 2 つがクライアント側の設定とずれると動きません。

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot
python3 -c "
import json, glob
p = glob.glob('outputs/train/<学習ディレクトリ>/checkpoints/last/pretrained_model/config.json')[0]
c = json.load(open(p))
print('cameras:', [k for k in c['input_features'] if 'image' in k])
print('n_action_steps:', c.get('n_action_steps'))
"
```

| モデル | クライアントに渡すカメラ | `--actions_per_chunk` |
|--------|--------------------------|-----------------------|
| M1 | front + wrist | 100 |
| M2 | **wrist だけ** | 100 |
| M3 | front + wrist | 32 |
| M4 | **wrist だけ** | 32 |

`--actions_per_chunk` は `n_action_steps` に合わせます（ACT = 100、Diffusion = 32）。

## 3. 役割と安全（[17](17_act_record_train_infer.md) と同じ）

| マシン | やること |
|--------|----------|
| WSL（4090） | 重みの保管と Thor への転送 |
| Jetson Thor（`${SO101_THOR_TAILSCALE_IP}`） | `policy_server`（起動しっぱなしでよい） |
| Raspberry Pi | 腕とカメラ。`go_so101_home.sh` と `robot_client` |

- **LeLab / Web Remote は起動しない**。ESTOP を手元に置く
- クライアントは `--robot.max_relative_target=5 --robot.disable_torque_on_disconnect=false` を必ず付ける（[17 §4](17_act_record_train_infer.md) と同じ値）
- Thor は初回のみ `scripts/patch_draccus_py314.py` を実行（venv を作り直したあとも）。`already patched` が出てからサーバを起動する

## 4. 手順

### 4a. WSL — 重みを 4 つまとめて Thor へ送る

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot/outputs/train
for m in act_so101_cobra_curated_bs32_20261019 \
         act_so101_cobra_curated_wrist_only_20261020 \
         diffusion_so101_cobra_curated_20261019 \
         diffusion_so101_cobra_curated_wrist_only_20261020; do
  rsync -a "$m/checkpoints/last/pretrained_model/" "<user>@${SO101_THOR_TAILSCALE_IP}:~/so101_eval/$m/"
done
```

送り先を `~/so101_eval/<学習ディレクトリ>/` に統一すると、以降のコマンド差し替えがパス 1 箇所だけで済みます。

### 4b. Thor — policy_server を上げる（1 回だけ）

[17 §3](17_act_record_train_infer.md) と同じです。**サーバはモデルを持ちません**。クライアントが最初の接続で重みのパスを渡し、Thor 側でロードします。サーバは起動しっぱなしでよく、モデルを替えるときはクライアントだけ再起動します。

```bash
# so101-lab リポジトリ直下で実行
uv run --no-sync python scripts/patch_draccus_py314.py   # 初回 / venv 作り直し後のみ

cd ~/robot/lerobot
uv run --no-sync python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 --port=8080 --fps=30 --obs_queue_timeout=5
```

`PolicyServer started on 0.0.0.0:8080` を確認します。

### 4c. Pi — 1 試行の進め方

1. **nest へ戻す**（試行のたびに必ず）:

   ```bash
   ./scripts/go_so101_home.sh --arm follower
   ```

2. **物体を定位置に置く**。コブラと容器は、録画データ（`so101_singlearm_pickup_cobra_20261018_205119_curated` の最初の episode の映像）と同じ位置・向きに置きます。位置をずらした試行は §5 の位置ばらつき評価でのみ行います
3. **クライアントを起動**（下のコマンド。モデル別の差し替え箇所は 2 箇所だけ）
4. タスクが完了、または **60 秒で打ち切り**（`Ctrl+C`）。打ち切り時点の状態を記録する
5. **nest へ戻す** → 結果を記録 → 次の試行へ

クライアント（M1 の例。`<MODEL>` と `--robot.cameras` をモデル別表で差し替える）:

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
  --policy_type=act \
  --pretrained_name_or_path=$HOME/so101_eval/act_so101_cobra_curated_bs32_20261019 \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=100 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  --task="Grab the cobra by the neck and put its whole body inside the clear plastic container."
```

**モデル別の差し替え**（表 §2 と同じ内容）:

| モデル | `--policy_type` | `--pretrained_name_or_path` | `--actions_per_chunk` | `--robot.cameras` |
|--------|-----------------|------------------------------|-----------------------|-------------------|
| M1 | `act` | `.../so101_eval/act_so101_cobra_curated_bs32_20261019` | 100 | front + wrist（上のまま） |
| M2 | `act` | `.../so101_eval/act_so101_cobra_curated_wrist_only_20261020` | 100 | **wrist のみ**にする |
| M3 | `diffusion` | `.../so101_eval/diffusion_so101_cobra_curated_20261019` | 32 | front + wrist |
| M4 | `diffusion` | `.../so101_eval/diffusion_so101_cobra_curated_wrist_only_20261020` | 32 | **wrist のみ**にする |

wrist のみにするときは、`--robot.cameras` から `front` の項目を削ります:

```bash
  --robot.cameras='{ wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} }' \
```

**カメラキー・解像度・fps は学習時と変えない**のが原則です（[17 §4](17_act_record_train_infer.md)）。wrist-only モデルで front を渡すと観測の形が学習とずれるため、削るのが安全です。俯瞰の映像が欲しいときは試行をスマホなどで外から撮影してください。

Thor のログに `Policy type: ... | Pretrained name or path: ...` が出てから腕が動きます。

### 4d. モデルを替える

サーバは触りません。Pi のクライアントを `Ctrl+C` → nest へ戻す → 表の 2 箇所（`--pretrained_name_or_path` と `--actions_per_chunk`、必要ならカメラ）を替えて起動し直すだけです。

## 5. 評価プロトコル

| 項目 | 既定 |
|------|------|
| 試行数 | モデルあたり **10 試行**（nest 開始・物体は定位置） |
| 成功 | コブラを首でつかみ、**全身が透明容器に入る**（タスク文どおり） |
| 打ち切り | 1 試行 60 秒。打ち切り時点の状態を失敗種別で記録 |
| 失敗種別 | `no_reach`（届かない） / `no_grasp`（把持できない） / `no_place`（容器に入らない・途中で落とす） / `disturb`（振動・暴走で停止） |
| 副指標 | 完了までの秒数（成功試行のみ）。Thor のログの推論 FPS も控える |
| MLflow 記録 | 10 試行の集計が終わったら `scripts/log_eval_mlflow.py` で学習 run に成功率・失敗内訳を記録（[16](16_local_mlflow.md)） |

物体位置を固定するのは、**モデル間の差を出すため**です。合格したモデルだけ、追加で位置ばらつき評価（物体を 3 箇所 × 各 3 試行）を行い、汎化を確認します。

## 6. 選別の基準

結果は [reports/model_eval_results.md](reports/model_eval_results.md) に集計します。集計が終わったら、モデルごとに `log_eval_mlflow.py` を 1 回実行して MLflow の学習 run に返します（パラメータを変えた学習と実機成功率の対応が、UI の 1 画面で見られるようになります）:

```bash
# so101-lab リポジトリ直下で実行
../lerobot/.venv/bin/python scripts/log_eval_mlflow.py \
  --output_dir ../lerobot/outputs/train/act_so101_cobra_curated_bs32_20261019 \
  --eval-id E-20261021-01 --trials 10 --successes 6 \
  --avg-success-s 41.2 --failures no_reach=2,no_grasp=1 --note "物体は定位置固定"
```

1. **主基準**: 成功率 5/10 以上 → 「このタスクで成立」と判断
2. **同率のとき**: 平均完了時間が短い方を上位に。さらに同点なら wrist-only（front カメラ不要で構成が軽い）を上位に
3. **全モデルが 5/10 未満のとき**: step 数を増やすのではなく、失敗種別の分布で次を決める（[17 §5](17_act_record_train_infer.md) の表）

| 最も多い失敗種別 | 次の一手 |
|------------------|----------|
| `no_reach` | デモの追加（位置のばらつきを増やす）。step 増は効かないことが多い |
| `no_grasp` | 把持の瞬間に wrist 映像が対象を捉えているか。グリッパ閉じるタイミングのデモを見直す |
| `no_place` | 容器位置の記録を撮り、デモと実機の位置ずれを消す |
| `disturb` | 推論設定（`max_relative_target`・chunk 設定）を確認。改善しなければそのモデルは落ちとする |

**落とし方**: 一度評価した重みは消さず、結果表に「採用 / 落選」と理由を残します。落選の理由が失敗種別で説明できていれば、次のデータ収集・学習の方針に直結します。

## 7. 進行の目安

1 モデル = 初回セットアップ 15 分 + 10 試行 × 2〜3 分 ≈ **45 分**。4 モデルで半日を見ます。試行をまたぐときのチェックは [チェックリスト](checklists/model_eval.checklist.md) を使います。

| 症状 | 対処 |
|------|------|
| クライアントが `Failed to connect` | Thor のサーバが上がっているか。`--server_address` は Thor の Tailscale IP か |
| Thor が重みを読めない | パスは **Thor 上**（`$HOME/so101_eval/...`）か。4a の rsync をやり直す |
| wrist-only で起動直後にエラー | クライアントのカメラから `front` を削り忘れていないか |
| 腕が nest 付近で小さくしか動かない | 開始姿勢がデモとずれている。nest 手順を見直す |
| 成功率が MLflow の損失と相関しない | それが普通です。実機成功率だけが選別の基準 |

---

## 8. スマホ操作（推論） {#infer-buttons}

録画の 8770 と同じ発想で、推論中は **Pi の `0.0.0.0:8771`** にスマホ向けページを出します。`scripts/infer_with_buttons.sh` が `robot_client` と同じ引数で起動し、接続後に URL をターミナルへ出します。LeLab / Web Remote は起動しません。

| 画面 | 表示 | ボタン |
|------|------|--------|
| 開始待ち | 試行 n/N、成功数、モデル名、ライブ映像 | 試行開始、nest へ |
| 推論中 | 経過 / 上限（既定 60s）、ライブ映像 | 試行終了、一時停止 |
| 結果 | 直前の経過 | 成功 / 届かない / 把持失敗 / 置けない / 暴走・停止 |

一時停止は行動キューを捨て、観測のサーバ送信も止めます。腕は現姿勢のままです（トルクは切りません）。60 秒で自動的に結果画面へ入ります（`SO101_INFER_TIMEOUT_S`）。試行数の表示は `SO101_INFER_TRIALS`（既定 10）。ポートは `SO101_INFER_BUTTONS_PORT`。

開始待ちでは **前のモデル / 次のモデル** でカタログを切り替えます（一覧は `configs/infer_models.snakebowl.json`、`SO101_INFER_MODELS` で差し替え可）。切替はサーバが重みを読み直すので数十秒かかることがあります。スコアはモデルごとにリセットします。SmolVLA など optional 行は `SO101_INFER_INCLUDE_OPTIONAL=1` のときだけ出ます。

初回の推論チャンクは GPU 共有時に **約10秒** かかることがあります。それ以降も動かないときはシリアル詰まりを疑い、セッション終了→ nest → 再起動します。

**ロールアウトの記録（GR-BC 用・オプション）**: 起動時に `SO101_INFER_RECORD=1` を付けると、
結果ボタンで確定した各試行が LeRobot v3.0 データセットとして録画され、成否は
`grbc_manifest.jsonl` に追記されます（失敗種別も記録。取り消しは manifest 側も無効化）。
評価フロー自体は変わりません。データの取り回しと注意は [15 §1c](15_dataset_pipeline.md#rollout-record)、
使う側の手順は [26](26_grbc_posttraining.md)。**実機での初回確認はまだ**（[D-20261027-01](reports/design_notes.md)）。

判断の記録: [D-20261023-02](reports/design_notes.md)。

---

## 9. snake_bowl（2026-10-23）の順次推論 {#snake-bowl}

タスク文（学習・推論で一致）:

```text
Pick the red neck of snake and place drop in the silver bowl
```

データ: `local/so101_single_snake_bowl_20261022_194956`。重みは WSL `../lerobot/outputs/train/`。評価順は **ACT → Diffusion → TurboVLA → SmolVLA**（軽い順・手法比較）。

| ID | モデル | 学習ディレクトリ | `--actions_per_chunk` | 備考 |
|----|--------|------------------|------------------------|------|
| SB1 | ACT | `act_snakebowl_frontwrist-base_20261023` | 100 | 先に通す |
| SB2 | Diffusion | `diffusion_snakebowl_frontwrist-base_20261023` | 32 | |
| SB3 | TurboVLA | `turbovla_snakebowl_frontwrist-base_20261023` | 12 | |
| SB4 | SmolVLA | `smolvla_snakebowl_frontwrist-base_20261023` | 50 | 学習完了後 |

カメラはいずれも `front` + `wrist`（学習時と同じ）。推論ホストは当面 **学習と同じ git の WSL**（`${SO101_GPU_TAILSCALE_IP}:8080`）を推奨（Thor の ACT キー不一致は [run_registry R-20261021-01](reports/run_registry.md)）。

### 9a. WSL — 重みを Pi が見るパスへ（サーバが WSL のとき）

サーバが WSL のときは、チェックポイントは WSL 上のまま渡せます（`--pretrained_name_or_path` は **サーバ側** のパス）:

```bash
# WSL
ls ../lerobot/outputs/train/act_snakebowl_frontwrist-base_20261023/checkpoints/last/pretrained_model
```

Thor で計算するときだけ rsync（[23](23_data_transfer.md)）:

```bash
cd ../lerobot/outputs/train
for m in act_snakebowl_frontwrist-base_20261023 \
         diffusion_snakebowl_frontwrist-base_20261023 \
         turbovla_snakebowl_frontwrist-base_20261023 \
         smolvla_snakebowl_frontwrist-base_20261023; do
  rsync -a "$m/checkpoints/last/pretrained_model/" "<user>@${SO101_THOR_TAILSCALE_IP}:~/so101_eval/$m/"
done
```

### 9b. サーバ（WSL 例・1 回）

```bash
cd ~/robot/lerobot
uv run --no-sync python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 --port=8080 --fps=30 --obs_queue_timeout=5
```

### 9c. Pi — スマホ付きクライアント（SB1 の例）

```bash
# so101-lab 直下
SO101_INFER_TRIALS=10 SO101_INFER_TIMEOUT_S=60 \
./scripts/infer_with_buttons.sh \
  --robot.type=so101_follower \
  --robot.port=${SO101_FOLLOWER_PORT} \
  --robot.id=my_follower \
  --robot.max_relative_target=5 \
  --robot.disable_torque_on_disconnect=false \
  --robot.cameras='{ front: {type: intelrealsense, serial_number_or_name: "${SO101_REALSENSE_SERIAL}", width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} }' \
  --server_address=${SO101_GPU_TAILSCALE_IP}:8080 \
  --policy_type=act \
  --pretrained_name_or_path=$HOME/robot/lerobot/outputs/train/act_snakebowl_frontwrist-base_20261023/checkpoints/last/pretrained_model \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=100 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  --task="Pick the red neck of snake and place drop in the silver bowl"
```

モデルを替えるときはクライアントを止めて、`--policy_type` / `--pretrained_name_or_path` / `--actions_per_chunk` だけ差し替えます（サーバは起動したまま）。結果は [model_eval_results.md](reports/model_eval_results.md) と [run_registry](reports/run_registry.md) へ。
