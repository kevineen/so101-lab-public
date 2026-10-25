# 18 — RL ポリシーの実機評価（real_eval）

sim2rl で学習した RL ポリシー（reach）を **実機 SO-101 で動かして採点する** 手順。
T-P2-02（実機 `real_eval.csv` プロトコル）の実装であり、sim2rl 第7章レッスン3の
チェックリストを実行に移す経路です。ツールは [`apps/real_eval`](../apps/real_eval/)。

> ⚠️ **実機を動かすドキュメントです。** Step 0 の安全確認を飛ばさないこと。
> 長時間のトルク ON の前に、独占ルール（[AGENT.md](reports/AGENT.md)）を確認する。

---

## 役割と前提

| マシン | やること |
|--------|----------|
| 学習した GPU ホスト | `export_onnx` で policy.onnx を作る |
| Raspberry Pi | ONNX 推論（onnxruntime）＋ 実機の読み書き。**torch は使わない** |

前提:

1. `~/robot/sim2rl` に学習 run（`runs/<ts>_<name>`、`checkpoints/best.zip` と `config.yaml`）
2. follower はキャリブ済み（`my_follower`。[04](04_calibration.md)）
3. LeLab / Web Remote / Quest bridge / Thor robot client は**起動していない**（シリアル独占）

## Step 0 — 安全確認（全て `[x]` になってから次へ）

- [ ] アーム作業域に人手・遮蔽物を入れない
- [ ] ESTOP（電源）が手の届く位置。「誰が」「何秒で」切るか決めた
- [ ] `max_relative_target: 5`（1 周期 5° 制限）を確認した
- [ ] 最初のエピソードは `steps_per_episode` を小さく（例 30）して目視確認する
- [ ] ゴール到達の物体は置かない（reach は到達タスク。把持はしない）

## Step 1 — ONNX を書き出す（GPU ホスト、sim2rl）

```bash
cd ~/robot/sim2rl
uv sync --extra onnx
uv run python -m sim2rl.training.export_onnx --run-dir runs/<run> --checkpoint best
# -> runs/<run>/policy.onnx
rsync -a runs/<run>/policy.onnx runs/<run>/config.yaml \
  <pi_user>@<pi>:~/robot/sim2rl/runs/<run>/   # Pi 側は sim2rl の clone がある前提
```

`best.zip`（クロスシム評価の最高得点）を推奨 — 実機は「見たことのない少し違う環境」
（sim2rl 第7章レッスン3）。

## Step 2 — 設定を用意する（Pi）

```bash
cd apps/real_eval
uv sync --group dev
cp configs/real_eval.example.yaml configs/real_eval.local.yaml
```

書き換える項目: `run_dir`（学習 run）、`goal_m`（下で計測）、`joint_map`（下で校正）。

## Step 3 — 座標を合わせる（2 段階。省略しない）

**3a. 零点（joint_map の offset）**: sim2rl の home 姿勢
（`~/robot/sim2rl/configs/robot/so101.yaml` の `home_position`）にアームを**手で保持**し:

```bash
PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml --calibrate-offsets
# 出力を yaml の joint_map: へ貼る
```

**3b. ゴール位置（goal_m）**: `--probe` で EE 位置を表示しながら、
テープ等で印を付けた点に tip を合わせ、その値を `goal_m` に書く
（URDF base_link 系・メートル）:

```bash
PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml --probe
```

> 🧭 向きの確認: `--probe` で 1 関節ずつ手で動かし、表示される qpos の増減が
> URDF の向きと合うか見る。逆ならその関節の `scale` を負にする。

## Step 4 — 評価を実行する（Pi）

```bash
PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml
# 既定 10 エピソード -> ~/robot/sim2rl/runs/<run>/real_eval.csv
```

1 エピソード = 150 step × 20 Hz = 7.5 秒。止めるときは `Ctrl+C`、
終わったら nest へ戻す（`./scripts/go_so101_home.sh --arm follower`）。

**CSV 形式**（sim2rl [docs/benchmarks.md](https://github.com/kevineen/sim2rl) §実機スコアと同一）:

```csv
date_utc,checkpoint,seed,episode,success,best_dist_m,final_dist_m,operator,notes
```

## 安全策の実体（ツール側）

| 策 | 実装 |
|----|------|
| 速度律速 | 1 周期あたりの指令変化を `max_relative_target` 度にクランプ |
| 関節リミット | URDF 限界 −マージン 2° のソフトリミット |
| ウォッチドッグ | 推論が `cmd_timeout_s`（0.5s）を超えたら **発火時の測定姿勢に目標を固定**（毎ティック現在値を追うと剛性ゼロで沈降 — sim2rl reproducibility.md の実機検証済み契約）。エピソード内で粘着し、次エピソードで再開 |
| 指令レート | 既定 20 Hz（契約の推奨下限） |
| トルク | 切断時もオフにしない（nest へ戻るまで維持。docs/17 と同じ） |

## うまくいかないとき

| 症状 | 見る場所 |
|------|----------|
| `policy expects N-d observations` | run が reach 以外（grasp/trace）。現状 reach 専用 |
| EE が明後日の方向へ動く | 3a/3b の校正をやり直す。特に `scale` の符号 |
| `No calibration for robot id` | [04](04_calibration.md) でキャリブ |
| ONNX が無い | Step 1 の `export_onnx` を忘れている |
| シリアルが取れない | LeLab / Web Remote / Thor client の起動確認（[06](06_troubleshooting.md)） |
| 動きが止まったまま | ウォッチドッグのホールド。原因（推論遅延）を確認してから再実行 |

## やらないこと（この文書の範囲外）

- 実機上での**学習**（SAC オンライン学習は sim2rl 第7章の将来課題）
- 把持（grasp）の実機評価 — 観測レイアウトが未対応
- SmolVLA / ACT の推論（LeRobot 経路。[14](14_single_arm_il.md)・[17](17_act_record_train_infer.md)）
