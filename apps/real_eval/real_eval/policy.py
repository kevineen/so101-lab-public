"""ONNX ポリシーの実行と観測ベクトルの構成。

観測レイアウトは sim2rl の reach タスク（``core/task.py``）:
``[qpos (6), ee_pos (3), ee_goal (3), goal - ee (3)]`` = 15 次元。
それ以外のタスク（grasp / trace）はレイアウトが違うため、入力次元が
15 でなければ「reach 以外は未対応」と明示的に拒否する。
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

#: reach の観測次元（qpos 6 + ee_pos 3 + ee_goal 3 + 差分 3）。
REACH_OBS_DIM = 15


class InferenceSession(Protocol):
    """onnxruntime.InferenceSession の必要最小面（テストは偽物を差し込む）。"""

    def run(self, output_names: list[str], input_feed: dict[str, np.ndarray]) -> list[np.ndarray]: ...


class OnnxPolicy:
    """``export_onnx`` で書き出した policy.onnx のラッパ。"""

    def __init__(self, session: InferenceSession) -> None:
        self.session = session
        input_shape = session.get_inputs()[0].shape
        obs_dim = int(input_shape[-1])
        if obs_dim != REACH_OBS_DIM:
            raise ValueError(
                f"policy expects {obs_dim}-d observations; real_eval currently supports "
                f"the reach layout only ({REACH_OBS_DIM}-d: [qpos, ee_pos, ee_goal, goal-ee])"
            )

    @staticmethod
    def build_obs(
        qpos_urdf: np.ndarray, ee_pos: np.ndarray, ee_goal: np.ndarray
    ) -> np.ndarray:
        """reach の観測ベクトル（sim2rl ReachTask.observation と同一式）。"""
        return np.concatenate([qpos_urdf, ee_pos, ee_goal, ee_goal - ee_pos]).astype(np.float32)

    def act(self, obs: np.ndarray) -> np.ndarray:
        """観測 → 正規化 [-1,1] 行動（決定的）。"""
        (action,) = self.session.run(["action"], {"obs": obs.reshape(1, -1)})
        return np.asarray(action, dtype=np.float64).reshape(-1)
