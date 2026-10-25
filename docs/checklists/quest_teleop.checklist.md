# Quest テレオペ — 個人チェックリスト

正本手順: [11_quest_teleop_runbook.md](../11_quest_teleop_runbook.md)  
事前スクリプト: `./scripts/check_quest_teleop.sh <PiIP>`

```bash
cp docs/checklists/quest_teleop.checklist.md docs/checklists/quest_teleop.local.md
```

| 記録 | 値 |
|------|-----|
| 名前 / 日付 | |
| メインPC IP | |
| Pi IP | |
| Quest 機種 | Quest 3 / |
| 備考 | |

---

## 環境

- [ ] so101-lab を clone / pull 済み
- [ ] メインPC: teleop venv + `import isaaccapture` OK
- [ ] Pi: 双腕キャリブ済み（[04](../04_calibration.md)）
- [ ] フル LeLab / フル Web Remote を止めた
- [ ] `./scripts/check_quest_teleop.sh <PiIP>` で致命的 NG なし

メモ:

---

## Step 0 — Quest ↔ CloudXR（アームなし）

- [ ] `./scripts/start_quest_gripper_example.sh` 起動
- [ ] Meta Quest Browser で Connect（Firefox ではない）
- [ ] 右トリガで `Right:` が `1.00` ↔ `-1.00`

メモ:

---

## Step 1 — Bridge dry-run（アーム動かない）

- [ ] Pi: `./scripts/start_bridge_receiver.sh --dry-run -v`
- [ ] PC: `./scripts/start_bridge_sender_demo.sh <PiIP> --duration 10 -v`
- [ ] sender: connected / hello / ack
- [ ] Pi に受信ログ

メモ:

---

## Step 2 — Bridge 実機デモ（Quest なし）

- [ ] 腕の周りを空けた
- [ ] Pi: `./scripts/start_bridge_receiver.sh -v`
- [ ] PC: `./scripts/start_bridge_sender_demo.sh <PiIP> --duration 20 -v`
- [ ] 左右が微小に動く / home_pan 実測あり

メモ:

---

## Step 3 — cameras-only

- [ ] Pi: `./scripts/start_camera_server.sh`
- [ ] `/api/info` で `"cameras_only": true`
- [ ] center / wrist_follower / wrist_leader のストリーム確認

メモ:

---

## Step 4 — Quest ライブ（クラッチ・双腕・相対 EE）

- [ ] Pi: `BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v` + 任意で cameras-only
- [ ] PC: `./scripts/start_quest_bridge_live.sh <PiIP>`
- [ ] クラッチ無し → アーム動かない
- [ ] A/X 押しながら → **先端**が追従（向きは `motion.axis_map`）
- [ ] 離す → hold / 再押しでジャンプなし
- [ ] トリガでグリッパ
- [ ]（任意）Quest 内カメラプレーン or ログの MJPEG URL

メモ:

---

## Step 5 —（任意）JSONL

- [ ] `./scripts/record_quest_teleop_jsonl.sh`
- [ ] stats: valid / hz / gripper≈[0,1]

メモ:

---

## 完了

- [ ] 止める順: PC → Quest Disconnect → Pi camera → Pi bridge
- [ ] 問題があれば runbook のトラブル表 / [06](../06_troubleshooting.md) を更新提案

完了日:
