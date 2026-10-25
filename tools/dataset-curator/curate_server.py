#!/usr/bin/env python
"""LeRobot データセット・キュレーションサーバー.

指定したデータセットの全エピソードをブラウザで閲覧し、エピソード削除と
フレーム範囲 (in/out) トリムをマークアップして curation.json に保存、
新しいキュレーション済みデータセットとして書き出すためのローカル Web アプリ。

使い方:
    python curate_server.py --repo-id local/mydataset --root /path/to/mydataset \
        [--host 127.0.0.1] [--port 8787]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
from collections import deque
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from apply_curation import (
    apply_curation,
    count_video_frames,
    load_curation,
)

STATIC_DIR = Path(__file__).parent / "static"


class AppState:
    def __init__(self, repo_id: str, root: Path):
        self.repo_id = repo_id
        self.root = root
        self.info = json.loads((root / "meta" / "info.json").read_text())
        self.fps = self.info["fps"]

        # エピソードメタデータ読み込み
        dfs = [
            pd.read_parquet(p)
            for p in sorted((root / "meta" / "episodes").glob("*/*.parquet"))
        ]
        eps_df = pd.concat(dfs, ignore_index=True).sort_values("episode_index")
        self.video_keys = [
            k for k, ft in self.info["features"].items() if ft["dtype"] == "video"
        ]
        self.tasks_df = pd.read_parquet(root / "meta" / "tasks.parquet")

        # 動画の実フレーム数 (chunk/file 単位)
        print("動画フレーム数を確認中...")
        self.file_frames: dict[tuple[str, int, int], int] = {}
        for vk in self.video_keys:
            keys = {
                (
                    int(r[f"videos/{vk}/chunk_index"]),
                    int(r[f"videos/{vk}/file_index"]),
                )
                for _, r in eps_df.iterrows()
            }
            for ck, fi in sorted(keys):
                p = root / self.info["video_path"].format(
                    video_key=vk, chunk_index=ck, file_index=fi
                )
                self.file_frames[(vk, ck, fi)] = count_video_frames(p)

        # エピソードごとの情報を構築
        task_names = {}
        for task_str, row in self.tasks_df.iterrows():
            task_names[int(row["task_index"])] = str(task_str)
        self.tasks_by_index = task_names

        self.episodes: list[dict] = []
        for _, r in eps_df.iterrows():
            ep: dict = {
                "index": int(r["episode_index"]),
                "length": int(r["length"]),
                "tasks": [str(t) for t in r["tasks"]],
                "data_chunk": int(r["data/chunk_index"]),
                "data_file": int(r["data/file_index"]),
                "videos": {},
            }
            avail = int(r["length"])
            for vk in self.video_keys:
                ck = int(r[f"videos/{vk}/chunk_index"])
                fi = int(r[f"videos/{vk}/file_index"])
                from_ts = float(r[f"videos/{vk}/from_timestamp"])
                to_ts = float(r[f"videos/{vk}/to_timestamp"])
                n_file = self.file_frames[(vk, ck, fi)]
                rel = self.info["video_path"].format(video_key=vk, chunk_index=ck, file_index=fi)
                ep["videos"][vk] = {
                    "url": f"/media/{rel}",
                    "chunk": ck,
                    "file": fi,
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                    "file_frames": n_file,
                }
                from_tick = round(from_ts * self.fps)
                to_tick = round(to_ts * self.fps)
                avail = min(avail, max(0, min(to_tick, n_file) - from_tick))
            ep["avail"] = avail
            self.episodes.append(ep)

        # 適用ジョブ状態
        self.apply_lock = threading.Lock()
        self.apply_running = False
        self.apply_log: deque[str] = deque(maxlen=500)
        self.apply_error: str | None = None
        self.apply_result: dict | None = None

    # ---------------- curation project ----------------

    @property
    def curation_path(self) -> Path:
        return self.root / "curation.json"

    def load_project(self) -> dict:
        if self.curation_path.exists():
            return json.loads(self.curation_path.read_text(encoding="utf-8"))
        return {"version": 1, "episodes": {}}

    def save_project(self, data: dict) -> None:
        tmp = self.curation_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.curation_path)

    # ---------------- signals ----------------

    @lru_cache(maxsize=8)
    def _load_data_file(self, chunk: int, file: int) -> pd.DataFrame:
        path = self.root / self.info["data_path"].format(chunk_index=chunk, file_index=file)
        return pd.read_parquet(path)

    def episode_signals(self, ep_index: int) -> dict:
        ep = self.episodes[ep_index]
        df = self._load_data_file(ep["data_chunk"], ep["data_file"])
        sub = df[df["episode_index"] == ep_index].sort_values("frame_index")
        state_names = self.info["features"].get("observation.state", {}).get("names", [])
        return {
            "fps": self.fps,
            "length": ep["length"],
            "avail": ep["avail"],
            "state_names": list(state_names),
            "state": [[float(x) for x in v] for v in sub["observation.state"]],
            "action": [[float(x) for x in v] for v in sub["action"]],
        }


state: AppState | None = None
app = FastAPI(title="LeRobot Dataset Curator")


# ---------------- static ----------------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/static/{rel:path}")
def static_files(rel: str):
    p = (STATIC_DIR / rel).resolve()
    if not p.is_relative_to(STATIC_DIR.resolve()) or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)


# ---------------- API ----------------

@app.get("/api/dataset")
def api_dataset():
    return {
        "repo_id": state.repo_id,
        "root": str(state.root),
        "fps": state.fps,
        "video_keys": state.video_keys,
        "tasks": state.tasks_by_index,
        "episodes": state.episodes,
        "curation_path": str(state.curation_path),
    }


@app.get("/api/episode/{ep_index}/signals")
def api_signals(ep_index: int):
    if ep_index < 0 or ep_index >= len(state.episodes):
        raise HTTPException(404, "episode index out of range")
    return state.episode_signals(ep_index)


@app.get("/api/project")
def api_get_project():
    return state.load_project()


class ProjectPayload(BaseModel):
    version: int = 1
    episodes: dict


@app.post("/api/project")
def api_save_project(payload: ProjectPayload):
    state.save_project(payload.model_dump())
    return {"ok": True, "saved_at": time.time()}


class ApplyPayload(BaseModel):
    output_repo_id: str | None = None
    output_root: str | None = None
    overwrite: bool = False


@app.post("/api/apply")
def api_apply(payload: ApplyPayload):
    with state.apply_lock:
        if state.apply_running:
            raise HTTPException(409, "適用ジョブが既に実行中です")
        state.apply_running = True
    state.apply_log.clear()
    state.apply_error = None
    state.apply_result = None

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        state.apply_log.append(line)
        print(line, flush=True)

    def run():
        try:
            from lerobot.datasets.lerobot_dataset import LeRobotDataset

            output_repo_id = payload.output_repo_id or f"{state.repo_id}_curated"
            output_root = Path(payload.output_root) if payload.output_root else (
                state.root.parent / f"{state.root.name}_curated"
            )
            if output_root.exists():
                if payload.overwrite and (output_root / "meta" / "info.json").exists():
                    log(f"既存の出力先を削除: {output_root}")
                    shutil.rmtree(output_root)
                else:
                    raise FileExistsError(
                        f"出力先が既に存在します: {output_root} (上書きする場合は overwrite を指定)"
                    )
            log(f"curation を読み込み: {state.curation_path}")
            curation = load_curation(state.curation_path)
            log(f"ソースデータセットを読み込み中: {state.repo_id}")
            src = LeRobotDataset(repo_id=state.repo_id, root=state.root)
            dataset = apply_curation(src, curation, output_root, output_repo_id, log=log)
            state.apply_result = {
                "output_root": str(output_root),
                "output_repo_id": output_repo_id,
                "total_episodes": dataset.meta.total_episodes,
                "total_frames": dataset.num_frames,
            }
            log("適用が完了しました ✓")
        except Exception as e:  # noqa: BLE001
            state.apply_error = f"{type(e).__name__}: {e}"
            log(f"エラー: {state.apply_error}")
        finally:
            state.apply_running = False

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True, "started": True}


@app.get("/api/apply/status")
def api_apply_status():
    return {
        "running": state.apply_running,
        "error": state.apply_error,
        "result": state.apply_result,
        "log": list(state.apply_log),
    }


# ---------------- media serving (Range 対応) ----------------

@app.get("/media/{relpath:path}")
def api_video(relpath: str, request: Request):
    videos_root = (state.root / "videos").resolve()
    p = (state.root / relpath).resolve()
    if not p.is_relative_to(videos_root) or not p.is_file():
        raise HTTPException(404)
    size = p.stat().st_size
    range_header = request.headers.get("range")

    def chunk_iter(start: int, end: int):
        with open(p, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                buf = f.read(min(1024 * 1024, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf

    if range_header and range_header.startswith("bytes="):
        try:
            spec = range_header.removeprefix("bytes=")
            if spec.startswith("-"):
                length = int(spec[1:])
                start = max(0, size - length)
                end = size - 1
            else:
                start_s, _, end_s = spec.partition("-")
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                return JSONResponse(
                    {"detail": "invalid range"}, status_code=416,
                    headers={"Content-Range": f"bytes */{size}"},
                )
            return StreamingResponse(
                chunk_iter(start, end),
                status_code=206,
                media_type="video/mp4",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(end - start + 1),
                },
            )
        except ValueError:
            pass

    return StreamingResponse(
        chunk_iter(0, size - 1),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes", "Content-Length": str(size)},
    )


def main():
    global state
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-id", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    state = AppState(args.repo_id, root)
    print(f"データセット: {args.repo_id} ({len(state.episodes)} エピソード)")
    print(f"http://{args.host}:{args.port} をブラウザで開いてください")

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
