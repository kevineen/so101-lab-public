# so101-lab

SO-101 アームのラボ運用リポジトリ（Web Remote、LeLab、実験、ドキュメント）。  
**マルチマシン運用の入口もこの 1 リポ**（Pi / Jetson Thor / メインPC / Quest の手順・将来ブリッジ契約）。

## 初めて参加するとき（ローカル設定）

このラボは **Pi / GPU（WSL）/ Jetson Thor / Quest** など複数マシンで動きます。  
IP・デバイスのシリアルなど**環境固有の値はリポジトリに含まない**ため、clone 直後に一度だけ次を行ってください。

```bash
# リポジトリ直下で
cp configs/lab.local.env.example configs/lab.local.env
cp configs/lab_hosts.yaml.example configs/lab_hosts.yaml   # エージェント/人間向けの PC 構成メモ（任意）
```

`configs/lab.local.env` を開き、使う機能の分だけ値を埋めます（コメントに調べ方あり）。

| 項目 | 意味 |
|------|------|
| `SO101_FOLLOWER_PORT` / `SO101_LEADER_PORT` | アーム2台の `/dev/serial/by-id/...`（**アームを動かすのに必須**） |
| `SO101_REALSENSE_SERIAL` ほかカメラ3変数 | RealSense のシリアル、Xiao カメラ URL、wrist カメラの by-path |
| `SO101_PI_LAN_IP` / `SO101_PI_BASE_URL` | Pi の IP（Quest テレオペ・ブラウザ表示） |
| `SO101_PI/GPU/THOR/PI4_SSH` ほか IP 類 | PC 間転送・docs の `${SO101_*}` コマンド例で使用 |
| `SO101_DATASET_SSH` ほか | 録画データの Pi→GPU オフロード先（空なら Pi に残す） |

- どちらのファイルも **gitignore 済み**（個人の IP・シリアルをコミットしない）
- 雛形の説明: [`configs/lab.local.env.example`](configs/lab.local.env.example) · [`configs/lab_hosts.yaml.example`](configs/lab_hosts.yaml.example)
- 人間向けの分担・ポート: [docs/07_multi_host.md](docs/07_multi_host.md)
- データセット／重みの送り方: [docs/23_data_transfer.md](docs/23_data_transfer.md)
- コブラ／スネークボウルのデータセット・学習済みモデルの入手: [docs/25_dataset_model_release.md](docs/25_dataset_model_release.md)
- タスクの録画・推論コマンド早見表: [notes/command.md](notes/command.md)

疎通確認の例:

```bash
set -a && source configs/lab.local.env && set +a
ssh -o BatchMode=yes ${SO101_GPU_SSH:-<user>@<相手のIP>} 'hostname; echo ok'
```

## どこから始めるか

| 目的 | 参照 |
|------|------|
| **初めて参加（PC 構成・IP / SSH）** | 上の「初めて参加するとき」· [`configs/lab_hosts.yaml.example`](configs/lab_hosts.yaml.example) |
| **ゼロから始める（組立・OS・キャリブから）** | [docs/learn/00_lab_map/00_setup_from_zero.md](docs/learn/00_lab_map/00_setup_from_zero.md) |
| **強化学習（RL/PPO/SAC）を学ぶ** | [~/robot/sim2rl/docs/learn](../sim2rl/docs/learn/README.md)（シム・RL の教科書。本リポは実機 IL 担当） |
| Pi で SO-101 を動かす | [docs/01_overview.md](docs/01_overview.md) → [02](docs/02_lelab.md) / [03](docs/03_web_remote.md) |
| **初学者向け学習コース（ACT→SmolVLA→双腕）** | [docs/learn/](docs/learn/README.md)（sim2rl `docs/learn` と連携） |
| **片腕 ACT / SmolVLA 運用正本** | [docs/14_single_arm_il.md](docs/14_single_arm_il.md) · [チェックリスト](docs/checklists/single_arm_il.checklist.md) |
| **データセット作成・閲覧・編集** | [docs/15_dataset_pipeline.md](docs/15_dataset_pipeline.md) · [作業レポート](docs/reports/single_arm_il_work_report.md) |
| **学習ログ（ローカル MLflow）** | [docs/16_local_mlflow.md](docs/16_local_mlflow.md) · `./scripts/start_mlflow.sh`（Docker） · `make mlflow-serve` |
| **学習済みモデルの実機評価・選別** | [docs/24_model_eval_campaign.md](docs/24_model_eval_campaign.md) · [結果](docs/reports/model_eval_results.md) |
| **片腕 ACT（録画→学習→Thor 推論）** | [docs/17_act_record_train_infer.md](docs/17_act_record_train_infer.md) |
| **RL ポリシーの実機評価（reach 採点）** | [docs/18_real_eval.md](docs/18_real_eval.md) · [apps/real_eval](apps/real_eval/) |
| **VRAM 目安（Diffusion / VLA 学習・推論）** | [docs/19_vram_guide.md](docs/19_vram_guide.md)（QLoRA 量子化・vLLM/SGLang 可否込み） |
| **片腕 pi05（3090 LoRA → Thor 推論）** | [docs/21_pi05_thor.md](docs/21_pi05_thor.md) |
| **PC 間データ転送（Pi / GPU / Thor）** | [docs/23_data_transfer.md](docs/23_data_transfer.md) |
| 第2腕をゆっくり駆動 / 12V 換装 | [docs/13_drive_profiles.md](docs/13_drive_profiles.md) |
| マシン分担・ポート | [docs/07_multi_host.md](docs/07_multi_host.md) · PC 構成 YAML は上の「初めて参加するとき」 |
| 双腕 MolmoAct2（Pi 制御 / Jetson Thor 推論） | [docs/10_molmoact2_thor.md](docs/10_molmoact2_thor.md) |
| メインPC + Quest 3（Isaac Teleop） | [docs/08_quest_isaacteleop.md](docs/08_quest_isaacteleop.md) |
| Quest テレオペ動作確認（順を追う） | [docs/11_quest_teleop_runbook.md](docs/11_quest_teleop_runbook.md) · [チェックリスト](docs/checklists/) |
| 3D モデルで可動域・干渉チェック（実機不要） | [docs/12_mujoco_sim.md](docs/12_mujoco_sim.md) · `scripts/sim_check.py` |
| 将来のブリッジ契約 | [docs/09_bridge_contract.md](docs/09_bridge_contract.md) · [bridges/](bridges/) |
| 全体ロードマップ | [docs/roadmap.md](docs/roadmap.md) |

