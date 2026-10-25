# 23 — Pi4 へのモデル転送と、Pi 上推論の前提

2026-10-20、wrist-only モデル(ACT / Diffusion)の作成に合わせて整理しました。
**モデルを Pi4 に置くことはできる。Pi4 の上で計算することは(今のところ)できない。**
何をどこへ送り、どこで計算するかをこの文書で固定します。

---

## 結論(要点)

| 目的 | 可否 | 方法 |
|------|------|------|
| モデルを Pi4 へ転送 | ✅ | rsync(Tailscale 経由)。本ページ §転送手順 |
| Pi4 上で torch 推論(ACT / Diffusion) | ❌ | Pi4 の torch(`2.11.0+cu128`)は大きい行列積が Illegal instruction。[17](17_act_record_train_infer.md) の実績と同じ |
| Pi を使った実機推論(正規ルート) | ✅ | **Thor `policy_server`(CUDA)× Pi `robot_client`**。[17 §3–4](17_act_record_train_infer.md) 。wrist-only モデル向けの差分は本ページ末尾 |
| ONNX 化して Pi4 で推論 | △ 将来 | sim2rl の RL ポリシーでは実績([18](18_real_eval.md))。lerobot ポリシー用の ONNX export はまだ無い |

## 対象モデル(2026-10-20 時点)

| モデル(run 名) | 種別 | サイズ | `n_action_steps` | カメラ |
|----------------|------|--------|------------------|--------|
| `act_so101_cobra_curated_wrist_only_20261020` | ACT | 198 MB | 100 | wrist のみ |
| `diffusion_so101_cobra_curated_wrist_only_20261020` | Diffusion | 1.0 GB | 32 | wrist のみ |

いずれも WSL `../lerobot/outputs/train/<run 名>/checkpoints/last/pretrained_model` にあります。
中身は `config.json`、`model.safetensors`、`policy_preprocessor.json`(+safetensors)、`policy_postprocessor.json`(+safetensors)、`train_config.json` の 7 ファイルで、**このディレクトリごと**送ります。

---

## 前提: 経路とホスト

| ホスト | Tailscale 名 / IP | 役割 |
|--------|-------------------|------|
| 4090 の WSL(学習機) | `gpu` / `${SO101_GPU_TAILSCALE_IP}` | `lerobot-train`。転送元 |
| Raspberry Pi 4 | `pi4` / `${SO101_PI4_TAILSCALE_IP}` | 腕・カメラ。robot client |
| Jetson Thor | `thor` / `${SO101_THOR_TAILSCALE_IP}` | `policy_server`(CUDA) |

[17 §3](17_act_record_train_infer.md) の rsync は **Pi が WSL から引き込む方向**で、そちらは元から鍵が通っています。
WSL から Pi への push 方向は **2026-10-20 に `ssh-copy-id` 済み**です(初回のみ下記を実行)。

```bash
# WSL(gpu)で。鍵が無ければ作る
ls ~/.ssh/id_ed25519.pub >/dev/null 2>&1 || ssh-keygen -t ed25519 -N ""
ssh-copy-id <user>@${SO101_PI4_TAILSCALE_IP}     # Pi のパスワードを 1 回入力
ssh <user>@${SO101_PI4_TAILSCALE_IP} 'uname -m'  # パスワード無しで通ることを確認
```

## 転送手順(WSL から push)

```bash
# WSL で
MODEL=act_so101_cobra_curated_wrist_only_20261020
rsync -a --info=stats1 \
  ../lerobot/outputs/train/$MODEL/checkpoints/last/pretrained_model/ \
  <user>@${SO101_PI4_TAILSCALE_IP}:~/.cache/lerobot/policies/$MODEL/
```

- **末尾のスラッシュに注意**: `pretrained_model/` の中身を `policies/<run 名>/` へ置きます(スラッシュを外すと一段深くなります)
- Pi 側の置き場は `~/.cache/lerobot/policies/<run 名>`([17](17_act_record_train_infer.md) の旧例と同じ慣習)
- Diffusion(約 1 GB)も同じ形式です。2026-10-20 の実測では Tailscale 経由で約 30 MB/s(直接接続)が出て、ACT が約 8 秒・Diffusion が約 34 秒でした。遅いときはリレー経由になっていないか `tailscale status` で確認し、同一 LAN なら 192.168.1.x 直指定も可です

Pi 側からの pull 方向(鍵の設定が要らない既存方向)で行うなら:

