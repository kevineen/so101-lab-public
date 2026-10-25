# 09 — ブリッジ契約（Isaac Teleop → SO-101）

**実装ステータス: Phase D 最小実装あり**（WebSocket JSON・双腕）。  
コード: [`../bridges/isaacteleop_to_so101/`](../bridges/isaacteleop_to_so101/)。  
起動: `scripts/start_bridge_receiver.sh`（Pi）/ `scripts/start_bridge_sender_demo.sh`（送信側）。

全体の流れは [07_multi_host.md](07_multi_host.md)。Quest 単体セットアップは [08_quest_isaacteleop.md](08_quest_isaacteleop.md)。

## 目的

```
Quest 3 → CloudXR → メインPC (IsaacTeleop retarget)
                         │
                         │  本契約のペイロード
                         ▼
                    Pi (bridge 受信) → LeRobot / SO-101 follower
```

メインPC は「人間の XR 入力 → 標準化されたロボット指令」までを担当し、  
Pi は「指令 → 実機関節」だけを担当する。

## 設計原則

1. **制御の単一所有者** — bridge 稼働中は LeLab / Web Remote を起動しない（[07](07_multi_host.md)）
2. **契約を先に固定** — 搬送手段（WebSocket / ROS 2）は後から選んでよいが、ペイロード形は変えない
3. **安全側に倒す** — タイムアウト・切断時は指令を止め、アームは hold（またはサイト方針の安全停止）
4. **IsaacTeleop 本体は fork しない** — 変換ロジックだけを `bridges/` に置く

## 論理インタフェース

### 入力（メインPC側が生成）

Isaac Teleop の retarget 出力を、ラボ共通の指令に正規化する。

| フィールド | 型 | 意味 |
|------------|-----|------|
| `schema_version` | string | 例 `"1.0"` |
| `timestamp_ns` | int | 送信側モノトニックまたは壁時計（実装で明記） |
| `frame_id` | string | 例 `"teleop_right"` / `"world"`（座標系は実装時に固定） |
| `arm` | string | `"left"` \| `"right"` \| `"single"` |
| `ee_pose` | object | `{ "position_m": [x,y,z], "quat_xyzw": [x,y,z,w] }` |
| `gripper` | float | `[0.0, 1.0]`（0=開、1=閉。実装で確認） |
| `valid` | bool | トラッキング喪失時は `false` |

周波数の目安: **30–50 Hz**（実測で調整。遅延より欠落検知を優先）。

絶対 pose（`ee_pose`）を第一候補とする。相対指令が必要なら `mode: "absolute" | "delta"` を後から追加し、`schema_version` を上げる。

### 出力（Pi 側が実行）

| 出力 | 内容 |
|------|------|
| LeRobot アクション | SO-101 の関節目標（または公式アクション空間） |
| ログ | 受信 JSON をファイル / stdout に残し、契約検証に使う |

IK / 関節変換の詳細は実装時に `bridges/isaacteleop_to_so101/` に置く。契約上は「Pi が EE+gripper を受け取り、安全な関節指令にする」ことだけを保証する。

## 搬送

**採用: WebSocket + JSON**（Phase D）。

```text
ws://<PiのIP>:8870/teleop
```

| 候補 | 向き | 状態 |
|------|------|------|
| WebSocket（JSON） | メインPC → Pi | **現行** |
| ROS 2 topic | メインPC → Pi | 将来候補 |
| gRPC / protobuf | 同上 | 将来候補 |

ポート `8870` は [07](07_multi_host.md) の表に記載。

## ペイロード例（schema 1.0）

```json
{
  "schema_version": "1.0",
  "timestamp_ns": 1710000000123456789,
  "frame_id": "teleop_right",
  "arm": "single",
  "ee_pose": {
    "position_m": [0.25, 0.02, 0.18],
    "quat_xyzw": [0.0, 0.0, 0.0, 1.0]
  },
  "gripper": 0.0,
  "valid": true
}
```

## 失敗時の振る舞い

| 事象 | 受信側（Pi）の動作 |
|------|-------------------|
| `valid: false` | 新規指令を適用しない（最後の安全姿勢を保持） |
| 受信タイムアウト（例: 200 ms） | hold。連続タイムアウトで切断扱い |
| スキーマ不正 / 版不一致 | ログして破棄。アームは hold |
| 送信側プロセス終了 | 同上 |
| 関節限界・速度限界 | Pi 側で clamp。超過をログ |

送信側（メインPC）は、トラッキングロスト時に必ず `valid: false` を出すか、送信を止める（どちらにするかを実装 PR で明記）。

## 検証手順（コード前〜コード後）

### Phase C（契約の机上・ログ検証）

1. メインPCで retarget 例を動かす（[08](08_quest_isaacteleop.md)）— **済**（gripper / SE3 controller abs）
2. 出力を上記 JSON 形に変換し、ファイルへダンプ:
   ```bash
   # Quest を Meta Quest Browser で Connect した状態で
   ./scripts/record_quest_teleop_jsonl.sh
   # または: DURATION=30 ARMS=right ./scripts/record_quest_teleop_jsonl.sh data/quest_teleop/run.jsonl
   ```
   変換コード: [`from_retarget.py`](../bridges/isaacteleop_to_so101/from_retarget.py) / [`record_quest.py`](../bridges/isaacteleop_to_so101/record_quest.py)
