# 17 — 片腕 ACT：デモを足す、学習する、Thor で推論する

2026-10-18 に通った経路の手順です。録画のキー操作は [15](15_dataset_pipeline.md)、**データ／重みの転送は [23](23_data_transfer.md)**、キャリブと手テレオペは [14](14_single_arm_il.md)、曲線は [16](16_local_mlflow.md)。ここは **どのマシンで、どのパスを、次に何をするか** だけを固定します。

コーヒーのスモーク（5 本・5,000 step）は、パイプラインが動くことの確認までです。ポッドまで届くポリシーには、デモを足してから学習を別ディレクトリでやり直します。

---

## 役割 {#roles}

| マシン | やること | やらないこと |
|--------|----------|----------------|
| Raspberry Pi 4 | 録画、nest、推論クライアント（腕とカメラ） | ACT の順伝播、`lerobot-train` |
| 4090 の WSL（Tailscale `gpu` / `${SO101_GPU_TAILSCALE_IP}`） | `lerobot-train`。データセットの保管。閲覧と選別（`lerobot-edit-dataset` / `lerobot-dataset-viz`） | 実機シリアルは繋がっていない。Pi では選別しない |
| Jetson Thor（Tailscale `thor` / `${SO101_THOR_TAILSCALE_IP}`） | `policy_server`（CUDA） | 腕の USB は挿さない |

Pi 4 の torch は `2.11.0+cu128` で、大きい行列積が Illegal instruction になります。`lerobot-rollout` をこの Pi で ACT に使っても、行動を出す前に落ちます。計算は Thor、腕は Pi です。

LeLab と Web Remote は、録画中も推論中も起動しません。ESTOP は手元に置きます。

---

## いま残っているもの（2026-10-18）

| もの | パス |
|------|------|
| デモ | WSL `~/.cache/huggingface/lerobot/local/so101_single_coffee_smoke_20261018_085324`（5 本、1332 フレーム、30 fps） |
| タスク文 | `Pick up the coffee pot, pour it into a clear container, and put the coffee pod back where it was.` |
| スモーク重み | WSL `../lerobot/outputs/train/act_so101_coffee_smoke_20261018/checkpoints/last/pretrained_model` |
| Thor にコピーした重み | `$HOME/act_so101_coffee_smoke_20261018` |
| Pi にコピーした重み | `~/.cache/lerobot/policies/act_so101_coffee_smoke_20261018` |

学習設定は step 5,000、batch 8、`policy.type=act`、`push_to_hub=false` です。5 本・1332 フレームだと、この step 数はデータをおよそ 30 周見ています。損失は step 200 で 6.47、終了時 0.32、と学習側から報告されています。この重みで実機は動きましたが、ポッドには届いていません。

この重みは消さず、比較用に残します。次の学習の初期値にはしません。

---

## 1. デモを足す（Pi）、選別は WSL

