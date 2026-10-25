# 第0章レッスン0 — ゼロから Lab を立てる（組立 → OS → 配線 → lerobot 導入 → 動作確認）

> 🎯 **このレッスンのゴール**
> ①部品箱の状態から「ブラウザで関節が動かせる」までを自力で進められる
> ②キャリブレーション結果と lerobot フォークが「どこに保存され・誰が管理するか」言える
> ③clone した直後に何も動かない理由（`lerobot` が別リポジトリ）を説明できる

**前提**: なし（ここが本当のゼロ起点）。ラボの机・電源・Wi-Fi があること。
**時間目安**: 組立 3〜5 時間＋セットアップ 1〜2 時間。
**正本**: 組立は R-DOC-LEROBOT-SO101-HARDWARE（公式）· キャリブは [04_calibration.md](../../../04_calibration.md) · lerobot は [00_repos.md](../../../00_repos.md)

> 🧰 すでに動くラボがある人はこのレッスンは読むだけで OK。
> 「第三者に同じ環境を作れるか」の確認用チェックリストとして使います。

---

## 0.0-1 ハードウェアを組み立てる（読む）

SO-101 は 3D プリント部品＋Feetech STS3215 サーボ 6 個で構成されるオープンソースアームです。

| 部品 | 数 | 備考 |
|------|----|------|
| STS3215 サーボ | 6 | follower 側。ID 1〜6 を公式手順で付与 |
| 3D プリント部品一式 | — | STL は R-DOC-LEROBOT-SO101-HARDWARE の TheRobotStudio 版（R-ASSET-SO101・Apache-2.0） |
| 電源（12V）· USB シリアル | 各 1 | サーボのデイジーチェーン末端に接続 |
| USB カメラ | 2 | 先端＋頭上（[05_cameras.md](../../../05_cameras.md)） |

組立・サーボ ID 付与は **公式手順の画像を見ながら** 行ってください（ネジの向きと
サーボの向きが合っていないと後のキャリブで苦労します）。ラボとしての追加方針:

- **短腕**（先端質量を減らす暫定措置。トルク不足の背景は [13_drive_profiles.md](../../../13_drive_profiles.md)）
- 機体の構造（6 関節の名前・可動域）を先に言葉にしたい人は
  [sim2rl 第1章 SO-101](../../../../../../sim2rl/docs/learn/01_so101/README.md) へ

## 0.0-2 Raspberry Pi を立てる（動かす 🧪）

```bash
# 1. Raspberry Pi OS（64-bit）を公式イメージャーで microSD へ
#    - ホスト名: 例 so101pi / ユーザーを作成 / SSH を有効化
# 2. 起動後、別 PC から:
ssh <user>@so101pi.local
sudo apt update && sudo apt full-upgrade -y

# 3. シリアル・カメラが見えているか
ls /dev/serial/by-id/     # USB シリアルアダプタを確認（ラボは by-id で固定運用）
ls /dev/video*            # カメラ 2 台
```

正本のマシン分担は [07_multi_host.md](../../../07_multi_host.md)。学習（4090 WSL）と
推論（Jetson Thor）の機体が無くても、**このレッスンは Pi 1 台で完結**します。

## 0.0-3 配線と電源（動かす）

1. サーボ同士をデイジーチェーン（公式組立手順の配線図どおり）
2. 末端を USB シリアル経由で Pi へ、12V 電源を接続
3. カメラ 2 台を USB へ（by-id / video 番号は [05_cameras.md](../../../05_cameras.md) で固定）

> ⚠️ 電源投入前に配線を一目見直す。逆差し・電源不足は Overload の典型原因
> （[06_troubleshooting.md](../../../06_troubleshooting.md)）。

## 0.0-4 so101-lab を clone して lerobot フォークを用意する（動かす 🧪）

**ここが一番のつまずきポイント**です。so101-lab を clone しただけでは何も動きません。

```bash
mkdir -p ~/robot && cd ~/robot
git clone https://github.com/kevineen/so101-lab.git

# lerobot は別リポジトリ（ワークスペース直下に clone するのが正規配置）
git clone https://github.com/kevineen/lerobot.git
cd lerobot
# venv は ~/robot/lerobot/.venv に作成（uv sync --extra feetech。pip / activate は使わない）
```

なぜこうなっているか: `lerobot` は Hugging Face 本家の**個人フォーク**で、
upstream へ誤 push しないよう so101-lab の git からは切り離しています
（[00_repos.md](../../../00_repos.md) の Git 運用）。
so101-lab のスクリプトは `LEROBOT_DIR` 環境変数（未設定なら `~/robot/lerobot`）を参照します。

## 0.0-5 キャリブレーション（動かす）

```bash
# ~/robot/lerobot の .venv/bin/ を直接パスで実行（activate 不要）
cd ~/robot/lerobot
.venv/bin/lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/serial/by-id/<シリアルID>
```

- 結果は `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<robot.id>.json` に保存
- **再起動・1臂↔2臂切替で再キャリブは不要**（保存された JSON を読むだけ）
- 手順の詳細は正本 [04_calibration.md](../../../04_calibration.md)

## 0.0-6 最初の動作確認（動かす 🧪）

```bash
# so101-lab リポジトリ直下で実行
./scripts/start_web_remote.sh
# 別 PC のブラウザから http://<PiのLAN-IP>:8765
```

スライダで各関節がゆっくり動けば、ハード〜ソフトの経路が全部つながっています。
**同時起動禁止**（LeLab `:8000`・Quest bridge・Thor robot client とシリアルを取り合う）に注意。

---

## ✅ 理解度チェック

<details><summary>Q1. clone したばかりの so101-lab で Web Remote が起動しない。第一に疑うものは？</summary>

lerobot フォーク（`~/robot/lerobot`）が未作成。so101-lab の git は lerobot を追跡しないため、
fork の clone ＋ `.venv` 作成（[00_repos.md](../../../00_repos.md)）が必要。
</details>

<details><summary>Q2. キャリブレーション結果はどこに保存され、いつ再実行が必要か？</summary>

`~/.cache/huggingface/lerobot/calibration/robots/so_follower/<robot.id>.json`。
再起動や 1臂↔2臂切替では不要。機体を組み直した・サーボを交換した・公式手順から
明らかに外れた姿勢になったときに再実行（[04_calibration.md](../../../04_calibration.md)）。
</details>

<details><summary>Q3. サーボに「ラボの方針」由来の注意点は？（組立ではなく運用方針の話）</summary>

先端質量を減らす「短腕」化と、第2駆動腕 OFF・leader は手テレオペ運用。
トルク不足（Overload）対策（[13_drive_profiles.md](../../../13_drive_profiles.md)・
[00_lab_map の 0.3](README.md)）。
</details>

### 自分チェックリスト

- [ ] 公式手順でアームを組み立て、サーボ ID を付与した
- [ ] Pi に SSH でき、`/dev/serial/by-id/` でシリアルを固定した
- [ ] `~/robot/lerobot` を clone し venv を作成した
- [ ] キャリブレーションを実行し JSON が保存されたことを確認した
- [ ] Web Remote で全関節を動かした

⏭️ 次: [第0章 ラボ地図（README）](README.md) — マシン分担とツールの使い分け。
