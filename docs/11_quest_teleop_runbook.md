# 11 — Quest テレオペ動作確認ランブック（順を追う）

メインPC + Quest 3 + Pi（双腕 SO-101）で、**いま動く経路**を段階確認する。  
前提セットアップ: [08_quest_isaacteleop.md](08_quest_isaacteleop.md)。契約: [09_bridge_contract.md](09_bridge_contract.md)。マシン分担: [07_multi_host.md](07_multi_host.md)。

設定: [`../configs/quest_teleop.yaml`](../configs/quest_teleop.yaml)

**個人の進捗記録:** テンプレをコピーして手元でチェックする（gitignore 済み）。

```bash
cp docs/checklists/quest_teleop.checklist.md docs/checklists/quest_teleop.local.md
```

詳細: [checklists/README.md](checklists/README.md)

## 事前チェック

| 項目 | 確認 |
|------|------|
| メインPC IP | 例: `${SO101_MAINPC_LAN_IP}`（`hostname -I`） |
| Pi IP | 例: `${SO101_PI_LAN_IP}` |
| Quest | **Meta Quest Browser**（Firefox 不可） |
| 同時起動禁止 | フル LeLab / フル Web Remote は止める（アーム二重制御） |
| 併用可 | bridge 受信 + **cameras-only**（`start_camera_server.sh`） |

```bash
# メインPC — 事前チェック（アームは動かさない）
./scripts/check_quest_teleop.sh ${SO101_PI_LAN_IP}
# または手動:
ping -c 1 ${SO101_PI_LAN_IP}
```

`check_quest_teleop.sh` は config / venv / `isaaccapture` / Pi 疎通 / ポート解放状況を表示する。  
ポートが closed の note は「まだ起動していない」だけで、次の Step で起動すればよい。

---

## Step 0 — Quest ↔ CloudXR（アームなし）

**目的:** ヘッドセット入力がメインPCに届くこと。

```bash
# メインPC
# so101-lab リポジトリ直下で実行
./scripts/start_quest_gripper_example.sh
```

Quest: `https://${SO101_MAINPC_LAN_IP}:48322/client/` → 証明書受理 → Server IP → **Connect**  
右トリガ: ターミナルの `Right:` が `1.00`（開）↔ `-1.00`（閉）。

| OK | NG |
|----|----|
| Connect 後に値が変わる | Connect 不可 → ポート / 同一 LAN / Browser |
| | 値が常に `1.00` → Quest 未接続 |

---

## Step 1 — Bridge 疎通（dry-run・アーム動かない）

**目的:** メインPC → Pi の WebSocket 契約だけ通す。

```bash
# Pi
# so101-lab リポジトリ直下で実行
./scripts/start_bridge_receiver.sh --dry-run -v
# 「bridge listening ... dry_run=True」を確認。このまま待つ。
```

```bash
# メインPC（別ターミナル）
# so101-lab リポジトリ直下で実行
./scripts/start_bridge_sender_demo.sh ${SO101_PI_LAN_IP} --duration 10 -v
```

| OK | NG |
|----|----|
| sender: `connected` / `hello` / `ack ... left|right` | `ConnectionRefused` → Pi で receiver が動いていない |
| Pi: 受信ログ | IP 誤り |

終わったら Pi で Ctrl+C。

---

## Step 2 — Bridge 実機デモ（Quest なし）

**目的:** 双腕がゆっくり動くこと。腕の周りを空けてから。

```bash
# Pi
./scripts/start_bridge_receiver.sh -v
```

```bash
# メインPC
./scripts/start_bridge_sender_demo.sh ${SO101_PI_LAN_IP} --duration 20 -v
```

| OK | NG |
|----|----|
| 左右アームが微小に追従 | シリアル / キャリブ → [04](04_calibration.md) [06](06_troubleshooting.md) |
| hello に `left_home_pan` 等の実測値 | LeLab / Web Remote がまだ動いている |

---

## Step 3 — cameras-only（アームなし映像）

**目的:** Pi が MJPEG を出すこと（bridge と併用可）。

```bash
# Pi（bridge と別ターミナルで可）
./scripts/start_camera_server.sh
```

ブラウザ（PC でも Quest Browser でも）:

