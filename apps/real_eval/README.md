# real_eval — sim2rl ポリシーを実機 SO-101 で評価する

sim2rl で学習した RL ポリシー（reach）を Pi 上で ONNX 推論し、実機 follower で
動かして `real_eval.csv` に記録するツール。**T-P2-02（Sim2Real の提出根拠）の実装**。

- 手順の正本: [docs/18_real_eval.md](../../docs/18_real_eval.md)（安全チェックリスト込み）
- 前提: `~/robot/sim2rl` に学習 run と `policy.onnx`（`python -m sim2rl.training.export_onnx`）
- 実行には lerobot フォーク（`~/robot/lerobot`）が PYTHONPATH に必要（キャリブ済み `my_follower`）

```bash
cd apps/real_eval
uv sync --group dev          # mujoco / onnxruntime 等
cp configs/real_eval.example.yaml configs/real_eval.local.yaml
# ... run_dir / goal_m / joint_map を編集 ...

PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml --probe              # まず読み取りのみ
PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml --calibrate-offsets  # 零点合わせ
PYTHONPATH=~/robot/lerobot/src uv run python -m real_eval \
  --config configs/real_eval.local.yaml                      # 評価実行
```

設計メモ: 観測は sim2rl reach の `[qpos, ee_pos, ee_goal, goal-ee]`（15 次元）を
実機側で再構成（qpos=follower 読み値、ee_pos=MuJoCo FK）。行動は URDF 限界で
[-1,1]→rad へ。推論は onnxruntime（Pi に torch を入れない — F-20261018-03）。