3. 座標系・gripper 極性・周波数（下表）

| 項目 | Phase C 実測・決定 |
|------|-------------------|
| `timestamp_ns` | 送信側 **壁時計** `time.time_ns()` |
| `frame_id` | `teleop_left` / `teleop_right`（Quest OpenXR デバイス系。SO-101 base への固定変換は未） |
| `arm` | 既定録画は `right`（右コントローラ）。双腕は `ARMS=both` |
| gripper 極性 | Isaac `GripperRetargeter`: **-1=閉 / +1=開** → 契約 **0=開 / 1=閉**（`(1 - isaac) / 2`） |
| `ee_pose` | SE3 **absolute** controller → `[x,y,z,qx,qy,qz,qw]` をそのまま `position_m` + `quat_xyzw` |
| `valid` | 位置ノルム ≲ 1e-3 m（原点パーキング）なら `false` |
| 周波数 | 録画既定 **30 Hz**（`--hz`）。実測は JSONL 末尾の stats 行を参照 |

### Phase D（実ブリッジ）

1. [x] `bridges/isaacteleop_to_so101/` に送信側・受信側の最小実装
2. Pi では Web Remote / LeLab を止め、`./scripts/start_bridge_receiver.sh`
3. まず `./scripts/start_bridge_sender_demo.sh <PiIP>` で双腕ジョイント追従
4. 切断・タイムアウト試験（`--cmd-timeout`）を必ず実施
5. [x] Quest retarget → 契約 JSON 前段（`record_quest`）
6. [x] ライブ Quest → bridge（`live_quest` / `scripts/start_quest_bridge_live.sh`）を実測

### Phase D+ — クラッチ・双腕・カメラ

**通しの動作確認（推奨）:** [11_quest_teleop_runbook.md](11_quest_teleop_runbook.md)（Step 0→4）  
事前チェック: `./scripts/check_quest_teleop.sh [PiIP]`

設定: [`configs/quest_teleop.yaml`](../configs/quest_teleop.yaml)

| 操作 | 既定 | 変更 |
|------|------|------|
| クラッチ（追従中のみ） | `primary_click`（右 A / 左 X） | yaml `controls.clutch`（`secondary_click` / `squeeze_value` 等） |
| グリッパ | `trigger_value` | yaml `controls.gripper`（後で `thumbstick_y` 可） |
| 離したとき | `valid: false` → Pi hold + IK reset（再掴みでアンカー更新） | — |
| 双腕 | yaml `arms: [left, right]` | CLI `--arms` |
| 相対 EE（先端追従） | `motion.mode: relative_ee` + Pi `BRIDGE_IK=relative` | `axis_map` / `pos_scale` |
| 感度 | `motion.pos_scale`（relative 時は Pi 側） / 受信 `--max-step-deg`（approx） | — |

カメラ（Pi アームと分離）:

```bash
# Pi（bridge と同時可）— 相対 EE は placo + URDF 必須
BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
./scripts/start_camera_server.sh          # :8765 cameras-only

# メインPC
./scripts/start_quest_bridge_live.sh ${SO101_PI_LAN_IP}
```

Quest 内プレーンは Televiz で Pi MJPEG（`/api/stream/<name>`）を表示（失敗時は URL をログ）。

## 置き場

```
bridges/
  README.md
  isaacteleop_to_so101/   ← sender (メインPC) / receiver (Pi)
```

IsaacTeleop・LeRobot 本体のコピーは置かない。薄いアダプタのみ。

## 決定済み / 残り

- [x] 搬送手段: WebSocket JSON（`8870/teleop`）
- [x] 1臂 / 2臂: `arm` = `left`→follower / `right`→leader / `single`→follower
- [x] gripper: 契約 `[0,1]` → LeRobot 度モード gripper `[0,100]`（開=0 側）
- [x] タイムアウト: 受信側既定 200 ms で hold
- [x] `frame_id` 命名: `teleop_<arm>`（Quest デバイス系。SO-101 base 校正は未）
- [x] クラッチ追従 + YAML 入力マップ（`quest_teleop.yaml`）
- [x] cameras-only HTTP（bridge 併用）+ Quest Televiz プレーン（best-effort）
- [x] 相対 EE 先端追従（`RelativeEeIk` + `assets/robots/so101` + `motion.axis_map`）。絶対空間校正（方式 B）は未
- [x] 本格 IK 経路（`--ik relative|placo` + URDF）。デモは引き続き `--ik approx` / `joints` 可
- [ ] 認証の要否（現状 LAN 内限定）
- [ ] 録画（LeLab dataset）との同時運用方針

### 過渡フィールド `joints`（schema 1.0）

Quest / placo IK 前に双腕 E2E を通すため、任意で `joints`（度）を載せてよい。  
ある場合は受信側が EE→IK をスキップする。デモ sender（`--demo-bimanual`）はこの経路。
