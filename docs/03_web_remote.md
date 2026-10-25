# 03 — Web Remote（ブラウザ遠隔操作）

leader アームを手で動かさず、別 PC のブラウザから関節を操作し、カメラ映像を見ます。  
**1臂または 2臂**（follower + leader ポート）に対応しています。

## 起動

```bash
./scripts/start_web_remote.sh
```

環境変数（任意）:

| 変数 | 既定 | 意味 |
|------|------|------|
| `WEB_REMOTE_CONFIG` | `configs/so101_dual_cam.yaml` | 腕とカメラの yaml |
| `WEB_REMOTE_HOST` | `0.0.0.0` | 待受アドレス |
| `WEB_REMOTE_PORT` | `8765` | 待受ポート |
| `LEROBOT_DIR` | `~/robot/lerobot` | LeRobot フォークのチェックアウト |
| `WEB_REMOTE_CONTROL_HZ` | `40` | 高速側の制御周期。慎重側は 20Hz |
| `TYPESAFE_API_KEY` | 未設定 | あるときだけ、判断が曖昧な場面でテキスト Jev にモードを聞く |

追加引数の例:

```bash
# 片腕のみ
./scripts/start_web_remote.sh --no-leader

# キャリブ id を明示
./scripts/start_web_remote.sh --robot-id my_follower --leader-id my_leader_drive
```

別 PC: `http://<PiのIP>:8765/`

Quest テレオペ中にカメラだけ欲しい場合（アームは bridge が占有）:

```bash
./scripts/start_camera_server.sh
# = start_web_remote.sh --cameras-only
```

フル Web Remote と bridge は同時起動しない。cameras-only は bridge と併用可。

**LeLab と同時起動しないでください。**

## UI 機能

- アーム切替タブ（`follower` / `leader`）
- カメラ MJPEG
- 6 関節スライダー（選択中アーム）
- 仮想スティック（shoulder_pan / shoulder_lift）
- **入力モード切替**（オフ / ゲームパッド / キーボード）
- **Bluetooth / USB ゲームパッド**（ブラウザ Gamepad API）
- **キーボード操作**＋キー割当て設定画面（クリックしてキー押下で変更）
- 共通パラメータ（最大°/送信・グリッパ速度・送信間隔）とパッド用デッドゾーン — `localStorage` に保存
- **Calibration パネル**（指定モータの range_min/max・中点・保存）
- **ESTOP**（両腕トルクオフ） / **再開**（ESTOP 解除。続けてテレオペ ON で操作）
- 同時操作クライアントは 1 つのみ

leader ポートも内部的には **so101_follower として位置制御**します（詳細は [04_calibration.md](04_calibration.md)）。

## 入力モード

画面の **オフ / ゲームパッド / キーボード** ボタンで切り替えます（同時有効にはなりません）。

### ゲームパッド

コントローラーは **ブラウザを開いている PC** にペアリングします（Pi 側の Bluetooth は不要）。  
Chrome / Edge 等でページを開き、パッドの任意ボタンを一度押すと認識されます。

| 入力 | 動作 |
|------|------|
| 左スティック Y | 選択中関節を比例ジョグ |
| 右スティック Y | グリッパ比例ジョグ |
| 十字 ← / → | 関節選択（ハイライト） |
| LB / RB | アーム切替 |
| A | グリッパ全開⇔全閉 |
| Y | ホーム相当（関節 0、グリッパ 50） |
| Back + B | ESTOP（同時押し） |

### キーボード（既定割当て）

| キー | 動作 |
|------|------|
| ↑ / ↓ | 選択関節 + / - |
| ← / → | 関節選択 |
| Q / E | グリッパ閉 / 開 |
| `,` / `.` | アーム切替 |
| G | グリッパ開閉トグル |
| H | ホーム相当 |
| Space | ESTOP |

キー列のボタンをクリック → 新しいキーを押すと割当て変更。Esc でキャンセル、Backspace で未割当。「既定に戻す」で初期化。設定はブラウザの `localStorage` に保存されます。  
スライダー操作中などフォームにフォーカスがあるときはキーボード操作を無効化します。

### 共通パラメータ

