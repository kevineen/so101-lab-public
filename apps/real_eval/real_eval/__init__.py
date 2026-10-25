"""real_eval — sim2rl で学習した RL ポリシー（ONNX）を実機 SO-101 で評価する。

sim2rl 側の契約（docs/learn/07_sim2real/03_to_real.md）:

- 観測は reach タスクで ``[qpos, ee_pos, ee_goal, goal - ee]``（15 次元）
- ポリシー出力は正規化 [-1, 1] 行動。URDF 関節限界で rad へ写像して送る
- 指令途断時は **その瞬間の測定姿勢に目標を固定**（ウォッチドッグ契約）

実行には lerobot フォーク（~/robot/lerobot）が必要（PYTHONPATH。テストはモックで代用）。
"""
