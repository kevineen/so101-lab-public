# isaacteleop_to_so101 — Phase D 双腕ブリッジ

Quest / Isaac Teleop（メインPC）→ 契約 JSON → Pi → 左右 SO-101。

搬送: **WebSocket + JSON**（`ws://<Pi>:8870/teleop`）  
契約: [docs/09_bridge_contract.md](../../docs/09_bridge_contract.md)

## 論理アーム ↔ 物理ポート

契約の `arm`（コントローラ左右）→ 物理ポートは [`configs/quest_teleop.yaml`](../../configs/quest_teleop.yaml) の `arm_resolve` で変更可。

| 契約 `arm` | ラボ既定（swap 後） | 物理 yaml |
|------------|---------------------|-----------|
| `left`（左コン） | `leader` | `robot.leader_arm` |
| `right`（右コン） | `follower` | `robot.follower_arm` |
| `single` | `follower` | 同上 |

元に戻す例:

```yaml
arm_resolve:
  left: follower
  right: leader
  single: follower
```

## 起動（Pi）

LeLab / Web Remote を止めてから:

```bash
# 実機
./scripts/start_bridge_receiver.sh

# シリアルなし疎通
./scripts/start_bridge_receiver.sh --dry-run -v
```

## Phase C — Quest → JSONL（Pi 不要）

```bash
# Meta Quest Browser で Connect したまま
./scripts/record_quest_teleop_jsonl.sh
# DURATION=30 ARMS=both ./scripts/record_quest_teleop_jsonl.sh data/quest_teleop/run.jsonl
```

写像: `from_retarget.py`（Isaac gripper -1/+1 → 契約 0/1）。詳細は [docs/09](../../docs/09_bridge_contract.md)。

## Phase D — Quest ライブ → Pi（クラッチ・双腕・カメラ）

手順の本体（Step 0〜4）: [docs/11_quest_teleop_runbook.md](../../docs/11_quest_teleop_runbook.md)

```bash
# 事前チェック（アームは動かさない）
./scripts/check_quest_teleop.sh ${SO101_PI_LAN_IP}

# Pi — 相対 EE（先端追従; placo + assets/robots/so101 必須）
BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
./scripts/start_camera_server.sh          # アームなし MJPEG（bridge と併用可）

# メインPC — Meta Quest Browser で Connect
# 既定: 双腕 / A(X) クラッチ握り中だけ追従 / トリガ=グリッパ
./scripts/start_quest_bridge_live.sh ${SO101_PI_LAN_IP}
```

設定: [`configs/quest_teleop.yaml`](../../configs/quest_teleop.yaml)（`motion.mode` / `axis_map` / `controls.*`）。  
`valid:false` で IK reset → クラッチ再押下で先端アンカー更新。

## 起動（メインPC / 任意ホスト）

```bash
# 双腕ジョイント正弦波（Quest 不要の E2E）
# 既定: 接続後に nest（Web Remote 初期位置）へ移動してからデモ開始
./scripts/start_bridge_sender_demo.sh <PiのIP> --duration 20

# nest をスキップ
GO_HOME=0 ./scripts/start_bridge_sender_demo.sh <PiのIP> --duration 20

# または
PYTHONPATH=. python -m bridges.isaacteleop_to_so101.sender \
  --host <PiのIP> --demo-bimanual --hz 30 --duration 20 --go-home
```

JSONL 再生:

```bash
python -m bridges.isaacteleop_to_so101.sender \
  --host <PiのIP> --jsonl path/to/cmds.jsonl --hz 30
```

## ペイロード

### EE（契約どおり）

```json
{
  "schema_version": "1.0",
  "timestamp_ns": 1710000000123456789,
  "frame_id": "teleop_left",
  "arm": "left",
  "ee_pose": {
    "position_m": [0.25, 0.02, 0.18],
    "quat_xyzw": [0.0, 0.0, 0.0, 1.0]
  },
  "gripper": 0.0,
  "valid": true
}
```

受信側デモ既定は `--ik approx`（相対 Δxyz → 肩/肘の微小更新）。  
Quest 本番は `BRIDGE_IK=relative`（FK tip0 + `axis_map(Δ)` + placo IK、URDF 既定 `assets/robots/so101/so101.urdf`）。  
絶対 EE: `--ik placo --urdf ...`（Quest 生 pose をロボット座標とみなす・校正なしでは非推奨）。

### 関節直指定（Phase D 検証用・推奨）

`joints`（度、gripper 0–100）があると IK をスキップします。

```json
{
  "schema_version": "1.0",
  "timestamp_ns": 1,
  "frame_id": "teleop_right",
  "arm": "right",
  "gripper": 0.4,
  "valid": true,
  "joints": {
    "shoulder_pan": -10.0,
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 40.0
  }
}
```

## 安全

| 事象 | 動作 |
|------|------|
| `valid: false` | その腕は hold（新規指令なし） |
| 受信タイムアウト（既定 200 ms） | hold |
| クライアント切断 | 全腕 hold |
| 関節リミット | clamp |

## テスト

```bash
cd ~/robot/so101-lab
PYTHONPATH=. ~/robot/lerobot/.venv/bin/python -m unittest \
  bridges.isaacteleop_to_so101.tests.test_contract \
  bridges.isaacteleop_to_so101.tests.test_receiver_dryrun -v
```

## Quest からの次ステップ

1. メインPCで Isaac Teleop `dex_bimanual_example.py` 等を動かす（[docs/08](../../docs/08_quest_isaacteleop.md)）
2. retarget 出力を左右の契約 JSON に写す薄いスクリプトを sender 前段に置く
3. 最初は `--dump /tmp/bridge.jsonl` でログ検証 → 低速実機
