"""SO-101 共通定義・ユーティリティ（so101-lab 全コンポーネントの正本）。

各コンポーネント（web_remote / bridges / apps / scripts）は関節テーブル・
ホーム姿勢ファイル・設定パス・接続イディオムを **ここから** import する。
重複定義は禁止（変更はこのパッケージに集約する）。

利用方法: リポジトリルートを PYTHONPATH に含めて
``from so101_common.joints import JOINT_ORDER`` のように import する
（``PYTHONPATH=.`` または scripts/*.sh が自動設定）。
"""
