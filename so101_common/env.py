"""configs/lab.local.env（gitignore）の読み込みとデバイス設定の上書き。

ホスト名・IP・シリアル番号などの実値はリポジトリにコミットせず、
各クローン者が ``cp configs/lab.local.env.example configs/lab.local.env``
で作るローカル設定に置く（テンプレート: configs/lab.local.env.example）。

このモジュールが Python 側の唯一の読み込み口。bash 側は
scripts/record_with_buttons.sh などが同じファイルを source するため、
変数名はここで一元管理する。**すでに設定済みの環境変数を優先**する
（一時的な上書き ``SO101_FOLLOWER_PORT=... ./scripts/...`` を壊さない）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .paths import lab_root

logger = logging.getLogger(__name__)

#: lab.local.env の既定位置（SO101_LAB_ENV で差し替え可）。
LAB_ENV_PATH: Path = lab_root() / "configs" / "lab.local.env"

#: デバイス系の yaml キーと、それを上書きする環境変数の対応表。
#: （env 変数名, yaml 上のパス）
DEVICE_ENV_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SO101_FOLLOWER_PORT", ("robot", "follower_arm", "port")),
    ("SO101_LEADER_PORT", ("robot", "leader_arm", "port")),
    ("SO101_REALSENSE_SERIAL", ("cameras", "center_d435", "serial_number")),
    ("SO101_CAMERA_XIAO_URL", ("cameras", "center_xiao", "url")),
    ("SO101_WRIST_FOLLOWER_DEVICE", ("cameras", "wrist_follower", "device")),
    ("SO101_WRIST_LEADER_DEVICE", ("cameras", "wrist_leader", "device")),
)

_ARM_KEYS = ("SO101_FOLLOWER_PORT", "SO101_LEADER_PORT")
_CAMERA_KEYS = tuple(k for k, _ in DEVICE_ENV_KEYS if k not in _ARM_KEYS)


def parse_env_file(path: str | Path) -> dict[str, str]:
    """``KEY=VALUE`` 行を素直に辞書へ（export 接頭辞・引用符・コメントを許容）。"""
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_lab_env(
    path: str | Path | None = None,
    *,
    environ: MutableMapping = os.environ,
    overwrite: bool = False,
) -> dict[str, str]:
    """lab.local.env を os.environ へ取り込む（ファイルが無ければ何もしない）。

    戻り値はパース結果。``overwrite=False`` のとき既存の環境変数を優先する。
    """
    env_path = Path(path or os.environ.get("SO101_LAB_ENV") or LAB_ENV_PATH)
    values = parse_env_file(env_path)
    if not values:
        if env_path == LAB_ENV_PATH:
            logger.debug("lab env file not found (optional): %s", env_path)
        else:
            logger.warning("lab env file not found: %s", env_path)
        return values
    for key, value in values.items():
        if overwrite or key not in environ:
            environ[key] = value
    logger.debug("loaded %d vars from %s", len(values), env_path)
    return values


def _set_nested(data: dict[str, Any], path: tuple[str, ...], value: str) -> bool:
    """既存の親ブロックがすべて dict のときだけ leaf を差し替える（構造は作らない）。"""
    node: Any = data
    for key in path[:-1]:
        child = node.get(key) if isinstance(node, dict) else None
        if not isinstance(child, dict):
            return False
        node = child
    if not isinstance(node, dict):
        return False
    node[path[-1]] = value
    return True


def _get_nested(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def apply_lab_overrides(
    data: dict[str, Any],
    *,
    environ: Mapping[str, str] = os.environ,
) -> dict[str, Any]:
    """yaml 辞書へデバイス系環境変数を上書き適用（空の env 変数は無視）。"""
    for env_key, yaml_path in DEVICE_ENV_KEYS:
        value = str(environ.get(env_key, "") or "").strip()
        if value:
            _set_nested(data, yaml_path, value)
    return data


def missing_device_keys(
    data: Mapping[str, Any],
    *,
    section: str = "all",
    environ: Mapping[str, str] = os.environ,
) -> list[str]:
    """有効になっているデバイスのうち、env と yaml の両方で未設定の変数名を返す。

    ``section``: ``"arms"``（アーム2キーのみ）/ ``"cameras"`` / ``"all"``。
    親ブロックに ``enabled: false`` があるデバイスは要求しない（カメラは任意構成のため）。
    """
    if section == "arms":
        keys: tuple[str, ...] = _ARM_KEYS
    elif section == "cameras":
        keys = _CAMERA_KEYS
    else:
        keys = tuple(k for k, _ in DEVICE_ENV_KEYS)

    path_by_key = dict(DEVICE_ENV_KEYS)
    missing: list[str] = []
    for env_key in keys:
        yaml_path = path_by_key[env_key]
        parent = _get_nested(data, yaml_path[:-1])
        if not isinstance(parent, Mapping):
            continue  # yaml にブロックが無い = そのデバイスは使わない設定
        if parent.get("enabled") is False:
            continue
        if str(environ.get(env_key, "") or "").strip():
            continue
        yaml_value = _get_nested(data, yaml_path)
        if yaml_value is None or not str(yaml_value).strip():
            missing.append(env_key)
    return missing


def lab_env_setup_hint(missing: list[str]) -> str:
    """未設定キーに対する案内メッセージ（エラーにそのまま載せる）。"""
    return (
        "Missing lab device settings: " + ", ".join(missing)
        + ". Create your local config: cp configs/lab.local.env.example configs/lab.local.env"
        + " (then fill the values listed above; template comments explain each key)."
    )
