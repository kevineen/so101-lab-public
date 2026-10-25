"""so101_common.env のテスト（lab.local.env loader とデバイス上書き）。"""

from __future__ import annotations

from pathlib import Path

from so101_common.env import (
    apply_lab_overrides,
    lab_env_setup_hint,
    load_lab_env,
    missing_device_keys,
    parse_env_file,
)


def test_parse_env_file_handles_comments_and_quotes(tmp_path: Path):
    env_file = tmp_path / "lab.env"
    env_file.write_text(
        "# comment\n"
        "SO101_A=1\n"
        "export SO101_B=hello world\n"
        "SO101_C=\"quoted\"\n"
        "SO101_D='single'\n"
        "\n"
        "not a pair\n"
        "SO101_E=  spaced  \n",
        encoding="utf-8",
    )
    values = parse_env_file(env_file)
    assert values == {
        "SO101_A": "1",
        "SO101_B": "hello world",
        "SO101_C": "quoted",
        "SO101_D": "single",
        "SO101_E": "spaced",
    }


def test_parse_env_file_missing_file_returns_empty(tmp_path: Path):
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_load_lab_env_keeps_existing_env(tmp_path: Path):
    env_file = tmp_path / "lab.env"
    env_file.write_text("SO101_X=from_file\n", encoding="utf-8")
    environ: dict[str, str] = {"SO101_X": "from_shell"}

    loaded = load_lab_env(env_file, environ=environ)
    assert loaded == {"SO101_X": "from_file"}
    assert environ["SO101_X"] == "from_shell"  # 既存 env を優先


def test_load_lab_env_fills_unset(tmp_path: Path):
    env_file = tmp_path / "lab.env"
    env_file.write_text("SO101_X=from_file\n", encoding="utf-8")
    environ: dict[str, str] = {}

    load_lab_env(env_file, environ=environ)
    assert environ["SO101_X"] == "from_file"


def test_apply_lab_overrides_sets_nested_device_keys():
    data: dict = {
        "robot": {"follower_arm": {"port": ""}},
        "cameras": {"center_d435": {"class": "RealSenseCamera", "serial_number": ""}},
    }
    out = apply_lab_overrides(
        data,
        environ={
            "SO101_FOLLOWER_PORT": "/dev/ttyACM0",
            "SO101_REALSENSE_SERIAL": "000111222",
            "SO101_CAMERA_XIAO_URL": "",  # 空は無視
        },
    )
    assert out["robot"]["follower_arm"]["port"] == "/dev/ttyACM0"
    assert out["cameras"]["center_d435"]["serial_number"] == "000111222"
    assert out["cameras"]["center_d435"]["class"] == "RealSenseCamera"
    assert "center_xiao" not in out["cameras"]


def test_apply_lab_overrides_skips_missing_blocks():
    # yaml に無いブロックは作らない（minimal config を壊さない）
    data: dict = {"robot": {"follower_arm": {"port": "/dev/ttyACM0"}}}
    out = apply_lab_overrides(data, environ={"SO101_REALSENSE_SERIAL": "000111222"})
    assert "cameras" not in out
    assert out["robot"]["follower_arm"]["port"] == "/dev/ttyACM0"


def _base_data() -> dict:
    return {
        "robot": {
            "follower_arm": {"port": ""},
            "leader_arm": {"enabled": False, "port": ""},
        },
        "cameras": {
            "center_xiao": {"enabled": False, "url": ""},
            "center_d435": {"enabled": True, "serial_number": ""},
        },
    }


def test_missing_device_keys_reports_enabled_only():
    missing = missing_device_keys(_base_data(), section="all", environ={})
    # follower（常時必須）と有効な center_d435 のみ。無効な leader/xiao は要求しない
    assert missing == ["SO101_FOLLOWER_PORT", "SO101_REALSENSE_SERIAL"]


def test_missing_device_keys_respects_section():
    assert missing_device_keys(_base_data(), section="arms", environ={}) == [
        "SO101_FOLLOWER_PORT"
    ]
    assert missing_device_keys(_base_data(), section="cameras", environ={}) == [
        "SO101_REALSENSE_SERIAL"
    ]


def test_missing_device_keys_env_satisfies():
    data = _base_data()
    apply_lab_overrides(data, environ={"SO101_FOLLOWER_PORT": "/dev/ttyACM0"})
    assert missing_device_keys(data, section="arms") == []
    assert missing_device_keys(data, section="cameras", environ={
        "SO101_REALSENSE_SERIAL": "000111222"
    }) == []


def test_lab_env_setup_hint_lists_keys():
    hint = lab_env_setup_hint(["SO101_FOLLOWER_PORT"])
    assert "SO101_FOLLOWER_PORT" in hint
    assert "lab.local.env" in hint
