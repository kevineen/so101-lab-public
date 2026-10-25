# 10 — 双腕 MolmoAct2（Pi が実機、Jetson Thor が推論）

同一 LAN で役割を分ける。

| マシン | 持つもの | 持たないもの |
|--------|----------|--------------|
| **Raspberry Pi** | 両アームの USB シリアル、USB 先端カメラ 2 台、Xiao MJPEG の取得、行動の書き込み | MolmoAct2 の重み |
| **Jetson Thor** | MolmoAct2 の GPU 推論（gRPC policy server） | シリアル、カメラデバイス |

つなぎは `vendor/lerobot` の async inference です。Pi が観測を送り、Thor が行動チャンクを返します。Thor からカメラ URL や `/dev/ttyACM*` は開きません。

```
Pi  bi_so_follower
  カメラ 3 台 + 12 関節を読む
        │  画像・関節角・タスク文（gRPC, TCP 8080）
        ▼
Thor  policy server
  MolmoAct2
        │  行動チャンク
        ▼
Pi  が left_* / right_* の目標角度を両アームへ書く
```

LeLab（`:8000`）と Web Remote（`:8765`）は、このクライアントと同時に起動しません。USB シリアルとカメラを取り合います。Isaac Teleop ブリッジ受信とも同時に起動しません（[07_multi_host.md](07_multi_host.md)）。

## 両マシンへの clone

lerobot フォークは so101-lab の git に含まれません。Pi と Thor の両方で、同じコミットのフォークを別途 clone します。観測キーと行動の並びは Pi のロボット定義、前処理は Thor のポリシーコードなので、**lerobot のコミットを揃えます**。

```bash
git clone https://github.com/kevineen/so101-lab.git ~/robot/so101-lab
git clone https://github.com/kevineen/lerobot.git ~/robot/lerobot
```

詳細は [00_repos.md](00_repos.md)。

## 起動前: policy server が molmoact2 を拒否する

いまの `~/robot/lerobot/src/lerobot/async_inference/constants.py` の `SUPPORTED_POLICIES` は `act` や `pi05` までで、`molmoact2` がありません。このままクライアントが接続すると、サーバは `Policy type molmoact2 not supported` で落ちます。

Thor と Pi の両方のフォークで、`SUPPORTED_POLICIES` に `"molmoact2"` を足してから起動します。この変更は so101-lab ではなく `kevineen/lerobot` 側です。

サーバは `PolicyClass.from_pretrained(パス)` しか呼びません。載せる重みは LeRobot 形式のチェックポイントです。`allenai/MolmoAct2` を `checkpoint_path` と `norm_tag` だけで開く経路は、このサーバにはありません。チェックポイント側に `dtype=bfloat16` と `inference_action_mode=continuous` が入っていること。

クライアント CLI は `rename_map` をサーバへ渡しません。カメラのキー名を、チェックポイントが読む `observation.images.*` と一致させます。

## チェックポイント

公開重みを、この双腕 SO-101 にそのまま出しません。

| チェックポイント | 中身 | この機体 |
|------------------|------|----------|
| `lerobot/MolmoAct2-SO100_101-LeRobot` | 片腕 6 関節、カメラ `cam0` / `cam1` | 片腕の通信確認に使える。12 関節には使わない |
| `lerobot/MolmoAct2-BimanualYAM-LeRobot` | カメラ `top` / `left` / `right`、ロボットは YAM | 関節の次元と順番が SO-101 と違う |

双腕で出す重みは、下の「データ」で録った 12 次元データからファインチューンします。`control_mode` は `absolute joint pose`、`image_keys` は録画時のカメラキー、`setup_type` は双腕 SO-101 の説明にします。デモが少ないときは `train_mode_vlm=lora` または `freeze` にし、action expert は学習させます。学習フラグの一覧は `~/robot/lerobot/src/lerobot/policies/molmoact2/README.md` です。

