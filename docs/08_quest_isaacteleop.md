# 08 — Quest 3 × Isaac Teleop（メインPC）

**現状:** Phase B（Quest 単体）〜 Phase D+（クラッチ付きライブ）まで実装あり。  
この文書は **メインPC + Quest 3 で Isaac Teleop / CloudXR を動かす**手順。  
SO-101 までの通し確認は **[11_quest_teleop_runbook.md](11_quest_teleop_runbook.md)** を順に実行する。

ブリッジ契約は [09_bridge_contract.md](09_bridge_contract.md)。マシン分担は [07_multi_host.md](07_multi_host.md)。

## このラボでの位置づけ

| 項目 | 内容 |
|------|------|
| 入口リポ | 常に `so101-lab`（手順・契約・将来 `bridges/`） |
| 外部本体 | [NVIDIA/IsaacTeleop](https://github.com/NVIDIA/IsaacTeleop)（submodule にしない） |
| クライアント | Quest 3 ブラウザ → [CloudXR.js クライアント](https://nvidia.github.io/IsaacCapture/client) |
| 成功条件（Phase B） | Quest から入力 → retarget 例がメインPCで動く（アーム不要） |

公式 Quick Start: https://nvidia.github.io/IsaacCapture/main/getting_started/quick_start.html  
Isaac Lab + CloudXR: https://isaac-sim.github.io/IsaacLab/develop/source/how-to/cloudxr_teleoperation.html

**注意 (1.6+):** PyPI 配布名と import は `isaaccapture`（旧名 `isaacteleop`）。現行の clone 例は `isaaccapture` 前提。

## メインPC要件

- Linux（公式の teleop 経路は Linux 前提）
- **NVIDIA GPU**（CloudXR / Isaac Lab 用。Raspberry Pi では不可）
- Python 3.11+（`isaaccapture` パッケージの要求に合わせる）
- Quest 3 と同一 LAN、ファイアウォールで CloudXR ポート許可（[07](07_multi_host.md)）

任意: Isaac Lab 3.x と連携する場合は公式の Isaac Lab インストールに従う。  
Quick Start の gripper 例だけなら、まずは `isaaccapture[cloudxr,retargeters]` からでよい。

## セットアップ（メインPC）

### 1. ラボ入口と Isaac Teleop を clone

```bash
mkdir -p ~/robot && cd ~/robot
git clone https://github.com/kevineen/so101-lab.git
git clone https://github.com/NVIDIA/IsaacTeleop.git
```

### 2. `isaaccapture` を入れる

仮想環境は uv で作ります（このラボでは `pip`・`activate` を使わない。`--python` で対象 venv を明示）:

```bash
uv venv ~/robot/isaac-teleop-env/.venv   # 初回のみ
uv pip install --python ~/robot/isaac-teleop-env/.venv/bin/python \
  'isaaccapture[cloudxr,retargeters]~=1.7.0' \
  --extra-index-url https://pypi.nvidia.com --prerelease=allow

# PyPI 安定版だけ試す場合（例が古いと import が合わないことがある）
# uv pip install --python ~/robot/isaac-teleop-env/.venv/bin/python \
#   'isaaccapture[cloudxr,retargeters]~=1.0'
```

ソースから試す場合は IsaacTeleop リポの Build from Source に従う。

### 3. ポートを開ける

```bash
sudo ufw allow 47998/udp
sudo ufw allow 49100,48322/tcp
```

### 4. デバイスプロファイル

CloudXR ランタイムのデフォルトは `Quest3`（WebXR クライアント向け。Quest / Pico / デスクトップエミュレータ含む）。  
Apple Vision Pro を使う場合のみ `auto-native` 等へ変更する（通常このラボでは不要）。

解決済み設定の確認:

```bash
cat ~/.cloudxr/run/cloudxr.env
```

## Quest 3 から接続

1. Quest で **Hand and Body Tracking** を有効化（初回）
2. イヤホンブラウザで開く: https://nvidia.github.io/IsaacCapture/client  
   （オフライン時はメインPC の `https://<メインPCのIP>:48322/client/`）
3. **Server IP** にメインPC の LAN IP を入力
4. ページ上の `https://<IP>:48322/` リンクから自己署名証明書を受理
5. **Connect**

ファームウェアは最新推奨。古い WebXR だと接続や機能が落ちることがある。

## 動作確認（アームなし）

ラボラッパー（venv を自動で使う）:

```bash
# so101-lab リポジトリ直下で実行
./scripts/start_quest_gripper_example.sh
```

または手動:

```bash
cd ~/robot/IsaacTeleop
~/robot/isaac-teleop-env/.venv/bin/python examples/teleop/python/gripper_retargeting_example_simple.py
```

コントローラのトリガを握ると、ターミナルに gripper 値が流れるはず。  
他の例: `se3_retargeting_example.py`（EE pose）、`dex_bimanual_example.py` など。

デスクトップブラウザでも同 URL を開き、IWER で Quest 3 をエミュレートできる（実機なしの疎通確認用）。

## このラボ固有メモ（記入用）

運用時にここに実値を追記する。

| 項目 | 値 |
|------|-----|
| メインPC ホスト名 / IP | `main-dual-ubuntu` / `${SO101_MAINPC_LAN_IP}` |
| `isaaccapture` 版 | `1.7.14rc1`（venv: `~/robot/isaac-teleop-env/.venv`） |
| Isaac Lab 版（使う場合） | （未導入・Quick Start 例のみ） |
| CloudXR プロファイル | `Quest3`（既定） |
| 備考 | 起動: `./scripts/start_quest_gripper_example.sh`（初回は EULA 承認あり）。クライアントは **Meta Quest Browser**（Firefox 不可）。Phase C JSONL: `./scripts/record_quest_teleop_jsonl.sh` |

## SO-101 について（重要）

- **この段階では Pi / SO-101 を起動しなくてよい**
- retarget 出力を SO-101 へ送るブリッジは **Phase D MVP あり** → [09](09_bridge_contract.md) / [`../bridges/isaacteleop_to_so101/`](../bridges/isaacteleop_to_so101/)（Quest 前段の JSON 変換はこれから）
- Pi 側の日常操作はこれまでどおり LeLab / Web Remote（[01_overview.md](01_overview.md)）

## よくある問題

| 症状 | 確認 |
|------|------|
| Connect できない | メインPC IP、UDP 47998 / TCP 49100・48322、同一 LAN |
| 証明書警告で止まる | `:48322` を一度開いて Proceed |
| 映像は出るが入力が来ない | Quest のハンドトラッキング、クライアント / ランタイム版の組み合わせ |
| **時間が経つと Connect 画面に戻る** | 下の「長時間セッション」 |
| Pi で動かそうとして失敗 | GPU ホストが必要。Pi では CloudXR 経路は対象外 |

### 長時間セッション（Connect に戻される）

これは `so101-lab` の `DURATION` ではなく、**Quest Browser 上の CloudXR クライアント**側です。セッション終了時にページをリロードする既定があり、Connect 画面に見えます。

Quest クライアント（Connect 画面の Advanced / 設定）で:

| 設定 | 推奨 |
|------|------|
| **Auto Refresh on Session End** | **Never**（既定の Clean だと切断後にリロード→Connect） |
| Retry on Error | ON、回数を多め（例 20+） |
| Stream Attach / Warm-up Timeout | 誤検知なら `0`（無効）も可 |

URL で固定する例:

```text
https://${SO101_MAINPC_LAN_IP}:48322/client/?cloudxrAutoRefreshMode=never
```

あわせて:

- Quest の **スリープを長め／開発中は無効寄り**に（装着中にスリープすると XR セッション終了）
- Wi‑Fi を安定させる（2.4 GHz より 5 GHz、PC と近距離）
- メインPC の `start_quest_bridge_live.sh` / CloudXR ランタイムを止めない（止めるとクライアントも落ちる）
- 落ちたら同じ URL で再 Connect。PC から開き直すなら:  
  `python -m isaaccapture.cloudxr.webclient`

公式トラブルシュートも Isaac Teleop / Isaac Lab の CloudXR 文書を参照する。
