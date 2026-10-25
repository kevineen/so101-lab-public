#!/usr/bin/env python
"""LeRobot データセット キュレーション適用ツール.

curation.json (エピソード削除・フレーム範囲トリム) をソースデータセットに適用し、
新しいデータセット `<name>_curated` を作成する。元データセットは一切変更しない。

使い方:
    python apply_curation.py --repo-id local/mydataset --root /path/to/mydataset \
        [--curation /path/to/curation.json] \
        [--output-repo-id local/mydataset_curated] [--output-root /path/to/out]

curation.json 形式:
    {
      "version": 1,
      "episodes": {
        "5":  {"decision": "delete"},
        "12": {"decision": "keep", "trim": [30, 250]}
      }
    }
    - `trim` はエピソードローカルの [start, end) フレーム範囲 (endは排他)。
    - 未記載のエピソードは全体を保持。
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from lerobot.configs import encoder_config_from_video_info
from lerobot.datasets.compute_stats import aggregate_stats, compute_episode_stats
from lerobot.datasets.dataset_metadata import LeRobotDatasetMetadata
from lerobot.datasets.dataset_tools import (
    _keep_episodes_from_video_with_av,
    _load_episode_with_stats,
    _write_parquet,
)
from lerobot.datasets.io_utils import write_info, write_stats
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import DEFAULT_DATA_PATH
from lerobot.utils.utils import flatten_dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("apply_curation")


def count_video_frames(path: Path) -> int:
    """mp4 のフレーム数を数える。まずコンテナメタデータ、なければデコードして数える。"""
    import av

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if stream.frames and stream.frames > 0:
            return int(stream.frames)
        if stream.duration is not None:
            fps = float(stream.average_rate) if stream.average_rate else 30.0
            return int(round(float(stream.duration * stream.time_base) * fps))
        # 最終手段: デコードして数える
        n = 0
        for packet in container.demux(stream):
            n += len([f for f in packet.decode() if f is not None])
        return n


def compute_video_availability(dataset: LeRobotDataset) -> dict[tuple[str, int, int], int]:
    """(video_key, chunk, file) ごとの実フレーム数を返す。"""
    meta = dataset.meta
    if meta.episodes is None:
        meta.episodes = {}
    counts: dict[tuple[str, int, int], int] = {}
    for video_key in meta.video_keys:
        file_keys = set()
        for ep_idx in range(meta.total_episodes):
            ep = meta.episodes[ep_idx]
            ck = ep[f"videos/{video_key}/chunk_index"]
            fi = ep[f"videos/{video_key}/file_index"]
            file_keys.add((ck, fi))
        for ck, fi in sorted(file_keys):
            path = dataset.root / meta.video_path.format(video_key=video_key, chunk_index=ck, file_index=fi)
            counts[(video_key, ck, fi)] = count_video_frames(path)
    return counts


def episode_video_avail_frames(
    dataset: LeRobotDataset,
    ep_idx: int,
    file_frame_counts: dict[tuple[str, int, int], int],
) -> int:
    """エピソードが各動画特徴で実際に持つフレーム数の最小値 (データ行数を超え得る場合は length で打ち切り)。"""
    meta = dataset.meta
    ep = meta.episodes[ep_idx]
    length = int(ep["length"])
    avail = length
    for video_key in meta.video_keys:
        from_tick = round(ep[f"videos/{video_key}/from_timestamp"] * meta.fps)
        to_tick = round(ep[f"videos/{video_key}/to_timestamp"] * meta.fps)
        ck = ep[f"videos/{video_key}/chunk_index"]
        fi = ep[f"videos/{video_key}/file_index"]
        n_file = file_frame_counts[(video_key, ck, fi)]
        avail = min(avail, max(0, min(to_tick, n_file) - from_tick))
    return avail


def load_curation(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "episodes" not in data:
        raise ValueError(f"curation ファイルに 'episodes' キーがありません: {path}")
    for k, v in data["episodes"].items():
        if not isinstance(k, str) or not k.lstrip("-").isdigit():
            raise ValueError(f"エピソード番号が不正です: {k!r}")
        decision = v.get("decision", "keep")
        if decision not in ("keep", "delete"):
            raise ValueError(f"decision は 'keep' か 'delete' である必要があります: {k}={decision}")
        trim = v.get("trim")
        if trim is not None:
            if len(trim) != 2 or not all(isinstance(x, int) for x in trim):
                raise ValueError(f"trim は [start, end) の整数ペアである必要があります: {k}={trim}")
    return data


def _extract_source_stats(
    src_dataset: LeRobotDataset,
    episode_row: dict,
    numeric_keys: set[str],
) -> dict[str, dict]:
    """ソースの episodes parquet 行から stats を取り出す。

    numeric_keys に入っている特徴は呼び出し側でトリム後の行から再計算するため、
    ここでは image/video 特徴 (と再計理対象外のキー) のみを返す。
    """
    features = src_dataset.meta.features
    stats: dict[str, dict] = {}
    for key in episode_row:
        if not key.startswith("stats/"):
            continue
        stat_key = key.removeprefix("stats/")
        parts = stat_key.split("/")
        if len(parts) != 2:
            continue
        feature_name, stat_name = parts
        if feature_name in numeric_keys:
            continue
        value = episode_row[key]
        if feature_name in features and features[feature_name]["dtype"] in ("image", "video") and stat_name != "count":
            # pandas が (C,1,1) 配列をネストした object 配列にしてしまうのを元に戻す
            # (lerobot の _copy_and_reindex_episodes_metadata と同じ処理)
            if isinstance(value, np.ndarray) and value.dtype == object:
                flat = []
                for item in value:
                    while isinstance(item, np.ndarray):
                        item = item.flatten()[0]
                    flat.append(item)
                value = np.array(flat, dtype=np.float64).reshape(-1, 1, 1)
            elif isinstance(value, np.ndarray) and value.ndim == 1:
                value = value.reshape(-1, 1, 1)
        stats.setdefault(feature_name, {})[stat_name] = value
    return stats


def _fresh_numeric_stats(
    ep_df: pd.DataFrame,
    features: dict,
) -> dict[str, dict]:
    """トリム後のデータ行から数値特徴の stats を再計算する。"""
    episode_data: dict[str, np.ndarray] = {}
    for key, ft in features.items():
        if ft["dtype"] in ("image", "video", "string", "language"):
            continue
        if key not in ep_df.columns:
            continue
        values = ep_df[key].values
        if len(values) == 0:
            continue
        if hasattr(values[0], "__len__"):
            episode_data[key] = np.stack(values)
        else:
            episode_data[key] = np.asarray(values)
    if not episode_data:
        return {}
    feats = {k: features[k] for k in episode_data}
    return compute_episode_stats(episode_data, feats)


def apply_curation(
    src_dataset: LeRobotDataset,
    curation: dict,
    output_root: Path,
    output_repo_id: str,
    log=logger.info,
) -> LeRobotDataset:
    """curation を適用した新しいデータセットを output_root に作成して返す。"""
    meta = src_dataset.meta
    if meta.episodes is None:
        raise RuntimeError("エピソードメタデータが読み込めていません")
    fps = meta.fps
    total = meta.total_episodes

    # ---- 1. 各エピソードの確定範囲を決める ----
    decisions: dict[int, tuple[int, int] | None] = {}  # ep -> None=削除 / (start, end)
    for ep_idx in range(total):
        entry = curation["episodes"].get(str(ep_idx), {})
        if entry.get("decision") == "delete":
            decisions[ep_idx] = None
            continue
        trim = entry.get("trim")
        if trim is None:
            decisions[ep_idx] = (0, int(meta.episodes[ep_idx]["length"]))
        else:
            decisions[ep_idx] = (int(trim[0]), int(trim[1]))

    kept = [ep for ep in range(total) if decisions[ep] is not None]
    deleted = [ep for ep in range(total) if decisions[ep] is None]
    if not kept:
        raise ValueError("すべてのエピソードが削除対象です")
    log(f"保持 {len(kept)} エピソード / 削除 {len(deleted)} エピソード "
        f"(削除対象: {deleted if len(deleted) <= 30 else str(deleted[:30]) + '...'} )")

    # ---- 2. 動画の実フレーム数を把握し、データ行を安全な範囲にクランプ ----
    log("動画ファイルのフレーム数を確認中...")
    file_frame_counts = compute_video_availability(src_dataset)

    eff_ranges: dict[int, tuple[int, int]] = {}
    clamped: list[str] = []
    for ep_idx in kept:
        s, e = decisions[ep_idx]
        length = int(meta.episodes[ep_idx]["length"])
        avail = episode_video_avail_frames(src_dataset, ep_idx, file_frame_counts)
        eff_s, eff_e = max(0, s), min(e, length, avail)
        if eff_s >= eff_e:
            raise ValueError(
                f"エピソード {ep_idx}: トリム範囲 [{s}, {e}) が有効なフレームを含みません "
                f"(長さ {length}, 動画利用可能 {avail})"
            )
        if (s, e) != (eff_s, eff_e):
            clamped.append(f"ep{ep_idx}: [{s},{e})→[{eff_s},{eff_e})")
        eff_ranges[ep_idx] = (eff_s, eff_e)
    if clamped:
        log("※ 動画フレーム不足のため範囲をクランプ: " + "; ".join(clamped[:10]) + ("..." if len(clamped) > 10 else ""))

    episode_mapping = {old: new for new, old in enumerate(kept)}

    # ---- 3. 出力メタデータ作成 ----
    if output_root.exists():
        raise FileExistsError(f"出力先が既に存在します: {output_root}")
    new_meta = LeRobotDatasetMetadata.create(
        repo_id=output_repo_id,
        fps=fps,
        features=meta.features,
        robot_type=meta.robot_type,
        root=output_root,
        use_videos=len(meta.video_keys) > 0,
    )

    # ---- 4. 動画のコピー/再エンコード ----
    log("動画を処理中...")
    video_metadata: dict[int, dict] = {new_idx: {} for new_idx in episode_mapping.values()}
    t0 = time.time()
    for video_key in meta.video_keys:
        encoder = encoder_config_from_video_info(meta.features.get(video_key, {}).get("info"))
        file_to_episodes: dict[tuple[int, int], list[int]] = {}
        for old_idx in kept:
            ep = meta.episodes[old_idx]
            ck = ep[f"videos/{video_key}/chunk_index"]
            fi = ep[f"videos/{video_key}/file_index"]
            file_to_episodes.setdefault((ck, fi), []).append(old_idx)

        for (ck, fi), eps_in_file in sorted(file_to_episodes.items()):
            src_video = src_dataset.root / meta.video_path.format(video_key=video_key, chunk_index=ck, file_index=fi)
            dst_video = new_meta.root / new_meta.video_path.format(video_key=video_key, chunk_index=ck, file_index=fi)
            dst_video.parent.mkdir(parents=True, exist_ok=True)
            n_file = file_frame_counts[(video_key, ck, fi)]

            all_eps_in_file = sorted(
                ep for ep in range(total)
                if meta.episodes[ep].get(f"videos/{video_key}/chunk_index") == ck
                and meta.episodes[ep].get(f"videos/{video_key}/file_index") == fi
            )
            file_untouched = all_eps_in_file == sorted(eps_in_file) and all(
                eff_ranges[ep] == (0, int(meta.episodes[ep]["length"])) for ep in eps_in_file
            )

            if file_untouched:
                shutil.copy(src_video, dst_video)
                for old_idx in eps_in_file:
                    new_idx = episode_mapping[old_idx]
                    ep = meta.episodes[old_idx]
                    video_metadata[new_idx][f"videos/{video_key}/chunk_index"] = ck
                    video_metadata[new_idx][f"videos/{video_key}/file_index"] = fi
                    video_metadata[new_idx][f"videos/{video_key}/from_timestamp"] = ep[f"videos/{video_key}/from_timestamp"]
                    video_metadata[new_idx][f"videos/{video_key}/to_timestamp"] = ep[f"videos/{video_key}/to_timestamp"]
            else:
                ranges = []
                for old_idx in sorted(eps_in_file, key=lambda x: episode_mapping[x]):
                    from_tick = round(meta.episodes[old_idx][f"videos/{video_key}/from_timestamp"] * fps)
                    to_tick = round(meta.episodes[old_idx][f"videos/{video_key}/to_timestamp"] * fps)
                    s, e = eff_ranges[old_idx]
                    keep_from = max(from_tick, min(from_tick + s, min(to_tick, n_file)))
                    keep_to = max(keep_from, min(from_tick + e, min(to_tick, n_file)))
                    ranges.append((keep_from, keep_to))
                log(f"  再エンコード: {video_key} chunk-{ck:03d}/file-{fi:03d} "
                    f"({len(ranges)} 範囲, ソース {n_file} フレーム)")
                _keep_episodes_from_video_with_av(src_video, dst_video, ranges, fps, encoder)
                cum = 0.0
                for old_idx in sorted(eps_in_file, key=lambda x: episode_mapping[x]):
                    new_idx = episode_mapping[old_idx]
                    new_len = eff_ranges[old_idx][1] - eff_ranges[old_idx][0]
                    video_metadata[new_idx][f"videos/{video_key}/chunk_index"] = ck
                    video_metadata[new_idx][f"videos/{video_key}/file_index"] = fi
                    video_metadata[new_idx][f"videos/{video_key}/from_timestamp"] = cum
                    video_metadata[new_idx][f"videos/{video_key}/to_timestamp"] = cum + new_len / fps
                    cum += new_len / fps
    log(f"動画処理完了 ({time.time() - t0:.1f} 秒)")

    # ---- 5. データ parquet のフィルタ・再インデックス ----
    log("データ parquet を処理中...")
    data_file_to_episodes: dict[Path, list[int]] = {}
    for old_idx in kept:
        data_file_to_episodes.setdefault(src_dataset.meta.get_data_file_path(old_idx), []).append(old_idx)

    # タスクはそのまま引き継ぐ (保存 → 新インデックス mapping)
    kept_tasks = []
    for old_idx in kept:
        for t in meta.episodes[old_idx]["tasks"]:
            if t not in kept_tasks:
                kept_tasks.append(t)
    new_meta.save_episode_tasks(kept_tasks)
    task_mapping = {}
    for old_task_idx in range(len(src_dataset.meta.tasks)):
        task_name = src_dataset.meta.tasks.iloc[old_task_idx].name
        new_idx = new_meta.get_task_index(task_name)
        if new_idx is not None:
            task_mapping[old_task_idx] = new_idx

    global_index = 0
    data_metadata: dict[int, dict] = {}
    ep_frames: dict[int, pd.DataFrame] = {}  # 新エピソードごとの行 (stats 再計算用)

    for src_path in sorted(data_file_to_episodes.keys()):
        df = pd.read_parquet(src_dataset.root / src_path)
        parts = []
        for old_idx in sorted(data_file_to_episodes[src_path]):
            s, e = eff_ranges[old_idx]
            ep_df = df[(df["episode_index"] == old_idx) & (df["frame_index"] >= s) & (df["frame_index"] < e)]
            if len(ep_df) == 0:
                raise ValueError(f"エピソード {old_idx}: データ行が空になりました (範囲 [{s},{e}))")
            ep_df = ep_df.copy()
            ep_df["frame_index"] = ep_df["frame_index"] - s
            ep_df["timestamp"] = ep_df["frame_index"] / fps
            ep_df["index"] = range(global_index, global_index + len(ep_df))
            ep_df["episode_index"] = episode_mapping[old_idx]
            ep_df["task_index"] = ep_df["task_index"].replace(task_mapping)
            parts.append(ep_df)
            ep_frames[episode_mapping[old_idx]] = ep_df.reset_index(drop=True)
            global_index += len(ep_df)
        out_df = pd.concat(parts, ignore_index=True)

        src_ep = meta.episodes[min(data_file_to_episodes[src_path])]
        ck = src_ep["data/chunk_index"]
        fi = src_ep["data/file_index"]
        dst_path = new_meta.root / DEFAULT_DATA_PATH.format(chunk_index=ck, file_index=fi)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        _write_parquet(out_df, dst_path, new_meta)

        for old_idx in data_file_to_episodes[src_path]:
            new_idx = episode_mapping[old_idx]
            sub = out_df[out_df["episode_index"] == new_idx]
            data_metadata[new_idx] = {
                "data/chunk_index": ck,
                "data/file_index": fi,
                "dataset_from_index": int(sub["index"].min()),
                "dataset_to_index": int(sub["index"].max()) + 1,
            }

    # ---- 6. エピソードメタデータ + 統計 ----
    log("エピソードメタデータと統計を書き込み中...")
    numeric_keys = {
        k for k, ft in meta.features.items() if ft["dtype"] not in ("image", "video", "string", "language")
    }
    all_stats = []
    total_frames = 0
    for old_idx, new_idx in sorted(episode_mapping.items(), key=lambda x: x[1]):
        src_row = _load_episode_with_stats(src_dataset, old_idx)
        ep_df = ep_frames[new_idx]
        new_len = len(ep_df)

        episode_stats = _extract_source_stats(src_dataset, src_row, numeric_keys)
        episode_stats.update(_fresh_numeric_stats(ep_df, meta.features))
        all_stats.append(episode_stats)

        episode_dict = {
            "episode_index": new_idx,
            "tasks": meta.episodes[old_idx]["tasks"],
            "length": new_len,
        }
        episode_dict.update(data_metadata[new_idx])
        episode_dict.update(video_metadata[new_idx])
        episode_dict.update(flatten_dict({"stats": episode_stats}))
        new_meta._save_episode_metadata(episode_dict)
        total_frames += new_len

    new_meta.finalize()
    new_meta.info.total_episodes = len(kept)
    new_meta.info.total_frames = total_frames
    new_meta.info.total_tasks = len(new_meta.tasks) if new_meta.tasks is not None else 0
    new_meta.info.splits = {"train": f"0:{len(kept)}"}
    write_info(new_meta.info, new_meta.root)

    aggregated = aggregate_stats(all_stats)
    filtered = {k: v for k, v in aggregated.items() if k in new_meta.features}
    write_stats(filtered, new_meta.root)

    log(f"完了: {len(kept)} エピソード / {total_frames} フレーム → {output_root}")

    # ---- 7. 検証ロード ----
    new_dataset = LeRobotDataset(repo_id=output_repo_id, root=output_root)
    if new_dataset.meta.total_episodes != len(kept) or new_dataset.num_frames != total_frames:
        raise RuntimeError(
            f"検証失敗: 出力メタデータが不一致 "
            f"(episodes {new_dataset.meta.total_episodes}/{len(kept)}, "
            f"frames {new_dataset.num_frames}/{total_frames})"
        )
    return new_dataset


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-id", required=True, help="ソースデータセットの repo-id (例: local/mydataset)")
    ap.add_argument("--root", required=True, help="ソースデータセットのルートディレクトリ")
    ap.add_argument("--curation", default=None, help="curation.json のパス (デフォルト: <root>/curation.json)")
    ap.add_argument("--output-repo-id", default=None, help="出力 repo-id (デフォルト: <repo-id>_curated)")
    ap.add_argument("--output-root", default=None, help="出力ルート (デフォルト: <root>_curated)")
    args = ap.parse_args()

    src_root = Path(args.root).resolve()
    curation_path = Path(args.curation) if args.curation else src_root / "curation.json"
    if not curation_path.exists():
        sys.exit(f"curation ファイルがありません: {curation_path}")
    output_repo_id = args.output_repo_id or f"{args.repo_id}_curated"
    output_root = Path(args.output_root).resolve() if args.output_root else src_root.parent / f"{src_root.name}_curated"

    src_dataset = LeRobotDataset(repo_id=args.repo_id, root=src_root)
    curation = load_curation(curation_path)
    apply_curation(src_dataset, curation, output_root, output_repo_id)


if __name__ == "__main__":
    main()
