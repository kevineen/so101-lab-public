"""runner + safety: モックアームと偽ポリシーで評価ループ・CSV・ウォッチドッグを検証。"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from real_eval.arm import SafetyGuards, Watchdog
from real_eval.config import JOINT_ORDER, RealEvalConfig

URDF = Path.home() / "robot" / "sim2rl" / "assets" / "robots" / "so101" / "so101.urdf"
needs_urdf = pytest.mark.skipif(not URDF.exists(), reason="sim2rl so101 URDF not available")


class FakeArm:
    """読み値は固定、書き込みを記録するだけのアーム。"""

    def __init__(self, measured: np.ndarray) -> None:
        self.measured = measured
        self.writes: list[np.ndarray] = []
        self.closed = False

    def read_joints(self) -> np.ndarray:
        return self.measured.copy()

    def write_joints(self, target: np.ndarray) -> None:
        self.writes.append(np.asarray(target).copy())

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, action: np.ndarray) -> None:
        self.action = action.reshape(1, -1)
        self.delay_s: float = 0.0
        self._t0 = 0.0

    def get_inputs(self):
        class _I:
            shape = [1, 15]

        return [_I()]

    def run(self, output_names, input_feed):
        import time

        if self.delay_s and self._t0 == 0.0:
            self._t0 = time.monotonic()
        if self.delay_s:
            time.sleep(self.delay_s)
        return [self.action]


def _cfg(tmp_path: Path, run_dir: Path, **kw) -> RealEvalConfig:
    cfg = RealEvalConfig(
        run_dir=run_dir,
        goal_m=(0.25, -0.1, 0.15),
        port="/dev/ttyACM99",
        episodes=1,
        steps_per_episode=3,
        rate_hz=50,
        cmd_timeout_s=0.05,
        success_threshold_m=0.03,
        operator="tester",
        notes="unit",
    )
    for key, value in kw.items():
        setattr(cfg, key, value)
    return cfg.resolve()


# --- SafetyGuards / Watchdog（URDF 不要）-----------------------------------------------


def test_guards_clamp_step_and_limits():
    lower, upper = np.array([-90.0] * 6), np.array([90.0] * 6)
    guards = SafetyGuards(lower, upper, max_step=5.0, margin=2.0)
    current = np.zeros(6)
    clamped = guards.clamp_target(current, np.array([100.0, -100.0, 3.0, 0.0, 0.0, 0.0]))
    assert clamped[0] == pytest.approx(5.0)  # ステップ制限
    assert clamped[1] == pytest.approx(-5.0)
    assert clamped[2] == pytest.approx(3.0)  # 範囲内はそのまま
    # リミット近くではマージン内に丸まる
    near = guards.clamp_target(np.array([88.0, 0, 0, 0, 0, 0]), np.array([95.0, 0, 0, 0, 0, 0]))
    assert near[0] == pytest.approx(88.0)  # 90-2=88 が上限


def test_watchdog_freezes_at_measured_pose_on_expiry():
    wd = Watchdog(timeout_s=0.01)
    assert not wd.stale
    wd.note_write()
    measured = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    import time

    time.sleep(0.02)
    assert wd.stale
    hold1 = wd.hold_target(measured)
    # その後の測定値が変わってもホールド姿勢は発火時のまま（沈降防止契約）
    hold2 = wd.hold_target(measured + 10.0)
    np.testing.assert_allclose(hold1, measured)
    np.testing.assert_allclose(hold2, measured)
    # ホールドは粘着: 書き込んでも自動再開しない。再開は reset()（次エピソード）
    wd.note_write()
    assert wd.stale
    wd.reset()
    assert not wd.stale


# --- run_eval（URDF 必要）---------------------------------------------------------------


@needs_urdf
def test_run_eval_writes_benchmark_csv(tmp_path):
    from real_eval.kinematics import Kinematics
    from real_eval.policy import OnnxPolicy
    from real_eval.runner import CSV_HEADER, run_eval

    run_dir = tmp_path / "runs" / "20261018_000000_fake"
    run_dir.mkdir(parents=True)
    (run_dir / "config.yaml").write_text("seed: 42\n", encoding="utf-8")

    kin = Kinematics(URDF, {})
    # 実機の静止姿勢らしい読み値（LeRobot 度系）
    measured = np.array([0.0, -20.0, 40.0, -20.0, 0.0, 50.0])
    arm = FakeArm(measured)
    policy = OnnxPolicy(FakeSession(np.full(6, 0.1)))
    cfg = _cfg(tmp_path, run_dir)

    csv_path = run_eval(arm, kin, policy, cfg)
    assert csv_path == run_dir / "real_eval.csv"
    assert arm.closed
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0].keys() == set(CSV_HEADER)
    assert rows[0]["seed"] == "42"
    assert rows[0]["checkpoint"] == "best"
    assert rows[0]["operator"] == "tester"
    assert float(rows[0]["best_dist_m"]) >= 0.0
    assert rows[0]["success"] in ("True", "False")
    # 指令はステップ分出ている
    assert len(arm.writes) == cfg.steps_per_episode
    # 指令はクランプされている: 初期読み値からの変化が max_step 以下
    delta = np.abs(arm.writes[0] - measured)
    assert delta.max() <= cfg.max_relative_target + 1e-9


@needs_urdf
def test_slow_policy_engages_watchdog_hold(tmp_path):
    """推論が cmd_timeout を超えると、目標は測定姿勢に固定され続ける。"""
    from real_eval.kinematics import Kinematics
    from real_eval.policy import OnnxPolicy
    from real_eval.runner import run_eval

    run_dir = tmp_path / "runs" / "20261018_000001_slow"
    run_dir.mkdir(parents=True)

    kin = Kinematics(URDF, {})
    measured = np.array([5.0, -25.0, 45.0, -25.0, 5.0, 40.0])
    arm = FakeArm(measured)
    session = FakeSession(np.full(6, 0.9))
    session.delay_s = 0.08  # cmd_timeout_s=0.05 を恒常的に超える
    policy = OnnxPolicy(session)
    cfg = _cfg(tmp_path, run_dir)

    run_eval(arm, kin, policy, cfg)
    # 遅延ポリシーの出した目標は使われず、ホールド（＝測定姿勢）が書かれる
    np.testing.assert_allclose(arm.writes[1], measured, atol=1e-9)
    np.testing.assert_allclose(arm.writes[-1], measured, atol=1e-9)
