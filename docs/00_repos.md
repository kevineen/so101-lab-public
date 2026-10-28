# 00 — リポジトリ構成

ワークスペース全体の地図は [`~/robot/README.md`](../../../README.md) も参照（本ページは so101-lab 視点の詳細）。

## 全体像

```
~/robot/
  so101-lab/       ← 実験・運用のメイン（private: kevineen/so101-lab）★ここ
  lerobot/         ← LeRobot フォーク（kevineen/lerobot）。upstream は Hugging Face
  GR-BC/           ← GR-BC フォーク（kevineen/GR-BC, nview ブランチ）。VLA ポストトレーニング
  sim2rl/          ← シム・RL の教科書（強化学習・Sim2Real・論文 IL）
  LIBERO-plus/     ← LIBERO ベンチマークのフォーク（parc/ に PARC 競技ワークスペース）
  leisaac/         ← IsaacLab 拡張テンプレート（休止中 → ~/robot_archive へ退避済み）
  IsaacLab/        ← 上流クローン（変更しない）
  IsaacTeleop/     ← 上流クローン（変更しない）
  TurboVLA/        ← 上流クローン（VLA モデル・チェックポイント）
```

| パス | 役割 | GitHub |
|------|------|--------|
| `so101-lab/` | SO-101 ラボ（Web Remote、実験 apps、docs、configs）＋実機 IL 学習コース | `kevineen/so101-lab`（**private**） |
| `~/robot/lerobot/` | LeRobot 本体の作業コピー（venv・コアライブラリ）。FRS/TurboVLA 実験 | `kevineen/lerobot`（origin） |
| `GR-BC/` | GR-BC（失敗・介入含むロールアウトからの VLA ポストトレーニング）。fork の `nview` ブランチで 2 視点対応。環境は `.venv311`（[docs/26](26_grbc_posttraining.md)） | `kevineen/GR-BC`（fork） |
| `sim2rl/` | シミュレータ・強化学習・Sim2Real の学習・実験リポ（[docs/learn](../../sim2rl/docs/learn/README.md) と相互リンク） | `kevineen/sim2rl` |
| `LIBERO-plus/parc/` | PARC 競技ワークスペース（VR テレオペ、学習キュー、fleet、Web UI） | `kevineen/LIBERO-plus` |
| `leisaac/` | IsaacLab 拡張テンプレート（休止中） | `kevineen/leisaac` |

## so101-lab vs ~/robot/lerobot

- **so101-lab**: 実験コード（`apps/`）、起動スクリプト、yaml、ドキュメント、レポート。日常のラボ作業の入口。
- **~/robot/lerobot**: Hugging Face LeRobot のフォーク。コア API・ロボットドライバ・学習コード。**ワークスペース直下に clone する**（`vendor/` には置かない）。`so101-lab` のスクリプトからは `LEROBOT_DIR` 環境変数で参照する。

実験特化コード（SayCan / trainswap / experiment_report）は **so101-lab/apps** に置き、フォーク側には残さない（upstream への誤 push を避ける）。

## multi-PC セットアップ

典型例:

| マシン | 役割 |
|--------|------|
| Raspberry Pi | アーム・カメラ・Web Remote / LeLab LAN 公開。MolmoAct2 実機クライアント |
| Jetson Thor | 双腕 MolmoAct2 の GPU 推論（policy server）。手順は [10_molmoact2_thor.md](10_molmoact2_thor.md) |
| メインPC（NVIDIA GPU） | Isaac Teleop / CloudXR /（将来）ブリッジ送信・本格学習 |
| Meta Quest 3 | XR テレオペクライアント（コードは公式 Web クライアント） |
| WSL / デスクトップ PC | SayCan・CLIP・LLM（LM Studio）・軽量実験 |

Pi 上では `scripts/start_web_remote.sh` / `start_lelab_lan.sh` を使い、別 PC のブラウザから `http://<PiのLAN-IP>:8765`（Web Remote）または `:8000`（LeLab）を開く。

詳細（ポート・clone 先・同時起動ルール）: [07_multi_host.md](07_multi_host.md)  
Quest / Isaac Teleop: [08_quest_isaacteleop.md](08_quest_isaacteleop.md)  
将来ブリッジ: [09_bridge_contract.md](09_bridge_contract.md) · [`../bridges/`](../bridges/)  
双腕 MolmoAct2（Pi / Jetson Thor）: [10_molmoact2_thor.md](10_molmoact2_thor.md)

### 外部リポ（本リポに取り込まない）

| リポ | 役割 |
|------|------|
| [NVIDIA/IsaacTeleop](https://github.com/NVIDIA/IsaacTeleop) | Quest / CloudXR / retarget（メインPC で clone） |
| Hugging Face LeRobot（upstream） | `~/robot/lerobot` の取り込み元（push しない） |
| [isaac-sim/IsaacLab](https://github.com/isaac-sim/IsaacLab) | NVIDIA Isaac Lab（上流クローン。`leisaac` の母体） |

## Git 運用（重要）

1. **so101-lab** は private。`.venv`・データ成果物はコミットしない（`uv.lock` はコミットする）。
2. **~/robot/lerobot** の `origin` は `https://github.com/kevineen/lerobot`。コア変更や同期用。
3. **`upstream`（huggingface/lerobot）へは push しない。** 取り込みは `git fetch upstream` + merge/rebase のみ。

## ~/robot/lerobot の初期化

```bash
cd ~/robot
git clone https://github.com/kevineen/lerobot.git
cd lerobot
# 作業用 venv は lerobot/.venv に作成（uv sync）
# so101-lab のスクリプトからは LEROBOT_DIR=~/robot/lerobot で参照（未設定時のデフォルトも同じ）
```
