# 02 — LeLab（ワークフロー基盤）

LeLab は Hugging Face 公式のブラウザ UI です。キャリブ、leader→follower テレオペ、録画、学習、推論を GUI から行えます。

公式: https://github.com/huggingface/leLab

## インストール

Python **3.12+** が必要です。

```bash
uv tool install --python 3.12 git+https://github.com/huggingface/leLab.git
```

LeLab は **隔離された uv tool 環境**に入ります。既存の `~/robot/lerobot/.venv` は変更しません。

システム既定が Python 3.10 のままだと `Python>=3.12` エラーになります。必ず `--python 3.12` を付けてください。

## LAN から開く（別 PC のブラウザ）

公式 `lelab` コマンドは `127.0.0.1` 固定のため、別 PC からは開けません。ラッパーを使います。

```bash
./scripts/start_lelab_lan.sh
```

環境変数（任意）:

| 変数 | 既定 |
|------|------|
| `LELAB_HOST` | `0.0.0.0` |
| `LELAB_PORT` | `8000` |

別 PC: `http://<PiのIP>:8000/`

初回起動は依存ロードで **20〜40 秒**かかることがあります。

## UI 上の推奨ポート／カメラ

[`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml) に合わせる:

| 項目 | 値 |
|------|-----|
| follower port | `${SO101_FOLLOWER_PORT}` |
| leader port | `${SO101_LEADER_PORT}` |
| センター（既定 Xiao） | `${SO101_CAMERA_XIAO_URL}`（yaml `center_xiao` / `center_source: xiao`） |
| センター（D435） | シリアル `${SO101_REALSENSE_SERIAL}`（`CENTER_SOURCE=d435` または `center_source: d435`） |
| その他カメラ | [05_cameras.md](05_cameras.md) 参照 |

データ収集でセンターを D435 にしたいときは、Web Remote / cameras-only を `CENTER_SOURCE=d435` で起動するか、yaml の `center_source` を書き換えます。LeLab UI から直接カメラを選ぶ場合も、録画キーを `center` に揃えると後段が楽です。

`/dev/ttyACM*` の番号は挿し直しで変わるため、**by-id パスを推奨**します。

## 学習について

Raspberry Pi 上での本格学習は重いです。LeLab の **HF Jobs（クラウド GPU）** を使うか、別マシンで学習してください。`hf auth login` が必要です。

### 片腕 ACT / SmolVLA（現行ラボ方針）

物理 leader を第2 **駆動**腕にするとトルク不足になりやすいため、当面は **follower 片腕**で ACT → SmolVLA を試します。

- デモ収集: leader は **手テレオペ**（`so101_leader` / `my_leader`）。駆動ではない  
- Web Remote の第2ポートは OFF（`leader_arm.enabled: false`）  
- CLI 手順の正本: **[14_single_arm_il.md](14_single_arm_il.md)**  

LeLab UI でも同じ分担（Record = leader テレオペ → follower、Train は GPU / HF Jobs、Inference は follower）に揃えてください。

## ファイアウォール（任意）

```bash
sudo ufw allow from 192.168.0.0/16 to any port 8000 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 8765 proto tcp
```

## LeLab のテレオペについて

LeLab 標準のテレオペは **物理 leader → follower** です。ブラウザのスライダーだけで動かす場合は [03_web_remote.md](03_web_remote.md) を使います。
