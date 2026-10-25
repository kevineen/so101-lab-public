# 06 — トラブルシュート

## 別 PC からブラウザが開かない

```bash
ss -lntp | grep -E '8000|8765'
hostname -I
```

- `0.0.0.0:8000` / `0.0.0.0:8765` で待ち受けているか
- ファイアウォール（UFW）で LAN から許可しているか
- LeLab は公式 `lelab` ではなく `scripts/start_lelab_lan.sh` を使っているか

## Permission denied（シリアル）

```
PermissionError: ... /dev/serial/by-id/usb-1a86_...
```

```bash
sudo usermod -aG dialout <user>
# 再ログイン後:
groups   # dialout が含まれていること
```

一時回避（抜き差しで戻る）:

```bash
sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2
```

## OpenCV カメラが開けない

```
Failed to open OpenCVCamera(N)
```

- カメラが刺さっているか（`lsusb` / `ls /dev/video*`）
- `video` グループに入っているか
- yaml の `index` / `device` が合っているか → `lerobot-find-cameras opencv`

## ESP32 / Xiao の ttyACM0 をカメラに指定しても映らない

それは **シリアル**です。映像は Wi‑Fi の MJPEG を使います。

現行: `url: ${SO101_CAMERA_XIAO_URL}`（Xiao カメラサーバー）  
手順の詳細は [05_cameras.md](05_cameras.md)。

## Xiao / ESP32 のストリームが Web Remote に出ない

1. ブラウザで `${SO101_CAMERA_XIAO_URL}` が直接開けるか確認  
2. Pi から疎通: `ping -c 2 ${SO101_CAMERA_XIAO_IP}`  
3. yaml の `esp32cam.enabled: true` と `url:` が一致しているか  
4. Web Remote を再起動（設定は起動時に読み込む）  
5. IP が変わっている場合はルータ／シリアルログで再確認し、yaml を更新

## no calibration / has no calibration registered

初回キャリブが未実施です。[04_calibration.md](04_calibration.md)

```bash
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=${SO101_FOLLOWER_PORT} \
  --robot.id=my_follower
```

二臂なら `my_leader_drive` も同様に。

## 依存パッケージ不足（feetech / deepdiff / pyrealsense2）

`start_web_remote.sh` が不足分のインストールを試みます。手動の場合:

```bash
uv pip install --python "${LEROBOT_DIR:-$HOME/robot/lerobot}/.venv/bin/python" \
  feetech-servo-sdk pyserial deepdiff pyrealsense2 \
  fastapi "uvicorn[standard]" pyyaml
```

## LeLab が Python>=3.12 で入らない

```bash
uv tool install --python 3.12 git+https://github.com/huggingface/leLab.git
```

## アームが動かない（キャリブ済み）

- ESTOP が残っていないか（UI の **再開** → テレオペ ON）
- LeLab と二重起動していないか
- 正しい by-id ポートか（follower / leader の取り違え）

## leader の肘などが Overload / ランプ点滅

物理 leader を第2駆動腕にしていると、減速比が弱く過負荷しやすいです。詳細は [13_drive_profiles.md](13_drive_profiles.md)。

- **学習を進めるだけなら** Web Remote 第2腕を切る（`leader_arm.enabled: false`）→ [14_single_arm_il.md](14_single_arm_il.md)（デモは手テレオペ）
- ESTOP → 電源／USB でサーボをリセット → 端に押し込まない
- yaml の `leader_arm.drive_profile: gentle_7v4`（遅い追従）を確認
- 常用するなら第2腕を follower（できれば 12V）に換装し `drive_profile: full` へ。**7.4V モータに 12V を入れない**

## ゆっくり上げようとすると落下する

サーボの Acceleration を下げすぎると保持が弱く落ちます。現行の `gentle_7v4` は **step のみ制限**（加速度は既定）。  
Web Remote を再起動して最新プロファイルを入れてください。それでも落ちるならハードのトルク不足です → [13_drive_profiles.md](13_drive_profiles.md)
