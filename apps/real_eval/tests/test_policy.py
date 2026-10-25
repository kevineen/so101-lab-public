"""policy: 観測レイアウトと ONNX セッション契約（偽セッションで検証）。"""

from __future__ import annotations

import numpy as np
import pytest

from real_eval.policy import REACH_OBS_DIM, OnnxPolicy


class _Input:
    def __init__(self, shape: list[int]) -> None:
        self.shape = shape


class FakeSession:
    def __init__(self, obs_dim: int, action: np.ndarray | None = None) -> None:
        self._obs_dim = obs_dim
        self._action = action if action is not None else np.zeros((1, 6))
        self.calls: list[np.ndarray] = []

    def get_inputs(self) -> list[_Input]:
        return [_Input([1, self._obs_dim])]

    def run(self, output_names, input_feed):
        self.calls.append(input_feed["obs"].copy())
        return [self._action]


def test_obs_layout_matches_reach():
    qpos = np.arange(6, dtype=float)
    ee = np.array([0.1, 0.2, 0.3])
    goal = np.array([0.3, 0.2, 0.1])
    obs = OnnxPolicy.build_obs(qpos, ee, goal)
    assert obs.shape == (REACH_OBS_DIM,)
    np.testing.assert_allclose(obs, np.concatenate([qpos, ee, goal, goal - ee]))


def test_act_returns_flat_action_and_feeds_obs():
    action = np.array([[0.1, -0.2, 0.3, -0.4, 0.5, -0.6]])
    session = FakeSession(REACH_OBS_DIM, action=action)
    policy = OnnxPolicy(session)
    obs = OnnxPolicy.build_obs(np.zeros(6), np.zeros(3), np.ones(3))
    got = policy.act(obs)
    assert got.shape == (6,)
    np.testing.assert_allclose(got, action[0])
    assert session.calls[0].shape == (1, REACH_OBS_DIM)


def test_non_reach_obs_dim_rejected():
    with pytest.raises(ValueError, match="reach"):
        OnnxPolicy(FakeSession(REACH_OBS_DIM + 3))