マニュアル索引: [`docs/manual.md`](docs/manual.md) · MkDocs: `make docs-serve`

## クイックスタート（Pi）

```bash
# Web Remote（ブラウザ遠隔操作）
./scripts/start_web_remote.sh

# LeLab（キャリブ・録画・学習 UI）— Web Remote と同時起動しない
./scripts/start_lelab_lan.sh
```

設定: [`configs/so101_dual_cam.yaml`](configs/so101_dual_cam.yaml)  
リポジトリ関係: [`docs/00_repos.md`](docs/00_repos.md)

### ドキュメントをブラウザ / スマホで読む（mkdocs）

`docs/`（learn カリキュラム含む）を Material for MkDocs で配信します。  
日本語 UI・全文検索・ダークモード・mermaid 図・`<details>` 折りたたみ回答に対応:

```bash
uv sync --all-groups    # 初回のみ（docs・tracking・lerobot[dataset-viz] 全部入り）
make docs-serve         # http://<PCのIP>:8100
```

- **PC**: <http://localhost:8100>
- **スマホ（同じ Wi-Fi）**: PC の LAN IP（`hostname -I` 等）の `http://<IP>:8100`
- WSL2 NAT モードの場合、スマホから届くには **管理者 PowerShell** で一度だけポート転送が必要:

```powershell
netsh interface portproxy add v4tov4 listenport=8100 listenaddress=0.0.0.0 connectport=8100 connectaddress=<wsl-ip>
netsh advfirewall firewall add rule name="mkdocs" dir=in action=allow protocol=TCP localport=8100
```

（`<wsl-ip>` は WSL 内 `hostname -I` の値。`make docs-build` で `site/` に静的生成もできます）

sim2rl 側も同様（既定 `:8100`）: `~/robot/sim2rl` で `make docs-serve`。**両方一気に**立ち上げるなら:

```bash
./scripts/serve_docs.sh        # sim2rl :8100 / so101-lab :8101 を同時 serve
```

#### 外出先からスマホで読む（サーバー常設不要）

| 方法 | 手順 | 特徴 |
|------|------|------|
| **オフライン 1 枚 HTML** | `make docs-print` → `print/so101-lab_docs.html` をスマホ / Google Drive へコピー | サーバー不要・圏外でも読める。検索は不可、更新のたび再生成 |
| **Tailscale 経由** | Tailscale 参加マシンで `./scripts/serve_docs.sh`、スマホは Tailscale アプリ ON → `http://<マシンのMagicDNS名>:8101` | フル機能（検索・ダークモード）。自宅のマシンが起動している必要あり |

sim2rl 側も `make docs-print` で `print/sim2rl_docs.html` が出ます。

## レイアウト

| パス | 内容 |
|------|------|
| `apps/` | SayCan / trainswap / experiment_report |
| `bridges/` | Isaac Teleop → SO-101 アダプタ（Phase D+・契約は docs/09） |
| `configs/` | アーム・カメラ YAML · **`lab.local.env.example`**（IP・シリアル等の各自設定）· `lab_hosts.yaml.example`（PC 構成メモ） |
| `docs/` | 運用・マルチホスト・Quest / ブリッジ手順 |
| `experiments/` | trainswap 実験設定 |
| `scripts/` | 起動ラッパー（Web Remote、MLflow、学習） |
| `tracking/` | ローカル MLflow ロガー（`lerobot-train` の曲線） |
| `docker-compose.yml` | ローカル MLflow UI（`:5000`、store は `mlflow_store/`） |
| `mlflow_store/` | MLflow の sqlite と artifacts（gitignore。実行後にできる） |
| `web_remote/` | ブラウザ遠隔操作 |
| `~/robot/lerobot/` | LeRobot フォーク（ワークスペース直下に別 clone。`LEROBOT_DIR` で参照） |