このラボの現行キャリブ（LeRobot の degree 系）で録ったデータには、SO-100/101 旧チェックポイント用の `joint_signs` / `joint_offsets` を付けません。あの変換は先頭 6 関節だけが対象で、右腕には掛かりません。ベースを `MolmoAct2-SO100_101` にするときだけ、左右それぞれに同じ変換が要ります。

state / action の quantile がデータセットに無いときは、Thor で次を実行します。

```bash
python src/lerobot/scripts/augment_dataset_quantile_stats.py \
  --repo-id=<データセット> \
  --overwrite \
  --skip-images
```

## アームとキャリブレーション

推論クライアントのロボット型は `bi_so_follower` です。Web Remote が leader ポートを `so101_follower` として動かす構成とは別です。

`bi_so_follower` はキャリブファイルを次の名前で読みます（`name` は `so_follower`）。

```text
~/.cache/huggingface/lerobot/calibration/robots/so_follower/<robot.id>_left.json
~/.cache/huggingface/lerobot/calibration/robots/so_follower/<robot.id>_right.json
```

Web Remote 用の原本は残します（[04_calibration.md](04_calibration.md)）。

```text
my_follower.json       ← ポート ...<follower by-id 末尾>
my_leader_drive.json   ← ポート ...<leader by-id 末尾>
```

`--robot.id=so101_bi` にする場合、物理的な左右を見てコピーします。下は「follower を左、leader_drive を右」にした例です。設置が逆ならファイルと `left_arm_config` / `right_arm_config` のポートを入れ替えます。

```bash
cd ~/.cache/huggingface/lerobot/calibration/robots/so_follower
cp my_follower.json so101_bi_left.json
cp my_leader_drive.json so101_bi_right.json
```

行動ベクトルの順番は、左 6 関節のあとに右 6 関節です。各腕の中は `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper` です。キーは `left_shoulder_pan.pos` のように `.pos` が付きます。録画と推論で、このロボット定義を変えないでください。クライアントは返ってきたテンソルを、この順番のまま `send_action` します。

## カメラ

3 台とも **Pi が開き**、フレームだけ Thor へ送ります。`bi_so_follower` のトップレベル `cameras` に置くと、キーに `left_` / `right_` が付きません。腕の `cameras` に入れると `left_wrist` のように付くので、チェックポイントの `top` / `left` / `right` とは一致しません。

現行のデバイスは [`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml) と同じです。

| キー（チェックポイントに合わせる） | 実体 |
|------------------------------------|------|
| `top` | Xiao MJPEG `${SO101_CAMERA_XIAO_URL}`（fps 15） |
| `left` | follower 側先端 USB。by-path `...usb-0:1.2.4.1:1.0-video-index0`、MJPG |
| `right` | leader_drive 側先端 USB。by-path `...usb-0:1.2.4.4:1.0-video-index0`、MJPG |

左右の先端を入れ替えるときは、上のキャリブと同じ向きにキーも入れ替えます。USB カメラの権限は [05_cameras.md](05_cameras.md) です。

`OpenCVCameraConfig.index_or_path` の注釈は `int | Path` です。Web Remote は HTTP URL を **str のまま**渡して開いています（`web_remote/web_remote/config.py`）。robot client の CLI が URL を `Path` にすると `http://` が `http:/` になり、OpenCV が開けません。ログにスラッシュ 1 本の URL が出たら、その正規化が原因です。

## Thor（先に起動）

MolmoAct2 の追加依存を入れます。

```bash
cd ~/robot/lerobot
uv sync --locked --extra molmoact2
```

`pyproject.toml` の Linux 向け torch は `download.pytorch.org` の cu128 です。これはデスクトップ GPU 向けなので、Thor では JetPack に合う CUDA 版 torch を使います。確認:

```bash
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`True` と Thor の GPU 名が出てからサーバを起動します。重みは Thor のディスク（または Thor から届く Hugging Face）に置きます。Pi はモデルを読みません。

```bash
uv run python -m lerobot.async_inference.policy_server \
  --host=0.0.0.0 \
  --port=8080 \
  --fps=30 \
  --obs_queue_timeout=5
```

`--host=0.0.0.0` にしないと Pi から届きません。ファイアウォールを使う場合は、Pi のアドレスから TCP 8080 だけを許可します。

```bash
sudo ufw allow from <PiのIP> to any port 8080 proto tcp
```

`--pretrained_name_or_path` はクライアントが送る文字列で、**Thor 上で解決**されます。Hub id なら Thor がダウンロードし、ローカルパスならそのパスが Thor に存在する必要があります。

## Pi（サーバのあと）

クライアントは Thor の IP へ接続します。`actions_per_chunk` はチェックポイントの `n_action_steps` に合わせます（LIBERO 系の例は 10）。`max_relative_target` は 1 制御周期あたりの最大移動量（degree）です。最初は 5 のままにします。

```bash
cd ~/robot/lerobot
uv run python -m lerobot.async_inference.robot_client \
  --robot.type=bi_so_follower \
  --robot.id=so101_bi \
  --robot.left_arm_config.port=${SO101_FOLLOWER_PORT} \
  --robot.right_arm_config.port=${SO101_LEADER_PORT} \
  --robot.left_arm_config.max_relative_target=5 \
  --robot.right_arm_config.max_relative_target=5 \
  --robot.cameras='{
      top: {type: opencv, index_or_path: "${SO101_CAMERA_XIAO_URL}", width: 640, height: 480, fps: 15},
      left: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30, fourcc: MJPG},
      right: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30, fourcc: MJPG}
  }' \
  --task="pick up the object and hand it to the other gripper" \
  --server_address=<THORのIP>:8080 \
  --policy_type=molmoact2 \
  --pretrained_name_or_path=<Thorで解決できるLeRobotチェックポイント> \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=10 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30