- `http://${SO101_PI_LAN_IP}:8765/api/info` → `"cameras_only": true` とカメラ名
- `http://${SO101_PI_LAN_IP}:8765/api/stream/center`
- `http://${SO101_PI_LAN_IP}:8765/api/stream/wrist_follower`
- `http://${SO101_PI_LAN_IP}:8765/api/stream/wrist_leader`

| OK | NG |
|----|----|
| 映像が出る | tip カメラ権限 / by-path → [05_cameras.md](05_cameras.md) |
| センターを D435 に | Pi: `CENTER_SOURCE=d435 ./scripts/start_camera_server.sh`（ストリーム名は `center` のまま） |
| | フル Web Remote と競合していないか |

---

## Step 4 — Quest ライブ（クラッチ・双腕・相対 EE）

**目的:** ボタン握り中だけ、**グリッパ先端がコントローラ相対移動に追従**。  
既定クラッチ = **右 A / 左 X**（`primary_click`）。  
IK: Pi で `BRIDGE_IK=relative`（FK tip0 + `axis_map` + placo）。要 `placo` と [`assets/robots/so101/so101.urdf`](../assets/robots/so101/so101.urdf)。

準備:

1. Pi: `BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v`（実機）
2. Pi: `start_camera_server.sh`（任意・映像用）
3. Quest: Meta Quest Browser で Connect（Step 0 と同じクライアント）
4. メインPC:

```bash
# so101-lab リポジトリ直下で実行
./scripts/start_quest_bridge_live.sh ${SO101_PI_LAN_IP}
# 既定は無制限（Ctrl+C で停止）。短時間試験: DURATION=60 ./scripts/...
# 接続直後に nest へ移動（既定 ON）。スキップ: GO_HOME=0 ./scripts/...
```

接続成功後、PC ログに `Requesting nest go_home` → `Nest done` が出てからクラッチ操作。  
（先に Web Remote で片腕ずつ初期位置を保存しておく。未保存腕は 0° 寄り。）

操作チェック:

| 操作 | 期待 |
|------|------|
| A（右）/ X（左）を**押さない** | アーム動かない。ログ `clutch=off` `valid=False` |
| 押しながらコントローラをゆっくり動かす | **先端**が同じ向きに動く。`clutch=ON` `valid=True` |
| 離す | その場で hold |
| 手を動かしてから再び押す | ジャンプせず追従再開（アンカー更新） |
| トリガ | グリッパ開閉 |
| ログの Camera URL | Pi MJPEG。Televiz 成功なら Quest 内プレーン |

| OK | NG |
|----|----|
| クラッチ無しで動かない | 常時追従 → 古いスクリプト / yaml 未読込 |
| 双腕それぞれ独立 | 片側だけ → `--arms` / yaml `arms` |
| 先端がコントローラと同方向 | 軸逆 → 下の `axis_map` |
| | ConnectionRefused → Step 1 に戻る |
| | `ImportError` / URDF なし → Pi に placo + `assets/robots/so101` |

### 開始前に空中 nest へ（推奨）

下がった姿勢から動かすと机に当たりやすい。Web Remote で **片腕ずつ** 空中姿勢を保存してから:

```bash
# Web Remote で follower / leader タブ → 選択腕の初期位置を保存 → Web Remote 停止
./scripts/go_so101_home.sh              # または --arm follower / leader
BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
```

### Quest 内で設定を触る（操作しながら）

CloudXR 没入中は YAML を触れないので、**設定 UI を Quest Browser で開く**:

```bash
# メインPC（live と別ターミナル）— Pi IP を渡すと保存が bridge に即反映
./scripts/start_quest_teleop_settings.sh ${SO101_PI_LAN_IP}
# → http://<メインPCのIP>:8766/
```

1. Quest で CloudXR をメニュー／一時退出  
2. Meta Quest Browser で上記 URL  
3. 感度・軸反転・safety・tip Z → **保存**（Pi へ WebSocket で push）  
4. CloudXR に戻って続きを操作（receiver 再起動不要）  

ローカル控え: `configs/quest_teleop.local.overrides.yaml`（gitignore）。

### ソフト可動範囲（机・自分・もう一方の腕）

モーターのキャリブ範囲とは別に、[`quest_teleop.yaml`](../configs/quest_teleop.yaml) の `safety:` で制限できる（上書き UI または yaml。Pi はホットリロード可）。

