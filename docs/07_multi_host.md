# 07 — マルチホスト構成（Pi / Jetson Thor / メインPC / Quest）

このラボは **1 つの GitHub（`so101-lab`）を入口**にし、役割の違うマシンを組み合わせて運用する。

**エージェント用 PC 構成（単一ファイル）**: [`configs/lab_hosts.yaml.example`](../configs/lab_hosts.yaml.example) をコピーして各自設定する。

```bash
cp configs/lab_hosts.yaml.example configs/lab_hosts.yaml
# this_host と hosts.*.network（IP / SSH）を編集。lab_hosts.yaml は gitignore
```

人間向けの手順・独占ルールはこの文書と [23](23_data_transfer.md) が正。

## マシン役割

| マシン | 役割 | このリポで触るもの |
|--------|------|-------------------|
| **Raspberry Pi** | SO-101・カメラ・LeLab / Web Remote。MolmoAct2 の実機クライアント | `scripts/` `web_remote/` `configs/` `~/robot/lerobot/` |
| **Jetson Thor** | 双腕 MolmoAct2 と片腕 ACT / pi05 等の GPU 推論 | [10](10_molmoact2_thor.md) · [17](17_act_record_train_infer.md) · [21](21_pi05_thor.md)。`policy_server` |
| **メインPC（NVIDIA GPU）** | Isaac Teleop / CloudXR。WSL（3090/4090）で片腕 IL 学習 | [08](08_quest_isaacteleop.md)、[17](17_act_record_train_infer.md)、[23 転送](23_data_transfer.md) |
| **Meta Quest 3** | XR テレオペクライアント | 接続手順のみ（アプリは公式 Web クライアント） |
| （任意）WSL / 別 PC | SayCan・CLIP・LLM・軽量実験 | `apps/` `experiments/` |

詳細なリポジトリ関係は [00_repos.md](00_repos.md)。ロードマップは [roadmap.md](roadmap.md)。  
データセットとチェックポイントの送り方は **[23_data_transfer.md](23_data_transfer.md)**。

## データ／制御の流れ（現状と将来）

```
【現状】
  ブラウザ ──HTTP──▶ Pi (LeLab :8000 / Web Remote :8765) ──▶ SO-101

【MolmoAct2】
  Pi（カメラ・両アーム）──gRPC :8080──▶ Jetson Thor（推論）
        ▲                                    │
        └──────── 行動チャンク ──────────────┘
  手順: docs/10

【片腕 IL（ACT / SmolVLA / Diffusion / pi05 等）】
  Pi（録画）──データセット──▶ GPU WSL（lerobot-train）
  GPU ──pretrained_model──▶ Jetson Thor（policy_server）
  Pi（カメラ・follower）──gRPC :8080──▶ Thor
  手順: docs/17 · docs/21 · **転送の正本: docs/23**

【将来（Phase D）】
  Quest 3 ──CloudXR──▶ メインPC (IsaacTeleop retarget)
                              │
                              │ bridge（契約: docs/09）
                              ▼
                         Pi (so101-lab) ──▶ SO-101
```

## どのマシンに何を clone するか

### Raspberry Pi（必須）

```bash
# ラボ入口
git clone https://github.com/kevineen/so101-lab.git ~/robot/so101-lab
git clone https://github.com/kevineen/lerobot.git ~/robot/lerobot
# venv 等は docs/00_repos.md 参照（uv sync --extra feetech）
```

起動:

- Web Remote → `./scripts/start_web_remote.sh` → `http://<PiのIP>:8765`
- LeLab → `./scripts/start_lelab_lan.sh` → `http://<PiのIP>:8000`

### Jetson Thor（MolmoAct2 推論）

Pi と同じく `so101-lab` と lerobot フォーク（`~/robot/lerobot`）を clone する。起動手順・ポート・チェックポイントの制約は [10_molmoact2_thor.md](10_molmoact2_thor.md)。

### メインPC（Quest / Isaac Teleop 用）

```bash
# 手順・契約・将来ブリッジの入口として同じリポを clone
git clone https://github.com/kevineen/so101-lab.git ~/robot/so101-lab

# Isaac Teleop 本体は外部（本リポには取り込まない）
git clone https://github.com/NVIDIA/IsaacTeleop.git ~/robot/IsaacTeleop
```