```bash
# Pi で
rsync -a ${SO101_GPU_SSH}:~/robot/lerobot/outputs/train/<run 名>/checkpoints/last/pretrained_model/ \
  ~/.cache/lerobot/policies/<run 名>/
```

### 転送の確認(Pi 側)

```bash
# Pi で
ls -la ~/.cache/lerobot/policies/$MODEL/          # 7 ファイル揃っていること
du -sh ~/.cache/lerobot/policies/$MODEL/          # 上の表のサイズと概ね一致
python3 - <<EOF
import json
cfg = json.load(open(f"$HOME/.cache/lerobot/policies/$MODEL/config.json"))
print(list(cfg["input_features"]))  # ['observation.state', 'observation.images.wrist'] だけであること
EOF
```

`input_features` に `observation.images.front` が入っていたら 2 カメラ版の誤転送です。

---

## Pi4 上での推論はできるか

- **実績上の制約**: Pi4 の lerobot venv（旧 `vendor/lerobot` 配下）の torch は `2.11.0+cu128` で、大きい行列積が **Illegal instruction** になります([17](17_act_record_train_infer.md) 冒頭の実測。2026-10-20 に Pi 上でバージョン再確認)。`lerobot-rollout` を Pi4 で ACT に使うと、行動を出す前に落ちます。CPU 版 torch への入れ替えは未検証で、仮に動いても ACT(52M パラメータ・640×480・chunk 100)で 1 推論数秒の見込み、Diffusion(263M + DDPM の反復サンプリング)は現実的ではありません。加えてこの Pi は **4GB RAM 版(実測 3.7Gi、常時空き約 2Gi)** なので、メモリ面でも Diffusion の model.safetensors(約 1GB)単体でぎりぎりです。
- したがって正規ルートは **「計算は Thor、腕は Pi」**。[17 §3–4](17_act_record_train_infer.md) の `policy_server`(Thor)× `robot_client`(Pi)構成です。重みは **Thor 側のパス**に置きます(Pi → Thor の rsync は 17 §3 の手順)。
- ONNX 化して onnxruntime で動かす経路は sim2rl の RL ポリシーで実績があります([18](18_real_eval.md))が、lerobot ポリシー用の export スクリプトはまだ無いため、やりたい場合は開発項目として起こします。

### wrist-only モデルを正規ルートで動かすときの差分

[17 §4](17_act_record_train_infer.md) のクライアントコマンドに対する変更は 3 点だけです。

| 引数 | wrist-only ACT | wrist-only Diffusion |
|------|----------------|----------------------|
| `--robot.cameras` | **`wrist` だけ**を渡す(front を外す。学習入力と一致させる) | 同左 |
| `--policy_type` | `act` | `diffusion` |
| `--actions_per_chunk` | `100`(`n_action_steps` に合わせる) | `32` |

```bash
# robot_client のカメラ指定(wrist のみ)の例。他の引数は 17 §4 と同じ
--robot.cameras='{ wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} }' \
```

Thor 側の GPU メモリ量は [19 — VRAM 目安](19_vram_guide.md) を参照してください。

---

## うまくいかないとき

| 症状 | 対処 |
|------|------|
| WSL→Pi が `Permission denied (publickey)` | `ssh-copy-id` 未実施。もしくは Pi 側から pull 方向(本ページ上段)を使う |
| rsync が異常に遅い | Tailscale がリレー経由になっていないか `tailscale status` で確認。同一 LAN なら 192.168.1.x 直指定 |
| Pi のディスクが足りない | `df -h`。`~/.cache/lerobot/policies/` の古い run を削除(Diffusion は 1 GB/本) |
| Pi 上で `lerobot-rollout` が Illegal instruction | 想定どおり。Thor 経路([17](17_act_record_train_infer.md))を使う |
| サーバが重みを読み込まない | `--pretrained_name_or_path` は **Thor 上のパス**であること(Pi 上のパスではない) |
| 転送したのに挙動が 2 カメラ版のまま | `config.json` の `input_features` を確認(上の確認手順) |

## 更新履歴

- 2026-10-20 初版。wrist-only ACT / Diffusion の作成に合わせ、転送手順と Pi4 上推論の可否を整理
- 2026-10-20 ssh-copy-id 実施。両モデルの実転送と Pi 側受領確認(ファイル一覧・サイズ・`input_features`)まで完了。Pi は 4GB RAM 版、Tailscale 直結で約 30 MB/s を確認
