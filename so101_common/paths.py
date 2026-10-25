"""so101-lab 内の正本パス解決。

これまで各モジュールが ``Path.home() / "robot" / "so101-lab"`` を個別に
組み立てていた（= ワークスペースを ~/robot に clone した場合のみ動く）。
ここではこのパッケージ自身の位置からリポジトリルートを求めるため、
**clone 先に依存しない**。``SO101_LAB_ROOT`` 環境変数で明示上書きもできる。
"""

from __future__ import annotations

import os
from pathlib import Path


def lab_root() -> Path:
    """so101-lab リポジトリのルート（SO101_LAB_ROOT 環境変数で上書き可）。"""
    env = os.environ.get("SO101_LAB_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


#: アーム+カメラ設定 yaml の既定位置。
DEFAULT_CONFIG_PATH: Path = lab_root() / "configs" / "so101_dual_cam.yaml"

#: ホーム（ネスト）姿勢ファイル。ユーザー単位のキャッシュなので ~/.cache に固定。
DEFAULT_HOME_PATH: Path = Path.home() / ".cache" / "so101-lab" / "home_poses.json"