## 依存

- **Python 環境は uv に統一**。`pip` と `source .venv/bin/activate` は使わない（uv の venv には pip が入っていない。また `VIRTUAL_ENV` が別環境を指していると `uv pip install` の宛先が変わるため、対象は `--python <venv>/bin/python` で明示する）
- **原則ログインユーザーで実行**（root / `sudo` を仮定しない。実行ユーザーの `~/.cache` を使う）
- so101-lab 本体: `uv sync --all-groups`（`lerobot[dataset-viz]` は通常依存、docs / tracking グループも入る）
- `~/robot/lerobot/.venv`（Pi）: `uv sync --extra feetech` — 手順は [`docs/00_repos.md`](docs/00_repos.md)
- LeLab: `uv tool install --python 3.12 git+https://github.com/huggingface/leLab.git`
- Quest / Isaac Teleop（メインPC）: 外部リポ [NVIDIA/IsaacTeleop](https://github.com/NVIDIA/IsaacTeleop)、パッケージは `isaaccapture`（1.6+）— 手順は [docs/08](docs/08_quest_isaacteleop.md)

## 提出用スナップショット運用（private 本家 → public 提出リポ）

課題提出などで公開するときは、**このリポジトリ（private）をそのまま public にしない**。
代わりに別の公開リポジトリへ「tracked ファイルだけのスナップショット」を書き出す。

```
kevineen/so101-lab (private)              kevineen/so101-lab-public (public, 提出・提出用)
  ├─ main: 今後も普通に開発                  └─ commit 1: 提出スナップショット
  ├─ サニタイズ済みの作業ツリー                  commit 2: 更新スナップショット（任意のタイミング）
  └─ 提出時にタグ (submission-YYYYMMDD)
```

**なぜ安全か**: `make publish-public` は `git archive`（tracked ファイルのみ）で書き出す。
`configs/lab.local.env`・`mlflow_store/`・個人ツールなど gitignore 済みのファイルは
**仕組み上入れない**。また公開側の履歴はスナップショット commit のみで、
本家の開発履歴（WIP や失敗も含む）は private 側にしか残らない。

### 初回セットアップ（— 済み）

`~/robot/so101-lab-public` にローカル snapshot を作成済み。GitHub への公開だけ実行する:

```bash
cd ~/robot/so101-lab-public
# gh CLI を使う場合（1コマンド）:
gh repo create kevineen/so101-lab-public --public --source=. --remote=origin --push

# Web UI で作る場合:
#   GitHub で空の public リポを作成 → 以下で接続
#   git remote add origin git@github.com:kevineen/so101-lab-public.git
#   git push -u origin main
```

### 日常の更新フロー（公開を更新したくなったら）

```bash
cd ~/robot/so101-lab
# 1) 本家で開発・コミット（いつもどおり）
# 2) 提出時点にタグを打つ / 付け直す
git tag -f submission-$(date +%Y%m%d) -m "提出スナップショット"
# 3) tracked のみをエクスポート
make publish-public DIR=$HOME/robot/so101-lab-public
# 4) 公開側でコミットして push
cd ~/robot/so101-lab-public
git add -A && git commit -m "Snapshot $(date +%Y-%m-%d)" && git push
```

### 公開前の最終チェック（任意だが推奨）

```bash
cd ~/robot/so101-lab-public
# プライベート IP が混入していないか（一般形で検査。127.0.0.1 / 0.0.0.0 は除外）
grep -rnE "\b(100|192\.168|172\.(1[6-9]|2[0-9]|3[01])|10)\.[0-9]+\.[0-9]+\.[0-9]+\b" \
  --include="*.py" --include="*.md" --include="*.sh" --include="*.yaml" --include="*.yml" \
  --include="*.json" --include="*.csv" --include="*.js" . | grep -vE "127\.0\.0\.1|0\.0\.0\.0"
# ホームの絶対パス（/home/<user>/）が混入していないか
grep -rnE "/home/[A-Za-z0-9_-]+/" \
  --include="*.py" --include="*.md" --include="*.sh" --include="*.yaml" --include="*.yml" \
  --include="*.json" --include="*.csv" --include="*.js" .
```

どちらも何も出なければクリーン。**ルール**: 公開側で直接編集しない（常に本家 → 公開の片方向）。
データセット・モデルの公開は [docs/25_dataset_model_release.md](docs/25_dataset_model_release.md)。

## ライセンス・上流

実験コードは本リポジトリ管理。LeRobot 本体は `~/robot/lerobot` のライセンスに従う。Hugging Face upstream への push は行わない。
