# 23 — PC 間データ転送（データセット・チェックポイント）

マルチホストで **何を・どこからどこへ・いつ** 送るかを固定する正本です。  
録画のライフサイクルは [15](15_dataset_pipeline.md)、マシン役割は [07](07_multi_host.md)、ACT / pi05 の通しは [17](17_act_record_train_infer.md) / [21](21_pi05_thor.md) に任せ、ここでは **パスと rsync コマンド**だけを集めます。

> **よくある失敗**  
> Thor で `local/my_so101_task` のような **仮名**を `--dataset.repo_id` にすると、ローカルに `meta/info.json` が無く、続けて Hub の `local/...` を取りに行き **404** になる。  
> → 実在するディレクトリ名を使い、無いなら先にこの文書で転送する。

---

## 1. マシンと既定パス {#hosts}

機械可読の一覧は [`configs/lab_hosts.yaml`](../configs/lab_hosts.yaml.example)（無いときは `.example` をコピーして編集）。  
下表は人間向けの要約（yaml と食い違うときは **yaml を正**にしてこの表も直す）。

| 呼び名 | Tailscale / IP（例） | 役割 |
|--------|----------------------|------|
| **Pi** | LAN IP（例: `${SO101_PI_LAN_IP}`） | 録画・推論クライアント。学習しない |
| **GPU**（メインPC WSL） | `gpu` / `${SO101_GPU_TAILSCALE_IP}` | データ保管・選別・`lerobot-train`（3090/4090） |
| **Thor** | `thor` / `${SO101_THOR_TAILSCALE_IP}` | `policy_server`。任意で学習（データ要転送） |

IP が変わったら `configs/lab_hosts.yaml` とこの表と `configs/dataset.local.env` を更新する。疎通確認:

```bash
# どのマシンからでも
ssh -o BatchMode=yes ${SO101_GPU_SSH} 'hostname; echo ok'
ssh -o BatchMode=yes <user>@${SO101_THOR_TAILSCALE_IP} 'hostname; echo ok'
```

`Permission denied` / `Host key verification failed` のときは鍵を入れてから転送する（下 §6）。

### ディレクトリ規約

| 種類 | 既定パス（全ホストで同じ相対構造） |
|------|-----------------------------------|
| ローカルデータセット | `~/.cache/huggingface/lerobot/local/<name>/` |
| 必須ファイル | 上の `meta/info.json`（これが無い = 未転送 or 仮名） |
| 学習出力（GPU） | `../lerobot/outputs/train/<job>/` |
| Thor 用推論重み | `$HOME/<job名>/`（`pretrained_model` の中身を直置き） |
| Pi 側一時キャッシュ（任意） | `~/.cache/lerobot/policies/<job名>/` |

`repo_id` が `local/so101_single_coffee_…` のとき、ディレクトリは:

```text
~/.cache/huggingface/lerobot/local/so101_single_coffee_…
```

（`local/` は repo_id のプレフィックス。ディスク上は `…/lerobot/local/<name>`）

学習コマンドでは必ず両方を実名で渡す:

```bash
--dataset.repo_id=local/<name> \
--dataset.root=$HOME/.cache/huggingface/lerobot/local/<name>
```

---

## 2. 何を送るか（早見表） {#matrix}

| 目的 | 送るもの | From → To | 必須? |
|------|----------|-----------|-------|
| 通常の片腕学習 | デモデータセット一式 | **Pi → GPU** | **必須**（録画の正経路） |
| ACT / SmolVLA / Diffusion / pi05 / TurboVLA 推論 | `checkpoints/last/pretrained_model/` | **GPU → Thor** | **必須** |
| Thor 上で学習（退避） | デモデータセット一式 | **GPU → Thor**（または Pi → Thor） | Thor 学習するときだけ |
| 評価用に Pi へ重みコピー | 同上 | GPU/Thor → Pi | 任意（クライアントは Thor パスを指せば不要なことが多い） |
| Hub 公開 | — | — | **しない**（ラボ既定） |

