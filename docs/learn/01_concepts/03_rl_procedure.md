# 第1章レッスン3 — 強化学習の学習手順（シムの reach）

> 🎯 **ゴール**
> ①PPO で SO-101 の reach をシム上で回せる
> ②学習曲線の成功率と手先距離の見方が言える
> ③この手順がどの論文のアルゴリズムか指せる

実機の模倣（ACT）は第2章です。ここは **報酬で試行錯誤する側** を、CPU のシミュレータで一周します。

数式と報酬コードの正本は sim2rl 第2章です。

| 深さ | 場所 |
|------|------|
| このページ | 回す順番と、見るファイル |
| 観測・報酬・MDP | [sim2rl 02_rl / 01_basics](../../../../sim2rl/docs/learn/02_rl/01_basics.md) |
| PPO と SAC の仕組み | [02_algorithms](../../../../sim2rl/docs/learn/02_rl/02_algorithms.md) |
| 同じ実習の詳しい読み方 | [03_practice](../../../../sim2rl/docs/learn/02_rl/03_practice.md) |
| 論文リンク一覧 | [papers.md](../papers.md) |

論文: [R-PAPER-PPO](https://arxiv.org/abs/1707.06347)（この手順の既定）· [R-PAPER-SAC](https://arxiv.org/abs/1801.01290)（任意の比較）

---

## 3.1 どこで回すか

| 項目 | 決め |
|------|------|
| リポジトリ | `~/robot/sim2rl` |
| マシン | CPU で足りる（このレッスンは MuJoCo 単環境） |
| タスク | `task=reach`（手先を目標点へ 3 秒で届ける） |
| アルゴリズム | 既定の PPO（Stable-Baselines3） |
| 実機 | このレッスンではトルクを入れない |

環境が無いときは sim2rl [第0章](../../../../sim2rl/docs/learn/00_setup/README.md) の CPU 手順（`uv sync --group dev`）を先に済ませます。

```bash
cd ~/robot/sim2rl
uv sync --group dev
```

---

## 3.2 手順

### 1. スモーク（1〜2 分）

パイプラインが起動することだけ確認します。4096 ステップでは評価間隔を下げないと評価が一度も走りません。

```bash
uv run python -m sim2rl.training.train sim=mujoco task=reach \
    train.total_timesteps=4096 train.eval_freq=1024
```

`make train-mujoco` も同じです。ログに `runs/<日時>_..._reach_ppo` が出れば記録場所です。

### 2. 本学習（10 万ステップ、数分〜十数分）

```bash
uv run python -m sim2rl.training.train sim=mujoco task=reach \
    train.total_timesteps=100000 run_name=first_reach
```

10,000 ステップごとに `eval/success_rate` と `eval/mean_dist` が出ます。  
目安は **成功率が 0.8 を超え、`mean_dist` が 0.03 m 付近まで下がる** ことです。seed でばらつくので、1 回の数字を確定結果にはしません。

### 3. 成果物を見る

```bash
ls runs/*first_reach/
```

| ファイル | 見ること |
|----------|----------|
| `training_curve.png` | 成功率の曲線が右肩上がりか |
| `eval_history.csv` | `timestep, success_rate, mean_dist, best_dist` |
| `config.yaml` | 再現に使う設定全文 |
| `metadata.json` | seed・git SHA |
| `checkpoints/final.zip` `best.zip` | 終了時 / 評価最良のポリシー |
| `tb/` | TensorBoard（`make tensorboard` → `http://localhost:6006`） |

`success_rate` は評価エピソードの **最終ステップ** で手先が目標の 3 cm 以内だった割合です。  
`mean_dist` は各エピソード中の **最小** 距離の平均です。近づいたのに最後まで留まれないと、距離は小さく成功率は 0 のまま、という行が出ます。

### 4. 軌跡を見る

```bash
uv run python -m sim2rl.training.eval --run-dir runs/*first_reach --episodes 20
```

`eval_report.json` と `eval_trajectories.png` が run ディレクトリに足されます。

### 5. 任意: SAC を 1 本だけ比べる

PPO は新しい経験を大量に使う on-policy です。SAC は過去の経験を再利用する off-policy で、単環境向きです（[R-PAPER-SAC](https://arxiv.org/abs/1801.01290)）。

```bash
uv run python -m sim2rl.training.train sim=mujoco algo=sac task=reach \
    train.total_timesteps=100000 run_name=first_reach_sac
```

公平な比較は seed を揃えて複数回です。道具は `uv run python -m sim2rl.benchmark.run`（作法は sim2rl 第8章）。

---

## 3.3 このあとやらないこと

reach の PPO を、そのまま Raspberry Pi の実機 SO-101 に載せてゼロから回す手順にはしません。失敗試行のコストが大きいため、実機の主経路はデモ模倣（第2章 ACT）です。シムのポリシーを実機へ寄せる考え方は sim2rl [第7章 Sim2Real](../../../../sim2rl/docs/learn/07_sim2real/README.md)。

GPU があるときは、同じタスクを Genesis 並列で短く確認できます（`make train-genesis`）。評価の正は引き続き MuJoCo 単環境です。

---

## 🧪 実習チェック

- [ ] `runs/*first_reach/` がある
- [ ] `training_curve.png` を開き、成功率の向きを一文で書いた
- [ ] 使ったアルゴリズムが PPO の論文だと指せる
- [ ] 実機のトルクは入れていない

---

## ✅ 理解度チェック

<details>
<summary>Q1. スモークを 4096 ステップだけにして、eval_freq を既定の 10000 のままにすると？</summary>

評価が一度も走らない設定として起動時に止まります。スモークで曲線を見るときは `train.eval_freq=1024` のように評価間隔を下げます。
</details>

<details>
<summary>Q2. なぜ実機で同じ PPO を最初に回さないのか？</summary>

報酬が出るまで試行錯誤が多く、腕と環境の失敗コストが大きいからです。ラボはシムで RL の手順を覚え、実機はデモの ACT から入ります。
</details>

⏭️ 模倣に戻る: [02_act_vs_vla.md](02_act_vs_vla.md) · 論文一覧: [papers.md](../papers.md)
