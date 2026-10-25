"""ホーム（ネスト）姿勢ファイルの正本実装。

``~/.cache/so101-lab/home_poses.json`` に物理アーム (follower / leader) ごとの
ホーム関節角を保存し、Web Remote・go-home CLI・ブリッジ受信側で共有する。
かつて web_remote/home_pose.py と bridges/nest.py に重複実装があった統合版で、
読み込み時のクランプ（web_remote 側の動作）を引き継ぐ。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .joints import JOINT_KEYS, clamp_joints, default_joints
from .paths import DEFAULT_HOME_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


def load_home_file(path: Path | None = None) -> dict[str, Any]:
    """ホームファイルを読む。欠損/破損時は空の arms を返す（例外を投げない）。"""
    path = path or DEFAULT_HOME_PATH
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "arms": {}, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read home poses %s: %s", path, exc)
        return {
            "schema_version": SCHEMA_VERSION,
            "arms": {},
            "path": str(path),
            "error": str(exc),
        }
    arms_raw = data.get("arms") if isinstance(data, dict) else {}
    arms: dict[str, dict[str, float]] = {}
    if isinstance(arms_raw, dict):
        for name, joints in arms_raw.items():
            if isinstance(joints, dict):
                try:
                    clamped = clamp_joints({str(k): float(v) for k, v in joints.items()})
                except (TypeError, ValueError):
                    continue
                if clamped:
                    # Fill any missing keys from defaults.
                    filled = default_joints()
                    filled.update(clamped)
                    arms[str(name)] = filled
    return {
        "schema_version": str(data.get("schema_version", SCHEMA_VERSION)),
        "arms": arms,
        "updated_at": data.get("updated_at"),
        "path": str(path),
    }


def save_home_file(
    arms: Mapping[str, Mapping[str, float]],
    *,
    path: Path | None = None,
    merge: bool = True,
) -> dict[str, Any]:
    """arm→joints を書き込む。``merge=True`` なら他アームの既存値を保持。"""
    path = path or DEFAULT_HOME_PATH
    existing = load_home_file(path) if merge else {"arms": {}}
    out_arms: dict[str, dict[str, float]] = dict(existing.get("arms") or {})
    for name, joints in arms.items():
        clamped = clamp_joints(dict(joints))
        if not clamped:
            continue
        filled = default_joints()
        filled.update(clamped)
        out_arms[str(name)] = filled
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "arms": out_arms,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Saved home poses for %s → %s", sorted(out_arms), path)
    return {"ok": True, "path": str(path), "arms": out_arms, "updated_at": payload["updated_at"]}


def joints_for_arm(arm: str, *, path: Path | None = None) -> tuple[dict[str, float], bool]:
    """(joints, from_file) を返す。未保存アームは既定姿勢と from_file=False。"""
    data = load_home_file(path)
    arms = data.get("arms") or {}
    if arm in arms:
        return dict(arms[arm]), True
    return default_joints(), False


def has_home_flags(*, path: Path | None = None, arm_names: list[str] | None = None) -> dict[str, bool]:
    """各物理アームがホーム姿勢を保存済みか。"""
    path = path or DEFAULT_HOME_PATH
    names = arm_names or ["follower", "leader"]
    if not path.is_file():
        return {n: False for n in names}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {n: False for n in names}
    arms = data.get("arms") if isinstance(data, dict) else {}
    if not isinstance(arms, dict):
        return {n: False for n in names}
    return {n: n in arms and isinstance(arms.get(n), dict) for n in names}


def near_home(
    current: Mapping[str, float],
    target: Mapping[str, float],
    *,
    tol_deg: float = 2.5,
) -> bool:
    """全関節が target の tol_deg 以内なら True。"""
    for key in JOINT_KEYS:
        if abs(float(current.get(key, 0.0)) - float(target.get(key, 0.0))) > tol_deg:
            return False
    return True


def near_target(
    current: Mapping[str, float],
    target: Mapping[str, float],
    *,
    tol_deg: float = 2.5,
) -> bool:
    """``target`` に含まれる関節だけ tol_deg 以内なら True（部分ターゲット対応）。"""
    for key, goal in target.items():
        if abs(float(current.get(key, goal)) - float(goal)) > tol_deg:
            return False
    return True


def summarize_nest(*, path: Path | None = None) -> dict[str, Any]:
    """ホーム姿勢の状態サマリ（デバッグ・UI 表示用）。"""
    path = path or DEFAULT_HOME_PATH
    flags = has_home_flags(path=path)
    return {"path": str(path), "has_home": flags}