| 項目 | 既定 | 意味 |
|------|------|------|
| デッドゾーン | 0.18 | スティック中立の不感帯（ゲームパッド時のみ） |
| 最大°/送信 | 3.0 | フル倒し／キー押し時、1 送信あたりの関節変化 |
| グリッパ速度 | 5.0 | 同上（グリッパ単位） |
| 送信間隔 ms | 50 | 連続入力の送信周期 |

## yaml の二臂設定

[`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml):

```yaml
robot:
  follower_arm:
    port: ${SO101_FOLLOWER_PORT}
    drive_profile: full          # 本物の follower（7.4V / 12V とも）
  leader_arm:
    enabled: false               # 片腕 IL 暫定（トルク不足）。ACT/VLA → docs/14
    port: ${SO101_LEADER_PORT}
    drive_profile: gentle_7v4    # enabled:true で物理 leader を暫定駆動するとき。換装後は full

# センター切替: xiao | d435（環境変数 CENTER_SOURCE でも可）
center_source: xiao
```

### drive_profile（腕ごとの速度 / 加速度）

| 値 | 用途 |
|----|------|
| `full`（別名 `follower_12v`） | 通常の駆動腕。第2腕を **12V follower に換装したら leader 側もこれ** |
| `gentle_7v4` | 物理 leader（7.4V・肘 1:191）を第2駆動腕にする暫定。step のみ制限（加速度は保持のため既定のまま） |

詳細・換装手順・チューニング: **[13_drive_profiles.md](13_drive_profiles.md)**  
（ソフトで定格トルクは上がらない。**7.4V モータに 12V を入れない。**）

D435 の RGB＋深度プレビュー（配置確認）: 既定 yaml で `d435` / `d435_depth` が並びます。論理センターを D435 にする例: `CENTER_SOURCE=d435 ./scripts/start_web_remote.sh`（`center` / `center_depth`）。詳細は [05_cameras.md](05_cameras.md)。

## API 概要

| Method | Path | 説明 |
|--------|------|------|
| GET | `/` | UI |
| GET | `/api/info` | アーム名・関節名・カメラ名・リミット・`drive_profiles` |
| GET | `/api/state` | 接続状態・各アームの目標／現在角・teleop・estop・`rate_mode` / `control_hz` / `scene` / `drive_profiles` |
| POST | `/api/action` | `{ "arm": "follower"\|"leader", "joints": { ... } }`（ヘッダ `X-Client-Token`） |
| GET | `/api/stream/<cam>` | MJPEG |
| POST | `/api/teleop` | `{ "enabled", "arm"? }` ON=そのアームだけトルク＋操作 / 他腕はトルクOFF |
| GET | `/api/home` | 保存済み初期位置（nest） |
| POST | `/api/home/save` | `{ "arm"? }` 現在姿勢を初期位置に保存（省略時は両腕） |
| POST | `/api/home/go` | `{ "arm"? }` 初期位置へ徐々に戻る（省略時は両腕） |
| POST | `/api/estop` | 非常停止（両腕・トルク OFF・teleop も OFF） |
| POST | `/api/estop/clear` | 再開（ESTOP 解除のみ。トルクは OFF のまま → テレオペ ON で復帰） |
| POST | `/api/release` | クライアント制御権の解放 |

## 初期位置（nest） {#nest}

安全な姿勢にアームを置いて保存すると、`~/.cache/so101-lab/home_poses.json` に腕ごとに記録されます（片腕ずつ可・他腕は上書きしない）。

| UI / キー | 動作 |
|-----------|------|
| 選択腕の初期位置を保存 | **選択中タブの腕だけ**現在角を保存（merge） |
| 両腕の初期位置を保存 | follower + leader の現在角をまとめて保存 |
| 初期位置へ戻る / `H` / パッド Y | 選択中アームだけ nest へ |
| 両腕を初期位置へ | follower + leader を同時に nest へ |

未保存の腕は従来どおり **0° / グリッパ 50** に戻します。復帰中はテレオペより優先され、到達後はその姿勢で保持します。  
Web Remote を止めたあと（MolmoAct2 推論後など）は同じファイルを使えます:

```bash
./scripts/go_so101_home.sh              # 両腕
./scripts/go_so101_home.sh --arm follower
./scripts/go_so101_home.sh --arm leader
```

データセット録画では、この nest で両腕を揃えてから `lerobot-record` を起動します。エピソードの開始角そのものは、録画開始時の leader の関節角です。手順は [15 — 初期位置](15_dataset_pipeline.md#initial-pose)。
| GET | `/api/calibration?arm=` | キャリブ JSON＋（モード中は）生エンコーダ |
| POST | `/api/calibration/enter` | キャリブ開始（トルク OFF） |
| POST | `/api/calibration/drive` | ブラウザ駆動 ON/OFF（トルク ON でジョグ可） |
| POST | `/api/calibration/jog` | raw エンコーダ差分で選択モータを動かす |
| POST | `/api/calibration/mid` | 選択モータの中点（half-turn homing） |
| POST | `/api/calibration/capture` | 現在位置を `range_min` / `range_max` に |
| POST | `/api/calibration/range/start` \| `stop` | 手動かし／ジョグで min/max を連続記録 |
| POST | `/api/calibration/update` | 数値の手動編集 |
| POST | `/api/calibration/save` \| `cancel` | 保存（JSON＋モータ）／復元 |

## ブラウザでグリッパー min/max を直す

1. 上タブで **follower**（または leader）を選択  
2. 画面下部 **Calibration** で `gripper` にチェック  
3. **キャリブ開始** → そのアームはトルク OFF（手で動かせる）  
4. 手で動かしにくい場合は **ブラウザ駆動 ON** → ステップを選び ± でジョグ（押しっぱなし可）。全軸を現在位置でホールドし、位置リミットは一時的に全開  
5. 閉じた位置で **現在を min**、開いた位置で **現在を max**（逆でも可）  
6. 表の数値を直接編集してもよい  
7. **保存して終了** → `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json` とモータへ書き込み、トルク復帰  

範囲記録スタート／ストップでも、手動かジョグで動かした間の最小・最大をまとめて取れます。`wrist_roll` はフル回転のため 0–4095 固定で、UI 上は約 ±180°（ほぼ1回転）まで動かせます。中点設定時はブラウザ駆動が OFF に戻ります。

## 速度の切替（40Hz / 20Hz）

モーター周期は起動時に固定しません。センターカメラ `center` を約 5Hz で見て、操作の大きさと合わせて次のどちらかにします。画面上部に「40Hz 高速」または「20Hz 慎重」と出ます。

| モード | 周期 | 1ティックの追従上限 | いつ |
|--------|------|----------------------|------|
| cruise | 40Hz（`WEB_REMOTE_CONTROL_HZ`） | 30° | 近くに物がなく、操作量が大きい |
| approach | 20Hz | 12° | 物に近い、画面の端、または関節がキャリブ範囲の端 |

カメラ読みはモーター周期とは別です。映像が遅いときも 40Hz の送信を待ちません。判定が数回続き、直前の切替から 0.4 秒以上たってから周期が変わります。見えていないだけの `unknown` では 20Hz に落としません。

知覚の結果は `SceneState`（`motion` / `proximity` / `workspace` / `source` / `summary`）です。いまの `source` は `center_cv` です。後から画像を見るモデルを足すときは、同じ型を `source=image_jev` で書けば、ルーターと 40Hz / 20Hz のエキスパートはそのまま使えます。

`TYPESAFE_API_KEY` があるとき、上のどちらでもない灰色の判断だけテキストの Jev（`jev-1.13.0`）に `cruise` か `approach` を聞きます。キーが無い、遅い、信頼度が低いときはローカルの判断を維持します。Jev は関節角度を出しません。

## ソース配置

```
web_remote/
  web_remote/
    config.py       # yaml → 腕・カメラ設定
    session.py      # 接続・モーター周期・カメラ周期・ESTOP
    scene_state.py  # 知覚の共通の型（画像 Jev もここへ書く）
    center_watch.py # センターカメラ → SceneState
    rate_router.py  # 40Hz / 20Hz の切替
    jev_router.py   # 灰色のときだけテキスト Jev
    server.py       # FastAPI
    static/index.html
```