```
【正本フロー】
  Pi 録画 ──rsync──▶ GPU（選別・学習）
                         │
                         │ pretrained_model
                         ▼
                       Thor（policy_server）◀──gRPC── Pi（腕・カメラ）

【Thor で学習するときだけ】
  GPU（または Pi）──データセット──▶ Thor ──train──▶ pretrained_model（Thor 上）
```

---

## 3. データセット: Pi → GPU（正本） {#ds-pi-gpu}

### 3a. 自動（推奨）

`scripts/record_with_buttons.sh` が `configs/dataset.local.env` を読む。雛形:

```bash
# configs/dataset.local.env.example をコピーして編集（gitignore 済み）
cp configs/dataset.local.env.example configs/dataset.local.env
```

```bash
# 例: Tailscale の GPU（<user>）
SO101_DATASET_SSH=${SO101_GPU_SSH}
SO101_DATASET_DIR=$HOME/.cache/huggingface/lerobot
SO101_DATASET_DELETE_LOCAL=1
```

- 「残す」と決めた本だけ、次の Start 前とセッション末に rsync  
- **成功時のみ** Pi 側を削除（`DELETE_LOCAL=1`）  
- 失敗した本は Pi に残る  
- 詳細・判断ログ: [15 — 指定 PC へ移す](15_dataset_pipeline.md) · [D-20261018-07](reports/design_notes.md)

事前確認:

```bash
# Pi で
ssh -o BatchMode=yes ${SO101_GPU_SSH} \
  'mkdir -p $HOME/.cache/huggingface/lerobot/local'
```

### 3b. 手動 rsync（自動が使えないとき）

```bash
# Pi で（<name> は meta/info.json がある実ディレクトリ名）
NAME=<name>
SRC="$HOME/.cache/huggingface/lerobot/local/${NAME}/"
DST="${SO101_GPU_SSH}:$HOME/.cache/huggingface/lerobot/local/${NAME}/"

test -f "${SRC}meta/info.json" || { echo "missing info.json: $SRC"; exit 1; }
rsync -a --info=progress2 "$SRC" "$DST"

# 到着確認（GPU）
ssh ${SO101_GPU_SSH} "test -f $HOME/.cache/huggingface/lerobot/local/${NAME}/meta/info.json && echo OK"
```

転送成功後に Pi 側を消す場合だけ:

```bash
rm -rf "$HOME/.cache/huggingface/lerobot/local/${NAME}"
```

---

## 4. データセット: GPU → Thor（Thor 学習時のみ） {#ds-gpu-thor}