| 項目 | 内容 |
|------|------|
| `soft_joint_limits_deg` | 関節ごとのソフト min/max（度）。腕別 `follower`/`leader` 可 |
| `tip_bounds_m` | 先端 XYZ の箱（ロボットベース m） |
| `enabled: false` | 一時オフ |

当たる方向だけ狭める。例: 内側に振りすぎる → その腕の `shoulder_pan` 上限／下限を寄せる。  
nest 姿勢が箱の外だと、旧実装ではクラッチ直後に箱へ引き込まれ（奥行き無効・下方向など）に見えた。相対 EE は tip0 を箱に含めてクランプする。  
**注意:** AABB／関節クランプであり、リンク同士の衝突判定ではない。双腕を大きく交差させない運用＋ nest を空中に置くこと。

### 軸合わせ（相対 EE）

1 軸ずつコントローラを動かして、[`quest_teleop.yaml`](../configs/quest_teleop.yaml) の `motion.axis_map` だけ直す（Pi 再起動で読込）。

```yaml
motion:
  mode: relative_ee
  pos_scale: 0.5            # 動きを半分に
  axis_map:
    x: x       # または -x / y / -z など
    y: -y
    z: z
```

設定変更例:

```yaml
# 左右コントローラ ↔ 腕（右コンで follower にしたいとき）
arm_resolve:
  left: leader
  right: follower

controls:
  clutch: secondary_click   # B / Y
  gripper: thumbstick_y     # 後でスティックにする場合
```

---

## Step 5 —（任意）JSONL 録画のみ

アーム不要。契約ログの再確認。

```bash
# メインPC — Quest Connect 済み
./scripts/record_quest_teleop_jsonl.sh
# 終了後 stats: valid / hz / gripper=[0,1]
```

---

## ワンショット起動順（本番）

```text
Pi #1:  BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
Pi #2:  ./scripts/start_camera_server.sh
Quest:  Meta Quest Browser → Connect
PC:     ./scripts/start_quest_bridge_live.sh <PiのIP>
```

止める順: PC（Ctrl+C）→ Quest Disconnect → Pi camera → Pi bridge。

---

## トラブル早見

| 症状 | 対処 |
|------|------|
| Connect 灰色 | Meta Quest Browser・証明書・capability check（[08](08_quest_isaacteleop.md)） |
| 時間が経つと Connect 画面に戻る | Quest クライアントの Auto Refresh → **Never**（[08](08_quest_isaacteleop.md) 長時間セッション）。スリープ／Wi‑Fi／PC 側停止も確認 |
| sender ConnectionRefused | Pi receiver 起動中か、IP、`:8870` |
| アーム動かないがログは ON | クラッチは押しているが `valid=False` → トラッキング喪失（コントローラ見失い） |
| 常に動く | `quest_teleop.yaml` が読まれているか。起動ログの `Clutch:` 行 |
| 動きの向きが逆 | `motion.axis_map` の符号・入替（Step 4） |
| 奥手前だけ死ぬ／クラッチで下へ引き込まれる | nest 先端が `tip_bounds_m` 外 → 旧ハードクランプの症状。現行は tip0 込みクランプ。それでもおかしいなら bounds を広げるか `safety.enabled: false` で切り分け |
| 先端ではなく関節が勝手に動く感 | Pi が `BRIDGE_IK=relative` か（`approx` だとヒューリスティック） |
| nest すぐ soft 関節に吸われる | `soft_joint_limits_deg` が nest より狭い → 幅を nest が入るように広げる |
| カメラだけ出ない | Step 3。Televiz 失敗時はログ URL をブラウザで確認 |
| Web Remote と bridge 同時 | **禁止**（cameras-only は可） |

---

## 関連スクリプト

| スクリプト | 役割 |
|------------|------|
| `scripts/start_quest_gripper_example.sh` | Step 0 |
| `scripts/start_bridge_receiver.sh` | Pi 受信 |
| `scripts/start_bridge_sender_demo.sh` | Step 1–2 |
| `scripts/start_camera_server.sh` | Step 3 |
| `scripts/start_quest_bridge_live.sh` | Step 4 |
| `scripts/record_quest_teleop_jsonl.sh` | Step 5 |
| `scripts/check_quest_teleop.sh` | 事前チェック自動化（アーム非操作） |