録画は Pi、映像を見て本を除く作業は WSL です。コマンドと、コブラ 66 本（`local/so101_singlearm_pickup_cobra_20261018_205119`）のパスは [15 — 閲覧・選別](15_dataset_pipeline.md#dataset-review)。

## 1b. すでに WSL にあるデモを仕分けるときの例（コーヒーのスモーク） {#demo-review}

この例も WSL の lerobot（so101-lab から見て `../lerobot`）で実行します。リポジトリと venv は **<user> 所有**（2026-10-19 に root から変換）なので、`<user>` ログインのまま `.venv/bin/lerobot-edit-dataset` を実行します。パスはリポジトリ相対（`../lerobot`）または `$HOME` で書きます（他人の環境でも再現しやすい）。

5 本は壊れていません。届かなかった理由は、その 5 本の軌道しか覚えていないことです。映像を見て、注ぎ切れている本は残します。途中で止まっている本、対象が `front` と `wrist` の両方に映っていない本は、新しいデータセットに入れません。

残す本だけを別ディレクトリに出すとき（番号は捨てる側）:

```bash
.venv/bin/lerobot-edit-dataset \
  --repo_id=local/so101_single_coffee_smoke_20261018_085324 \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_smoke_20261018_085324 \
  --new_repo_id=local/so101_single_coffee_smoke_20261018_085324_kept \
  --new_root=$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_smoke_20261018_085324_kept \
  --operation.type=delete_episodes \
  --operation.episode_indices="[1, 3]"
```

追加の録画は [15](15_dataset_pipeline.md) と同じカメラ、同じタスク文、nest から始めます。本数の目安は、場所を変えて合計 40〜50 です。スタンプ付きの新しい `repo_id` で録り、スモークと混ぜるときは結合します。

```bash
.venv/bin/lerobot-edit-dataset \
  --new_repo_id=local/so101_single_coffee_<日付> \
  --new_root=$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_<日付> \
  --operation.type=merge \
  --operation.repo_ids="['local/so101_single_coffee_smoke_20261018_085324_kept', 'local/so101_single_coffee_<追加分>']" \
  --operation.roots="['<kept の絶対パス>', '<追加分の絶対パス>']"
```

結合は GPU ホスト上のコピーに対して行います。`info` で `total_episodes` とカメラキーを確認してから学習します。

---

## 2. 学習する（4090 の WSL） {#train}

学習は **必ず `train_mlflow.sh` 経由** で回します（[16 のルール](16_local_mlflow.md)。素の `lerobot-train` は MLflow に曲線・ハイパラ・run ID が残らず、後から比較できません）。リポジトリと venv は **<user> 所有**なので、`<user>` ログインのまま実行します。`sudo` は付けません（`HOME` が `/root` に変わってキャッシュ先がずれます）。

`output_dir` は [16 の命名規約](16_local_mlflow.md)（`{policy}_{タスク}_{カメラ}-{バリアント}_{日付}`）で付け、`job_name` はその basename と同じにします（ラッパーが不一致を止めます）。

step 数は、スモークと同じ周回になるようフレーム数に比例させます。

```text
steps ≈ 5000 * (新しい total_frames / 1332)
```

バッチ 8 のままです。出力ディレクトリはスモークと別にします。

```bash
# so101-lab リポジトリ直下で実行
LEROBOT_DIR=../lerobot ./scripts/train_mlflow.sh \
  --dataset.repo_id=local/so101_single_coffee_<日付> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_<日付> \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --batch_size=8 \
  --steps=<上の式> \
  --output_dir=outputs/train/act_coffee_frontwrist-bs8_<日付> \
  --seed=1000
```

`--job_name` は省略できます（`output_dir` の basename から自動で付きます）。

終わったら、Pi から読めることを確認します。出力は `<user>` 所有で作られるので、通常は chmod 不要です（2026-10-19 より前の root 実行時代の出力だけ、必要に応じて `sudo chmod -R a+rX`）。

チェックポイントは次です。`last` は最終 step へのリンクです。

```text
outputs/train/act_so101_coffee_<日付>/checkpoints/last/pretrained_model
```

中身は `config.json`、`model.safetensors`、前後処理の JSON と safetensors、`train_config.json` です。このディレクトリごと Thor へ送ります。Hub には上げません。

曲線を見るときは [16](16_local_mlflow.md)。WSL の MLflow は `http://${SO101_GPU_TAILSCALE_IP}:5000` です。

---

## 3. Thor でサーバを上げる

重みの送り方（GPU→Thor / Pi 経由）の正本は **[23 — チェックポイント](23_data_transfer.md#ckpt-gpu-thor)**。  
`--pretrained_name_or_path` は **Thor 上のパス** です。最短例:

```bash
# GPU で
rsync -a ../lerobot/outputs/train/act_so101_coffee_<日付>/checkpoints/last/pretrained_model/ \
  <user>@${SO101_THOR_TAILSCALE_IP}:~/act_so101_coffee_<日付>/
```

Thor の lerobot venv は Python 3.14 です。そのままでは `dict | None` を argparse に渡して ACT の設定が読めません。venv を作り直したあとも、サーバの前に一度実行します。

```bash
# Thor で
# so101-lab リポジトリ直下で実行
uv run --no-sync python scripts/patch_draccus_py314.py
```

`already patched` または `patched:` が出てからサーバです。パッチのあとに起動したプロセスだけが修正を読みます。

```bash
cd ~/robot/lerobot
uv run --no-sync python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
uv run --no-sync python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 \
  --port=8080 \
  --fps=30 \
  --obs_queue_timeout=5
```

`True` と `NVIDIA Thor`、続けて `PolicyServer started on 0.0.0.0:8080` を確認します。ファイアウォールを使うときは、Pi から TCP 8080 だけを開けます。

---

## 4. Pi で推論する

初回だけ gRPC を入れます。torch は入れ替えません。

```bash
cd ~/robot/lerobot
uv pip install --python .venv/bin/python 'grpcio>=1.73.1,<2'
```

推論の前に follower だけ nest へ戻します。

```bash
# so101-lab リポジトリ直下で実行
./scripts/go_so101_home.sh --arm follower
```

ポット、ポッド、容器は録画と同じ位置に置きます。クライアントはサーバが `PolicyServer started` を出してから起動します。1 周期の移動は 5° までです。切断時にトルクは切りません。

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
  --pretrained_name_or_path=$HOME/act_so101_coffee_<日付> \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=100 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  --task="Pick up the coffee pot, pour it into a clear container, and put the coffee pod back where it was."
```

`actions_per_chunk` はチェックポイントの `n_action_steps`（この ACT は 100）に合わせます。ACT はタスク文を使わないので、文はログ用です。カメラキーと解像度は学習データと変えないでください。

Thor のログに `Policy type: act` が出てから腕が動きます。止めるときはクライアントを `Ctrl+C` し、そのあと nest へ戻します。

```bash
# so101-lab リポジトリ直下で実行
./scripts/go_so101_home.sh --arm follower
```

同じ引数でスマホから試行開始／一時停止／成功・失敗を付けるときは、`python -m …robot_client` の代わりに `./scripts/infer_with_buttons.sh` を使います（待受 `0.0.0.0:8771`）。手順と snake_bowl の順次評価は [24 §8–9](24_model_eval_campaign.md#infer-buttons)。

届いたかどうかは、試行回数と、ポッドを持ち上げて容器へ注げた回数を [作業レポート](reports/single_arm_il_work_report.md) に分けて書きます。

---

## 5. 本番セッションのゲートと進め方（T-P1-05）

スモークと同じ経路を、データを増やしてもう一周するのが本番です。着手前に以下を全て確認します（[チェックリスト](checklists/single_arm_il.checklist.md) の「本番」ブロックと同じ）。

**着手ゲート（全て `[x]` になってから録画へ）**:

- [ ] スモーク 5 本を映像で仕分け、残す本だけの `*_kept` データセットを作った
- [ ] 追加録画を含め合計 40〜50 本・場所にばらつきがある
- [ ] 結合後の `info.json` で `total_episodes` / `total_frames` / カメラキー（`front`・`wrist`）を確認した
- [ ] `steps ≈ 5000 * (total_frames / 1332)` を計算してある
- [ ] 新しい `output_dir` 名（`act_so101_coffee_<日付>`）を決めた
- [ ] 学習は `train_mlflow.sh` で回す（必須。[16](16_local_mlflow.md)）。WSL の MLflow（`http://${SO101_GPU_TAILSCALE_IP}:5000`）が起動している

**学習（正本）**: §2 の `train_mlflow.sh` と同じです（`LEROBOT_DIR` 込み）。以降（Thor 送信 → patch_draccus → サーバ → クライアント）は §3・§4 と同じです。

```bash
# so101-lab リポジトリ直下で実行。WSL 側の so101-lab でも可（LEROBOT_DIR 既定が ~/robot/lerobot）
LEROBOT_DIR=../lerobot ./scripts/train_mlflow.sh \
  --dataset.repo_id=local/so101_single_coffee_<日付> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_<日付> \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --batch_size=8 \
  --steps=<計算した値> \
  --output_dir=outputs/train/act_coffee_frontwrist-bs8_<日付> \
  --seed=1000
```

以降（Thor 送信 → patch_draccus → サーバ → クライアント）は §3・§4 と同じです。

**評価プロトコル（本番の成功判定）**:

| 項目 | 既定 |
|------|------|
| 試行 | **10 試行**（nest から。物体は毎回同じ位置） |
| 成功 | ポッドを持ち上げ、容器へ注ぎ切る（＝学習時のタスク文の完了） |
| 記録 | 試行数・成功数・どこで止まったかを [作業レポート](reports/single_arm_il_work_report.md) に S- セッションで追記 |
| 目安 | 10 試行中 5 以上で「ACT はこのタスクで成立」と判断し SmolVLA 比較へ |

判定が出たら `scripts/log_eval_mlflow.py` で成功率・失敗内訳を学習 run の MLflow に返します（[16](16_local_mlflow.md) · モデル横並びの評価は [24](24_model_eval_campaign.md)）。

**届かなかったときの判断**（むやみに step を増やさない）:

| 症状 | 次の一手 |
|------|----------|
| 動きが小さく nest 近辺で止まる | 推論設定（5° 制限・カメラキー）を再確認。デモの初期姿勢と nest を揃える |
| 方向は合うが届かない | **デモを追加**（位置のばらつきを増やす）。step 増は効かないことが多い |
| 試行ごとに成功・失敗が分かれる | 成功本と失敗本の映像を見て、失敗要因（光・物体位置）をデータで消す |
| 損失は下がるが実機が崩れる | オーバーフィットの疑い。step を 0.7 倍にして再学習して比較 |

**次の比較（ACT が成立してから）**: 同じデータで [SmolVLA FT](learn/03_smolvla/01_finetune.md)（[14 Step 4b](14_single_arm_il.md)）と
[Diffusion Policy](14_single_arm_il.md) の比較節へ。3 モデルで同じ評価プロトコルを回すのが
カリキュラム第 2〜4 章の到達点です。

---

## うまくいかないとき

| 症状 | 見る場所 |
|------|----------|
| Pi の `lerobot-rollout` が Illegal instruction | 想定どおり。この文書の Thor 経路を使う |
| Thor が `PolicyFeature] \| None is not callable` | `scripts/patch_draccus_py314.py` のあと、サーバを起動し直す |
| クライアントが `Failed to connect` | Thor が 8080 で待っているか。重みパスは Thor 側か |
| 腕が nest の近くで小さくしか動かない | 5° 制限の途中で止めていないか。目標姿勢そのものがポッドに向かっているか |
| 腕は大きく動くがポッドに届かない | デモの本数と、物体の位置が録画と同じか。5 本の重みでは届かない |
| 学習ディレクトリが root で読めない | 上の `chmod -R a+rX` |
| 切断したあと腕が落ちそう | `disable_torque_on_disconnect=false` を付けたか。外したら nest の前にトルクが切れる |