推論だけなら **不要**。Thor で `lerobot-train` するときだけ送る（[21 §2b](21_pi05_thor.md#train-thor)）。

```bash
# GPU（3090/4090 WSL）で
NAME=<name>   # 例: so101_singlearm_pickup_cobra_20261018_205119_curated
SRC="$HOME/.cache/huggingface/lerobot/local/${NAME}/"
DST="<user>@${SO101_THOR_TAILSCALE_IP}:$HOME/.cache/huggingface/lerobot/local/${NAME}/"

test -f "${SRC}meta/info.json" || { echo "missing on GPU: $SRC"; exit 1; }
ssh <user>@${SO101_THOR_TAILSCALE_IP} "mkdir -p $HOME/.cache/huggingface/lerobot/local"
rsync -a --info=progress2 "$SRC" "$DST"
ssh <user>@${SO101_THOR_TAILSCALE_IP} "test -f $HOME/.cache/huggingface/lerobot/local/${NAME}/meta/info.json && echo OK"
```

Thor での学習引数（仮名禁止）:

```bash
--dataset.repo_id=local/${NAME} \
--dataset.root=$HOME/.cache/huggingface/lerobot/local/${NAME}
```

### 一覧の出し方

```bash
# 各マシンで「実在するローカル DS」を列挙
ls -1 ~/.cache/huggingface/lerobot/local/*/meta/info.json 2>/dev/null
```

---

## 5. チェックポイント: GPU → Thor（推論の正本） {#ckpt-gpu-thor}

ポリシー共通。中身は `config.json` / `model.safetensors` / 前後処理 JSON・safetensors など。

```bash
# GPU で
JOB=act_so101_coffee_<日付>   # または pi05_so101_<task>_<日付> 等
SRC="../lerobot/outputs/train/${JOB}/checkpoints/last/pretrained_model/"
DST="<user>@${SO101_THOR_TAILSCALE_IP}:$HOME/${JOB}/"

test -f "${SRC}config.json" || { echo "missing checkpoint: $SRC"; exit 1; }
rsync -a --info=progress2 "$SRC" "$DST"
ssh <user>@${SO101_THOR_TAILSCALE_IP} "test -f $HOME/${JOB}/config.json && echo OK"
```

Pi 経由で運ぶ例（[17](17_act_record_train_infer.md) と同じ）:

```bash
# Pi で
JOB=act_so101_coffee_<日付>
mkdir -p /tmp/${JOB}
rsync -a ${SO101_GPU_SSH}:~/robot/lerobot/outputs/train/${JOB}/checkpoints/last/pretrained_model/ \
  /tmp/${JOB}/
rsync -a /tmp/${JOB}/ <user>@${SO101_THOR_TAILSCALE_IP}:~/${JOB}/
```

クライアントの `--pretrained_name_or_path` は **Thor 上のパス**（例: `$HOME/${JOB}`）。

| ポリシー | `--policy_type` | `--actions_per_chunk` 目安 |
|----------|-----------------|----------------------------|
| ACT | `act` | 100 |
| Diffusion | `diffusion` | 32 |
| SmolVLA | `smolvla` | チェックポイントに合わせる |
| pi05 | `pi05` | 50 |
| TurboVLA | `turbovla` | 既定 12（[20](20_turbovla.md)） |

---

## 6. SSH・権限の注意 {#ssh}

| 項目 | 内容 |
|------|------|
| ユーザー | 学習・転送は **<user>**。`sudo` で rsync / train しない（`HOME` が `/root` にずれる） |
| 鍵 | `ssh -o BatchMode=yes user@host` が通るまで自動転送は使わない |
| パーミッション | 昔 root で作った出力だけ `chmod -R a+rX` が要ることがある |
| 容量 | データセットは動画込みで大きい。Thor へ送る前に `du -sh` で確認 |
| 同時起動 | 転送そのものは LeLab と衝突しない。録画中の制御ループ内では rsync しない（[15](15_dataset_pipeline.md)） |

---

## 7. トラブルシュート {#trouble}

| 症状 | 原因 | 対処 |
|------|------|------|
| `No such file .../local/<x>/meta/info.json` のあと Hub 404 | 仮名 or 未転送 | §3/§4 で実 DS を送り、`repo_id`/`root` を実名に |
| `Repository Not Found ... datasets/local/...` | ローカル失敗後の Hub フォールバック | 同上。`local/` は Hub リポ名ではない |
| rsync 後に Pi で `No such file` | finalize 二重（既知） | 転送先を確認。成功済みなら無視可（[F-20261018-02](reports/design_notes.md)） |
| Thor 推論で古い挙動 | 別ジョブのパスを指定 | `config.json` の更新時刻と `JOB` 名を確認 |
| GPU に DS が無い | 録画が Pi のみ / 自動転送未設定 | §3a の `dataset.local.env` または §3b |

---

## 8. 関連ドキュメント

| 文書 | 担当 |
|------|------|
| [07](07_multi_host.md) | マシン役割・ポート |
| [15](15_dataset_pipeline.md) | 録画・自動 rsync・選別 |
| [17](17_act_record_train_infer.md) | ACT 通し（転送は本頁へ） |
| [21](21_pi05_thor.md) | pi05 通し（転送は本頁へ） |
| [16](16_local_mlflow.md) | 学習曲線（重み・動画は MLflow に入れない） |
| `configs/dataset.local.env.example` | Pi→GPU 自動転送の雛形 |
| `configs/lab_hosts.yaml.example` → `lab_hosts.yaml` | マシン役割・パス・IP/SSH（エージェント正本・各自コピー） |