```

Pi の制御周期は `--fps`（例: 30）です。MolmoAct2 の 1 回の推論はそれより遅いので、行動キューが `chunk_size_threshold` を下回ったときだけ次の観測を送ります。観測は非圧縮の pickle です。640×480 が 3 枚で 1 回あたり約 2.7MB なので、Pi と Thor の間は有線ギガビットにします。

両機の時刻は `chrony` で揃えます。クライアントを止めると `disable_torque_on_disconnect`（既定 true）でトルクが外れます。

### 推論後に初期位置へ戻す

1. 事前に Web Remote で安全姿勢にして **「初期位置を保存」**（`~/.cache/so101-lab/home_poses.json`）
2. Web Remote を止めてからクライアントを起動
3. 終了後に nest へ戻す:

```bash
# 手動
./scripts/go_so101_home.sh

# または client 終了（Ctrl+C 含む）で自動復帰
./scripts/run_molmoact2_client.sh \
  --server_address=<THORのIP>:8080 \
  --pretrained_name_or_path=<チェックポイント> \
  --task="pick up the object and hand it to the other gripper" \
  --policy_device=cuda
```

`GO_HOME=0 ./scripts/run_molmoact2_client.sh ...` で自動復帰をスキップできます。  
ラッパーは `disable_torque_on_disconnect=false` を付けて切断時の落下を避け、その後 `go_so101_home.sh` で nest へ寄せます。

## 片腕で通信だけ確認する

双腕のファインチューン前に、経路だけ確かめるときは片腕と `lerobot/MolmoAct2-SO100_101-LeRobot` を使います。カメラキーは `cam0` / `cam1` に合わせ、`policy_type=molmoact2` と `SUPPORTED_POLICIES` の追加は双腕と同じです。この重みを `bi_so_follower` の 12 関節には接続しません。

## 切り分け

1. Pi だけで Web Remote が両アームと 3 カメラを開ける（このクライアントは止めた状態）。
2. Thor で `torch.cuda.is_available()` が true。
3. Pi から `nc` または同等で Thor の TCP 8080 に届く。
4. サーバログにクライアント接続が出る。`molmoact2 not supported` なら、上の allowlist が未反映。
5. 観測送信後に `Action chunk` のログが出てから、`max_relative_target=5` のまま実機を動かす。