セットアップは [08_quest_isaacteleop.md](08_quest_isaacteleop.md)。

### Quest 3

コードの clone は不要。ブラウザで CloudXR.js クライアントを開き、メインPC の IP を入力する（[08](08_quest_isaacteleop.md)）。

## ポート一覧

| 用途 | ホスト | ポート | 備考 |
|------|--------|--------|------|
| LeLab | Pi | TCP 8000 | LAN からブラウザ |
| Web Remote | Pi | TCP 8765 | LAN からブラウザ |
| MolmoAct2 policy server | Jetson Thor | TCP 8080 | Pi の robot client から。手順は [10](10_molmoact2_thor.md) |
| CloudXR media | メインPC | UDP 47998 | Quest ↔ メインPC |
| CloudXR signaling | メインPC | TCP 49100 | 同上 |
| CloudXR WSS / cert | メインPC | TCP 48322 | HTTPS・証明書受理 |
| Quest→SO-101 bridge | Pi | TCP 8870 | WebSocket `ws://<Pi>:8870/teleop`（[09](09_bridge_contract.md)） |
| cameras-only MJPEG | Pi | TCP 8765 | bridge 併用可。`/api/stream/<name>`（[09](09_bridge_contract.md)） |
| MLflow UI | GPU ホスト | TCP 5000 | 学習曲線。Docker で `./scripts/start_mlflow.sh`（[16](16_local_mlflow.md)）。別 PC から見るときはこのポートを開ける |

Pi 側のファイアウォールを使う場合は 8000 / 8765 / 8870 を許可する。  
Thor の policy server（TCP 8080）は Pi からだけ開ける。例は [10](10_molmoact2_thor.md)。  
メインPC側の CloudXR 用ポート開放例:

```bash
sudo ufw allow 47998/udp
sudo ufw allow 49100,48322/tcp
```

## 同時起動・資源の独占ルール

| 組み合わせ | 可否 | 理由 |
|------------|------|------|
| LeLab ↔ Web Remote | **禁止** | USB シリアル・カメラを奪い合う |
| LeLab / Web Remote ↔ MolmoAct2 robot client | **禁止** | 同じシリアル・カメラを奪い合う（[10](10_molmoact2_thor.md)） |
| Web Remote ↔ bridge 受信 | **禁止** | 同じ follower を二重制御する |
| **cameras-only** Web Remote ↔ bridge 受信 | **可** | アームシリアルは触らない（`./scripts/start_camera_server.sh`） |
| LeLab ↔ bridge 受信 | **禁止** | 同上 |
| MolmoAct2 robot client ↔ bridge 受信 | **禁止** | 同じアームを二重制御する |
| メインPC の IsaacTeleop 単体 | 可 | SO-101 未接続の検証用 |
| Quest ↔ メインPC（SO-101 なし） | 可 | Phase B の目標 |
| bridge 受信（`start_bridge_receiver.sh`） | 可 | Web Remote / LeLab 停止後のみ |

将来ブリッジ稼働中は **Pi 上の制御入口は bridge のみ**とする。詳細は [09_bridge_contract.md](09_bridge_contract.md)。

## ネットワーク前提

- Pi・Jetson Thor・メインPC・Quest は同一 LAN（またはルーティング可能なセグメント）にあること
- Quest は安定した 5 GHz Wi‑Fi を推奨（CloudXR の帯域のため）
- Pi の IP 確認: `hostname -I`

## トラブル時の切り分け順

通しの動作確認は [11_quest_teleop_runbook.md](11_quest_teleop_runbook.md)（Step 0→4）。

1. Pi だけで Web Remote / LeLab が動くか（[06_troubleshooting.md](06_troubleshooting.md)）
2. メインPC だけで IsaacTeleop の例が動くか（[08](08_quest_isaacteleop.md)）
3. Quest → メインPC の映像・入力が通るか（ブリッジ不要）
4. その後に bridge 契約のログ検証（[09](09_bridge_contract.md)） / ランブック Step 1〜4
