# 01 — 全体概要

## 何ができるか

| 役割 | ツール | URL（例） |
|------|--------|-----------|
| キャリブ・leader テレオペ・録画・学習・推論 | **LeLab** | `http://<PiのIP>:8000/` |
| ブラウザのスライダー／スティックで腕を動かす + カメラ映像 | **Web Remote** | `http://<PiのIP>:8765/` |

Pi の LAN IP 確認:

```bash
hostname -I
```

例: `${SO101_PI_LAN_IP}`

リポジトリの関係（so101-lab / ~/robot/lerobot / sim2rl ほか）は [00_repos.md](00_repos.md) を参照。  
マニュアル索引: [manual.md](manual.md) · ブラウザ閲覧: `make docs-serve`

## ディレクトリ構成（so101-lab）

```
so101-lab/
  apps/                 ← SayCan / trainswap / experiment_report（実験コード）
  bridges/              ← Isaac Teleop → SO-101（未実装・契約は docs/09）
  configs/              ← so101_dual_cam.yaml
  data/                 ← 手動メモ・データ（gitignore 対象あり）
  docs/                 ← 本マニュアル
  experiments/          ← so101_trainswap 設定・環境例
  notes/                ← CLI チートシート等
  reports/              ← 旧実験メモ（新規は docs/reports/）
  docs/reports/         ← 提出用作業レポート（更新管理）
  scripts/              ← start_lelab_lan.sh / start_web_remote.sh
  web_remote/           ← Web Remote 本体
  ~/robot/lerobot/      ← フォークした LeRobot（.venv 含む・ワークスペース直下に別 clone）
```

同階層の `~/robot/AmazingHand/` は別プロジェクト（本リポジトリでは触れない）。

## 役割分担

1. **日常の手動操作（ブラウザから関節操作）** → Web Remote  
2. **データ収集・学習・推論・公式フロー** → LeLab  
3. **どちらか一方だけ起動する**（同じシリアル／カメラを奪い合うため）  
4. **Quest / Isaac Teleop（メインPC）** → [08_quest_isaacteleop.md](08_quest_isaacteleop.md)（SO-101 未接続の検証から）  
5. **将来の XR → 実機** → [09_bridge_contract.md](09_bridge_contract.md)
6. **双腕 MolmoAct2（推論は Jetson Thor）** → [10_molmoact2_thor.md](10_molmoact2_thor.md)
7. **第2腕が物理 leader のとき / 12V follower 換装** → [13_drive_profiles.md](13_drive_profiles.md)
8. **片腕 ACT / SmolVLA（第2駆動腕 OFF）** → 通し手順 [17_act_record_train_infer.md](17_act_record_train_infer.md) · 概念 [14_single_arm_il.md](14_single_arm_il.md)
9. **初学者カリキュラム（概念→ACT→VLA→双腕）** → [learn/](learn/README.md)

マルチホスト全体: [07_multi_host.md](07_multi_host.md) · 進捗: [roadmap.md](roadmap.md)

## 同時起動禁止

LeLab と Web Remote を同時に動かさないでください。両方とも follower / leader の USB シリアルとカメラを開きます。  
将来の bridge 受信、および Thor 推論用の robot client とも同時起動しない（[07](07_multi_host.md)、[10](10_molmoact2_thor.md)）。

## 今後の方針（未実装含む）

| 目標 | 方針 |
|------|------|
| カメラ構成の拡充 | LeLab UI + `so101_dual_cam.yaml` を揃える |
| Quest 3 + Isaac Teleop | メインPC で単体成功 → 契約検証 → `bridges/`（[roadmap](roadmap.md)） |
| 代替: LeRobot WebXR 直結 | `bi_so_follower` + WebXR。Isaac 経路と併記し、採用時に roadmap へ追記 |
| データセット／学習／推論 | **当面は片腕**（[17](17_act_record_train_infer.md): 4090 で学習、Thor で推論、Pi は腕）。概念は [14](14_single_arm_il.md)。双腕 MolmoAct2 は [10](10_molmoact2_thor.md) |
