"""so101_common.home_pose のファイル I/O とパス解決の検証。"""

from __future__ import annotations

from pathlib import Path

from so101_common.home_pose import (
    has_home_flags,
    joints_for_arm,
    load_home_file,
    near_home,
    save_home_file,
)
from so101_common.joints import default_joints
from so101_common.paths import DEFAULT_CONFIG_PATH, DEFAULT_HOME_PATH, lab_root


def test_default_paths_are_consistent():
    assert DEFAULT_HOME_PATH == Path.home() / ".cache" / "so101-lab" / "home_poses.json"
    assert lab_root().name == "so101-lab"
    assert DEFAULT_CONFIG_PATH.parent.name == "configs"
    assert DEFAULT_CONFIG_PATH.name == "so101_dual_cam.yaml"


def test_save_load_roundtrip(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    result = save_home_file({"follower": {"shoulder_pan": 10.0, "gripper": 30.0}}, path=path)
    assert result["ok"] is True

    joints, from_file = joints_for_arm("follower", path=path)
    assert from_file is True
    assert joints["shoulder_pan"] == 10.0
    # 未指定関節は既定で埋まる
    assert joints["wrist_roll"] == 0.0
    assert joints["gripper"] == 30.0


def test_missing_arm_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    save_home_file({"follower": {"gripper": 10.0}}, path=path)
    joints, from_file = joints_for_arm("leader", path=path)
    assert from_file is False
    assert joints == default_joints()


def test_corrupt_file_returns_defaults(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    path.write_text("{not json", encoding="utf-8")
    data = load_home_file(path)
    assert data["arms"] == {}
    joints, from_file = joints_for_arm("follower", path=path)
    assert from_file is False


def test_merge_keeps_other_arms(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    save_home_file({"follower": {"gripper": 10.0}}, path=path)
    save_home_file({"leader": {"gripper": 90.0}}, path=path, merge=True)
    _, follower_ok = joints_for_arm("follower", path=path)
    _, leader_ok = joints_for_arm("leader", path=path)
    assert follower_ok and leader_ok


def test_out_of_range_values_clamped_on_save(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    save_home_file({"follower": {"shoulder_pan": 500.0}}, path=path)
    joints, _ = joints_for_arm("follower", path=path)
    assert joints["shoulder_pan"] == 100.0


def test_has_home_flags(tmp_path: Path):
    path = tmp_path / "home_poses.json"
    assert has_home_flags(path=path) == {"follower": False, "leader": False}
    save_home_file({"follower": {}}, path=path)  # 空 → 保存されない
    assert has_home_flags(path=path) == {"follower": False, "leader": False}
    save_home_file({"follower": {"gripper": 10.0}}, path=path)
    assert has_home_flags(path=path) == {"follower": True, "leader": False}


def test_near_home_tolerance():
    target = default_joints()
    near = dict(target, shoulder_pan=1.0)
    far = dict(target, shoulder_pan=5.0)
    assert near_home(near, target, tol_deg=2.5) is True
    assert near_home(far, target, tol_deg=2.5) is False
    # 未指定関節は 0 とみなす（gripper 既定 50° との差で近 Hom とは判定されない）
    assert near_home({"shoulder_pan": 1.0}, target) is False
    assert near_home({}, {k: 0.0 for k in target}) is True
