# ロードマップ

`so101-lab` を唯一の入口とし、Pi 上の SO-101 運用と、メインPC + Quest 3 の Isaac Teleop、将来のブリッジを段階的に揃える。

関連: [07_multi_host.md](07_multi_host.md) · [08_quest_isaacteleop.md](08_quest_isaacteleop.md) · [09_bridge_contract.md](09_bridge_contract.md) · [11_quest_teleop_runbook.md](11_quest_teleop_runbook.md) · [10_molmoact2_thor.md](10_molmoact2_thor.md)

## フェーズ一覧

| Phase | 状態 | 目標 | 成果物 |
|-------|------|------|--------|
| **A** | 進行中 | ドキュメントでマシン分担と入口を一本化 | 本 roadmap、`07`〜`09`、`bridges/README` |
| **B** | 完了 | メインPCで Quest ↔ Isaac Teleop 単体成功 | `08` のメモ欄に版・IP を記入 |
| **C** | 完了 | retarget 出力を契約 JSON で可視化 | `record_quest` / `from_retarget` + `09` 表 |
| **D** | 完了（MVP+） | Pi へブリッジし SO-101 を動かす | demo + Quest live + クラッチ/双腕/cameras-only |
| **E** | 進行中 | データ収集・学習（当面は片腕 ACT / SmolVLA） | [17_act_record_train_infer.md](17_act_record_train_infer.md) · [14_single_arm_il.md](14_single_arm_il.md) |

## Phase A — ハブ化（今）

- [x] マルチホスト役割の文書化（`07`）
- [x] Quest / Isaac Teleop 手順の入口（`08`）
- [x] ブリッジ契約の先行定義（`09`）
- [x] `bridges/` プレースホルダ
- [x] README / docs 入口から辿れること

## Phase B — Quest 単体

- [x] メインPCに GPU 環境と `isaaccapture` を導入
- [x] CloudXR ポート開放、Quest から Connect（**Meta Quest Browser**。Firefox 不可）
- [x] `gripper_retargeting_example_simple.py` / `se3_retargeting_example.py`（choice 2）で入力確認
- [x] `08` の「ラボ固有メモ」を実値で更新

成功条件: **SO-101 なし**で、Quest 操作がメインPC上の retarget ログに出る。

## Phase C — 契約の検証

- [x] retarget 出力 → `09` の JSON への写像（`bridges/.../from_retarget.py` + `record_quest.py`）
- [x] 周波数・座標系・gripper 極性を `09` に記録
- [x] 実録 JSONL を 1 本以上残し、stats（hz / gripper 範囲）を確認（例: `data/quest_teleop/20261015_030059.jsonl`、hz≈27、gripper `[0,1]`）

成功条件: 実機を動かさずとも、「後で Pi が解釈できる指令列」がファイルに残る。

## Phase D — 実ブリッジ

- [x] 搬送手段を決定（WebSocket JSON / `:8870/teleop`）
- [x] メインPC sender / Pi receiver を `bridges/isaacteleop_to_so101/` に実装（双腕 `left`/`right`）
- [x] タイムアウト・切断時 hold（コード + dry-run テスト）
- [x] [07](07_multi_host.md) のポート表を実装値で更新
- [x] 実機で `--demo-bimanual` 低速追従を確認（Pi `${SO101_PI_LAN_IP}`、home_pan 実測あり）
- [x] Quest retarget → 契約 JSON の薄い前段（`record_quest` / `from_retarget`）
- [x] ライブ Quest → bridge（`scripts/start_quest_bridge_live.sh <PiIP>`）を実測
- [x] クラッチ追従 + YAML 入力マップ（`configs/quest_teleop.yaml`）
- [x] cameras-only サーバ + Quest Televiz プレーン（best-effort）
- [x] 相対 EE（グリッパ先端）追従: `RelativeEeIk` + `BRIDGE_IK=relative` + `assets/robots/so101`

成功条件: Quest → メインPC → Pi → SO-101 で低速追従できる。  
通し確認手順: [11_quest_teleop_runbook.md](11_quest_teleop_runbook.md)（Step 0→4）。  
相対 EE: クラッチ中にコントローラ Δ → 先端 Δ（`motion.axis_map` で軸合わせ）。  
当面の中間成功: **デモ sender → Pi → 双腕**（Quest なし）。  
この間 LeLab / Web Remote は起動しない。

## Phase E — データ・学習

当面の実行経路（ドキュメント済み）: **片腕 follower + ACT / SmolVLA** → [17_act_record_train_infer.md](17_act_record_train_infer.md)（学習は 4090、推論は Thor）。概念は [14_single_arm_il.md](14_single_arm_il.md)。  
データセットの作成・閲覧・編集: [15_dataset_pipeline.md](15_dataset_pipeline.md)。実施ログ: [作業レポート](reports/single_arm_il_work_report.md)。  
学習順の教科書: [learn/](learn/README.md)（sim2rl `docs/learn` と連携）。

- [x] 片腕 IL 手順書・チェックリスト（第2駆動腕 OFF・leader は手テレオペ）
- [x] `docs/learn/` 初学者カリキュラム（ACT→SmolVLA→他VLA→双腕地図）
- [x] データセット一連の手順と作業レポート雛形（録画本体は未実施）
- [ ] ラボで最初の ACT データセット（〜50 ep）と推論スモーク
- [ ] SmolVLA ファインチューン 1 本
- [ ] （任意）ブリッジ経由デモを LeRobot データセット形式へ
- [ ] 学習ホスト分担の実測メモ（メインPC GPU / Thor / HF Jobs）
- [ ] trainswap / SayCan（`apps/` `experiments/`）との関係整理

## 並行トラック（既存）

ブリッジと独立して進めてよいもの。

| 項目 | 参照 |
|------|------|
| LeLab / Web Remote 日常運用 | [01](01_overview.md)〜[06](06_troubleshooting.md) |
| 片腕 ACT / SmolVLA | [17_act_record_train_infer.md](17_act_record_train_infer.md) · [14_single_arm_il.md](14_single_arm_il.md) · [learn/](learn/README.md) |
| 双腕 MolmoAct2（Pi 制御 / Jetson Thor 推論） | [10_molmoact2_thor.md](10_molmoact2_thor.md) |
| カメラ拡充 | [05_cameras.md](05_cameras.md)、`configs/so101_dual_cam.yaml` |
| 代替: LeRobot WebXR 直結 | 旧 Phase 2 案。Isaac Teleop 経路と併記し、採用時は本 roadmap に追記 |

## やらないこと（当面）

- IsaacTeleop を本リポへ submodule / 巨大取り込み
- Raspberry Pi 上で CloudXR / Isaac Lab を動かす
- 契約（`09`）を飛ばして実機ブリッジを組む
