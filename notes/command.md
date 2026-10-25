# コマンド早見表 — 片腕 IL（コブラ／スネークボウル）

クローン直後の初期設定（1回だけ）:

```bash
cd ~/robot/so101-lab
cp configs/lab.local.env.example configs/lab.local.env
# → 自分の IP・アームの by-id パス・カメラのシリアルを書く
#   （docs/00_repos.md の LeRobot フォークも ~/robot/lerobot に配置）
```

以下のコマンドは `set -a && source configs/lab.local.env && set +a` を先に実行しておくと
`${SO101_*}` が展開されてそのまま貼り付けられる（録画・推論スクリプト自体も自動 source する）。

## 1. データセット録画（コブラ → 銀ボウル）

```bash
cd ~/robot/so101-lab
# activate 不要。録画スクリプトが ~/robot/lerobot/.venv を自動で使う

TASK="Grab the cobra by the neck and put its whole body inside the silver bowl."
# RGB のみのデータセットと特徴量が違うので、深度ありは repo_id を分ける
REPO_ID=local/so101_singlearm_pickup_cobra_depth

./scripts/record_with_buttons.sh \
  --robot.type=so101_follower \
  --robot.port=$SO101_FOLLOWER_PORT \
  --robot.id=my_follower \
  --teleop.type=so101_leader \
  --teleop.port=$SO101_LEADER_PORT \
  --teleop.id=my_leader \
  --robot.cameras="{ \
    front: {type: intelrealsense, serial_number_or_name: \"$SO101_REALSENSE_SERIAL\", width: 424, height: 240, fps: 15, use_depth: true}, \
    wrist: {type: opencv, index_or_path: \"$SO101_WRIST_FOLLOWER_DEVICE\", width: 640, height: 480, fps: 30, fourcc: MJPG} \
  }" \
  --display_data=false \
  --dataset.repo_id=$REPO_ID \
  --dataset.num_episodes=50 \
  --dataset.fps=15 \
  --dataset.episode_time_s=30 \
  --dataset.reset_time_s=15 \
  --dataset.single_task="$TASK" \
  --dataset.push_to_hub=false \
  --dataset.streaming_encoding=false \
  --dataset.encoder_threads=2
```

`use_depth: true` で `front`（RGB）と `front_depth`（深度 mm）を記録。8770 は `front_depth` を疑似カラー表示。開始待ちは既定で leader 追従。「両方 nest へ」トグルで両腕を nest に動かして保持（機能自体の無効化: `SO101_RECORD_GO_HOME=0`）。  
`streaming_encoding=false` は録画中のエンコード負荷を避けて追従を優先（エピソード終了後の保存は長め）。ストリーミングに戻すときは `true` を明示。  
カメラは Pi 4 向けに **front 424×240@15（深度）+ wrist 640×480@30 MJPG**（制御は `dataset.fps=15`）。wrist 機種によっては 320 幅と 15 fps を拒否するものがあり、その場合は 640@30 のままにする。まだカクつくときは Cadence の `observe` を見る。

録画データの閲覧・選別（curate）は [docs/15_dataset_pipeline.md](../docs/15_dataset_pipeline.md)、
HF Hub への公開／取得は [docs/25_dataset_model_release.md](../docs/25_dataset_model_release.md)。

## 2. 推論（policy server 方式）

まずモデルを保持する policy server（GPU 側）を立てる:

```bash
# サーバー側（GPU / WSL）
cd ~/robot/lerobot
uv run --no-sync python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 --port=8080 --fps=30 --obs_queue_timeout=5
```

```bash
# クライアント側（Pi）
cd ~/robot/so101-lab
LEROBOT_DIR=~/robot/lerobot \
SO101_INFER_TRIALS=10 SO101_INFER_TIMEOUT_S=60 \
./scripts/infer_with_buttons.sh \
  --robot.type=so101_follower \
  --robot.port=$SO101_FOLLOWER_PORT \
  --robot.id=my_follower \
  --robot.max_relative_target=5 \
  --robot.disable_torque_on_disconnect=false \
  --robot.cameras='{ front: {type: intelrealsense, serial_number_or_name: "$SO101_REALSENSE_SERIAL", width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: "$SO101_WRIST_FOLLOWER_DEVICE", width: 640, height: 480, fps: 30} }' \
  --server_address=${SO101_GPU_TAILSCALE_IP}:8080 \
  --policy_type=act \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=100 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  --task="Pick the red neck of snake and place drop in the silver bowl"
```

- モデルの切り替えはスマホ UI から。カタログは `configs/infer_models.local.json`（無ければ example の `configs/infer_models.snakebowl.json`）。`path` は **policy server 側ホスト**のチェックポイント。`$HOME/robot/lerobot/outputs/train/...` 形式で書ける（クライアントとサーバでユーザー名が違うならサーバ側の実パスを書く）
- 1モデルを直接指定するときは `--pretrained_name_or_path=<サーバ側の絶対パス>` を足す

録画→学習→推論の一連の正本: [docs/17_act_record_train_infer.md](../docs/17_act_record_train_infer.md) · 学習は `./scripts/train_mlflow.sh`（[docs/16_local_mlflow.md](../docs/16_local_mlflow.md)）
