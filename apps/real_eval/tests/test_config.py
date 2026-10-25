"""config: YAML 読み込み・既定値・検証。"""

from __future__ import annotations

from pathlib import Path

import pytest

from real_eval.config import DEG2RAD, RealEvalConfig

MINIMAL_YAML = """\
sim2rl_root: ~/robot/sim2rl
run_dir: ~/robot/sim2rl/runs/20261018_000000_reach
port: /dev/ttyACM99
goal_m: [0.25, -0.1, 0.15]
joint_map:
  shoulder_pan: {scale: 0.01745, offset: 0.1}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "real_eval.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_from_yaml_resolves_defaults(tmp_path):
    from real_eval.config import RealEvalConfig as C

    cfg = C.from_yaml(_write(tmp_path, MINIMAL_YAML))
    assert cfg.run_dir == Path.home() / "robot/sim2rl/runs/20261018_000000_reach"
    assert cfg.policy_onnx == cfg.run_dir / "policy.onnx"
    assert cfg.out_csv == cfg.run_dir / "real_eval.csv"
    assert cfg.joint_map["shoulder_pan"].offset == pytest.approx(0.1)
    # joint_map に無い関節は自由（gripper の既定は Kinematics が埋める）
    assert "gripper" not in cfg.joint_map


def test_missing_required_fields_raise(tmp_path):
    from real_eval.config import RealEvalConfig as C

    with pytest.raises(ValueError, match="run_dir"):
        C.from_yaml(_write(tmp_path, "goal_m: [0.1, 0, 0.2]\n"))
    with pytest.raises(ValueError, match="goal_m"):
        C.from_yaml(_write(tmp_path, "run_dir: /tmp/x\n"))
    with pytest.raises(ValueError, match="port"):
        C.from_yaml(_write(tmp_path, MINIMAL_YAML.replace("port: /dev/ttyACM99\n", "")))


def test_rate_guard(tmp_path):
    from real_eval.config import RealEvalConfig as C

    slow = MINIMAL_YAML + "rate_hz: 5\n"
    with pytest.raises(ValueError, match="rate_hz"):
        C.from_yaml(_write(tmp_path, slow))


def test_unknown_joint_in_map_rejected(tmp_path):
    from real_eval.config import RealEvalConfig as C

    bad = MINIMAL_YAML + "  elbow: {scale: 1.0, offset: 0.0}\n"
    with pytest.raises(ValueError, match="unknown joint"):
        C.from_yaml(_write(tmp_path, bad))
