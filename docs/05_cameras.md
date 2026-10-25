# 05 — カメラ

設定は [`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml) の `cameras:` です。  
オフラインや `enabled: false` のカメラは **スキップ**され、アームだけ起動できます。

## センターカメラ切替（Xiao / D435）

Web Remote・cameras-only・Quest Televiz が参照する論理名は常に **`center`** です。  
実カメラは `center_source`（または環境変数）で切り替えます。

| 指定 | 実体 | yaml キー |
|------|------|-----------|
| `xiao`（既定） | Xiao MJPEG | `center_xiao` |
| `d435` | RealSense D435 | `center_d435` |

```bash
# データ収集などで D435 を論理センターにする（1 回だけ）
CENTER_SOURCE=d435 ./scripts/start_camera_server.sh
CENTER_SOURCE=d435 ./scripts/start_web_remote.sh

# 既定を変える場合は yaml:
#   center_source: d435
```

論理センターのストリーム URL: `http://<Pi>:8765/api/stream/center`  
（Quest の `quest_teleop.yaml` も名前 `center` のままでよい）

### D435 深度プレビュー（Web Remote）

配置確認用に、深度をカラーマップ（TURBO）した MJPEG を追加表示できます。

| yaml | 意味 |
|------|------|
| `use_depth: true` | RealSense の depth ストリームを開く |
| `preview: true` | `center_source` が xiao のときも D435 を副映像として開く |

| 起動条件 | RGB | 深度（色付け） |
|----------|-----|----------------|
| 既定（`center_source: xiao` + `preview: true`） | `/api/stream/d435` | `/api/stream/d435_depth` |
| `CENTER_SOURCE=d435` | `/api/stream/center` | `/api/stream/center_depth` |

ブラウザ UI は `/api/info` のカメラ一覧に合わせてタイルを出します。深度は可視化用で、学習データセットの観測キーにはしません（録画は [14](14_single_arm_il.md) の `lerobot-record`）。

## 権限（USB / V4L）

```bash
sudo usermod -aG video <user>
sudo usermod -aG dialout <user>   # アーム用シリアルも必要
```

グループ反映には **再ログイン**（または `newgrp video`）が必要です。

## 普通の USB Webカメラ / アーム先端（wrist ×2）

両アームとも先端に **Innomaker U20CAM** を想定。yaml キーは:

| キー | アーム | 備考 |
|------|--------|------|
| `wrist_follower` | follower | 現在接続済みの1台 |
| `wrist_leader` | leader | 2台目を挿して `device:` を書いて `enabled: true` |

同一型番でシリアルが同じ（`SN0001`）だと `by-id` が衝突しやすいので、**USB ポート固定の `by-path`** を使います。

```yaml
wrist_follower:
  class: OpenCVCamera
  enabled: true
  device: /dev/v4l/by-path/platform-...-video-index0
  fps: 30
  width: 640
  height: 480

wrist_leader:
  class: OpenCVCamera
  enabled: true
  device: /dev/v4l/by-path/platform-...-video-index0   # もう一方のポート
  fps: 30
  width: 640
  height: 480
```

デバイス確認:

```bash
ls -l /dev/v4l/by-id/ /dev/v4l/by-path/ | grep -iE 'innomaker|video-index0'
lsusb | grep -i microdia
```

`Permission denied` / `Failed to open OpenCVCamera` のときは `video` グループ不足が多いです:

```bash
sudo usermod -aG video <user>
# 再ログイン後: groups | grep video
# すぐ試すだけなら（抜き差しで戻る）:
sudo chmod 666 /dev/video0 /dev/video1   # 2台目が増えたらその番号も
```

## Xiao / ESP32 カメラサーバー（Wi‑Fi MJPEG）

Seeed XIAO（ESP32-S3 Sense 等）や ESP32-CAM の **カメラ Web サーバー**は、同じ LAN 上の MJPEG URL として扱います。  
設定クラスはどちらも `OpenCVCamera` + `url:` です。

### 現行ラボ構成（2026-09）

| 項目 | 値 |
|------|-----|
| ボード | Xiao カメラサーバー |
| IP | `${SO101_CAMERA_XIAO_IP}` |
| ストリーム URL | `${SO101_CAMERA_XIAO_URL}` |
| yaml キー | `center_xiao`（`center_source: xiao` で論理名 `center`） |

```yaml
center_xiao:
  class: OpenCVCamera
  enabled: true
  url: ${SO101_CAMERA_XIAO_URL}
  fps: 15
  width: 640
  height: 480
```

IP やポートが変わったら、yaml の `url:` だけ直して Web Remote / LeLab を再起動します。

### 接続前の確認

1. Xiao と Pi が **同じ Wi‑Fi / LAN** にいること  
2. ブラウザでストリームが開くこと:

```text
${SO101_CAMERA_XIAO_URL}
```

3. 映らない場合はファームによりパスが違うことがある（例: `http://${SO101_CAMERA_XIAO_IP}/` やポート `80`）。**ブラウザで映る URL をそのまま `url:` に書く**

### USB 直結だけでは映像は取れない

Pi に見える次のデバイスは **カメラではありません**（シリアル／JTAG）:

```
usb-Espressif_USB_JTAG_serial_debug_unit_... -> /dev/ttyACM0
```

これは書き込み・ログ用です。UVC の `/dev/video*` にはなりません（UVC ファームを焼いた ESP32-S3 等は例外）。  
USB ケーブルは給電用のままで問題ありません。映像は HTTP 経由です。

### IP の探し方（DHCP が変わったとき）

1. シリアルモニタ（多くの場合 115200 baud）で起動ログの IP を見る  
2. ルータの DHCP 一覧で `espressif` / `ESP` / `XIAO` を探す  
3. （参考）LAN の `:80` / `:81` をスキャン  

見つかり次第、yaml の `url: http://<新しいIP>:81/stream` を更新します。

## RealSense D435

現行ラボ（2026-10、Pi USB3）:

| 項目 | 値 |
|------|-----|
| 機種 | Intel RealSense D435 |
| シリアル | `${SO101_REALSENSE_SERIAL}` |
| yaml キー | `center_d435`（`center_source: d435` で論理名 `center` に載る） |
| USB | 3.x 必須（帯域。ハブ経由なら USB3 ポート側） |

```yaml
center_d435:
  class: RealSenseCamera
  enabled: true
  serial_number: "${SO101_REALSENSE_SERIAL}"
  fps: 30
  width: 640
  height: 480
  use_depth: true
  preview: true   # xiao センターのまま d435 / d435_depth も表示
```

確認:

```bash
# USB 認識
lsusb | grep -i RealSense

# シリアル（lab venv）
# so101-lab リポジトリ直下で実行
~/robot/lerobot/.venv/bin/python -c \
  'import pyrealsense2 as rs; print([d.get_info(rs.camera_info.serial_number) for d in rs.context().query_devices()])'

# LeRobot ヘルパー（PATH にある場合）
lerobot-find-cameras realsense
```

依存: `pyrealsense2`（Web Remote 起動スクリプトが足りなければ自動インストールを試みます）。

## 無効化

```yaml
some_cam:
  enabled: false
  ...
```

使わないカメラは `enabled: false` にしておくと、起動時の待ち時間やエラーを減らせます。
