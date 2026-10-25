"""Copy a kept dataset tree to another PC and drop the Pi copy.

Frames stay on the Pi while the episode is captured. A take is copied only
after it is kept: before the next Start, and once more at session end.
``finalize`` deletes the local tree only when the final sync succeeded.
A second ``finalize`` (the video manager and ``record()`` both call it) does
not sync again after that delete. A dropped link keeps the Pi files.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SSH_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
# accept-new stores a first-seen host key. A changed key still fails closed.
_SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
    "-o",
    "StrictHostKeyChecking=accept-new",
]


@dataclass(frozen=True)
class OffloadSettings:
    """Where a recorded dataset is copied after each saved episode."""

    ssh: str
    remote_dir: str
    delete_local: bool


def load_settings() -> OffloadSettings | None:
    """Read ``SO101_DATASET_SSH`` / ``DIR`` / ``DELETE_LOCAL``.

    An empty SSH target means the dataset stays on the Pi. A target without
    an absolute remote directory is ignored so a half-filled env file cannot
    send data to an unexpected path.
    """
    ssh = os.environ.get("SO101_DATASET_SSH", "").strip()
    if not ssh:
        return None
    remote_dir = os.environ.get("SO101_DATASET_DIR", "").strip().rstrip("/")
    if not _SSH_RE.fullmatch(ssh):
        print(
            f"SO101_DATASET_SSH の形式が user@host ではありません: {ssh!r}。Pi に残します。",
            file=sys.stderr,
        )
        return None
    if not remote_dir.startswith("/") or ".." in Path(remote_dir).parts:
        print(
            "SO101_DATASET_DIR は絶対パスにしてください。Pi に残します。",
            file=sys.stderr,
        )
        return None
    delete_raw = os.environ.get("SO101_DATASET_DELETE_LOCAL", "1").strip()
    delete_local = delete_raw in {"1", "true", "True", "yes"}
    return OffloadSettings(ssh=ssh, remote_dir=remote_dir, delete_local=delete_local)


def remote_dataset_path(remote_dir: str, repo_id: str) -> str:
    """Remote directory for one ``repo_id``, including the ``local/...`` prefix."""
    if not _REPO_RE.fullmatch(repo_id) or ".." in Path(repo_id).parts:
        raise ValueError(f"repo_id に使えない文字があります: {repo_id!r}")
    return f"{remote_dir}/{repo_id}"


def rsync_argv(local_root: Path, ssh: str, remote_path: str) -> list[str]:
    """Argv for an incremental copy. The trailing slash syncs the tree contents."""
    ssh_cmd = " ".join(["ssh", *_SSH_OPTS])
    return [
        "rsync",
        "-a",
        "--partial",
        "-e",
        ssh_cmd,
        f"{local_root}/",
        f"{ssh}:{remote_path}/",
    ]


def _run(argv: list[str]) -> int:
    completed = subprocess.run(argv, check=False)
    return completed.returncode


def safe_to_delete(root: Path) -> bool:
    """Refuse to remove anything that is not one LeRobot dataset directory."""
    resolved = root.resolve()
    if resolved == Path.home().resolve() or resolved == Path("/"):
        return False
    if len(resolved.parts) < 4:
        return False
    return (resolved / "meta" / "info.json").is_file()


class OffloadSession:
    """One recording session. Copy after a keep; delete only at the end."""

    def __init__(self, settings: OffloadSettings, runner: object | None = None) -> None:
        self.settings = settings
        self._run = _run if runner is None else runner
        self.events: dict | None = None
        self.needs_sync = False
        self.ever_saved = False
        self.completed = False
        self.failed = False
        self._root: Path | None = None
        self._repo_id: str | None = None
        self._warned = False

    def note_saved(self, root: Path, repo_id: str) -> None:
        """Remember a kept episode. The copy itself waits until the arm is idle."""
        self._root = root
        self._repo_id = repo_id
        self.ever_saved = True
        self.needs_sync = True
        self.completed = False

    def sync_saved(self) -> bool:
        """Copy the tree now. Used before the next Start, not during the control loop."""
        if self.completed or not self.needs_sync:
            return not self.failed
        if self._root is None or self._repo_id is None:
            return False
        if self.events is not None:
            self.events["phase"] = "upload"
        ok = self._sync(self._root, self._repo_id)
        if ok:
            self.needs_sync = False
            self.failed = False
            return True
        self.failed = True
        return False

    def _sync(self, root: Path, repo_id: str) -> bool:
        try:
            remote_path = remote_dataset_path(self.settings.remote_dir, repo_id)
        except ValueError as exc:
            self._warn(str(exc))
            return False
        mkdir = ["ssh", *_SSH_OPTS, self.settings.ssh, "mkdir", "-p", remote_path]
        if self._run(mkdir) != 0:
            self._warn(
                f"転送先にディレクトリを作れません: {self.settings.ssh}:{remote_path}。"
                f"データセットは Pi に残します: {root}"
            )
            return False
        if self._run(rsync_argv(root, self.settings.ssh, remote_path)) != 0:
            self._warn(
                f"転送に失敗しました: {self.settings.ssh}:{remote_path}。"
                f"データセットは Pi に残します: {root}"
            )
            return False
        return True

    def _warn(self, text: str) -> None:
        if self._warned:
            return
        self._warned = True
        print(text, file=sys.stderr, flush=True)

    def finish(self, root: Path, repo_id: str) -> bool:
        """Sync the kept tree once more, then delete the Pi copy.

        Returns True when there is nothing to send, or the remote tree is
        complete. A second call after success does not rsync again. A failed
        copy leaves the Pi directory in place.
        """
        if self.completed:
            return True
        if not self.ever_saved:
            self.completed = True
            return True
        if self.events is not None:
            self.events["phase"] = "upload"
        if not self._sync(root, repo_id):
            self.failed = True
            self.needs_sync = True
            return False
        self.needs_sync = False
        self.failed = False
        if not self.settings.delete_local:
            self.completed = True
            return True
        if not safe_to_delete(root):
            self._warn(f"転送は済みですが、Pi 側の削除を見送りました: {root}")
            self.failed = True
            return False
        if root.exists():
            shutil.rmtree(root)
        self.completed = True
        return True


_CURRENT: OffloadSession | None = None


def current_session() -> OffloadSession | None:
    """The session installed for this process, or None when offload is off."""
    return _CURRENT


def install_dataset_offload() -> None:
    """Patch dataset save/finalize so a kept episode is pushed later."""
    global _CURRENT
    settings = load_settings()
    if settings is None:
        _CURRENT = None
        print(
            "データセットは Pi に残します。送り先は configs/dataset.local.env の SO101_DATASET_SSH です。",
            flush=True,
        )
        return
    try:
        import lerobot.datasets.lerobot_dataset as dataset_mod
    except ImportError:
        _CURRENT = None
        print("lerobot が無いので転送をスキップし、Pi に残します。", file=sys.stderr)
        return

    session = OffloadSession(settings)
    _CURRENT = session
    original_save = dataset_mod.LeRobotDataset.save_episode
    original_finalize = dataset_mod.LeRobotDataset.finalize
    destination = f"{settings.ssh}:{settings.remote_dir}/<repo_id>"
    print(f"残したエピソードは {destination} へ、次の開始前とセッションの最後に転送します。", flush=True)

    def save_episode(self: object, *args: object, **kwargs: object) -> None:
        original_save(self, *args, **kwargs)
        session.note_saved(Path(self.root), str(self.repo_id))

    def finalize(self: object, *args: object, **kwargs: object) -> None:
        original_finalize(self, *args, **kwargs)
        if session.completed:
            return
        root = Path(self.root)
        repo_id = str(self.repo_id)
        remote = f"{settings.ssh}:{settings.remote_dir}/{repo_id}"
        if not session.ever_saved:
            episodes = getattr(self, "num_episodes", None)
            if episodes == 0 and safe_to_delete(root):
                shutil.rmtree(root, ignore_errors=True)
                print(f"残した本がないので Pi の空データセットを消しました: {root}", flush=True)
            session.completed = True
            return
        if session.finish(root, repo_id):
            if settings.delete_local:
                print(f"データセットを移しました（Pi 側は削除）: {remote}", flush=True)
            else:
                print(f"データセットをコピーしました（Pi 側も残しています）: {remote}", flush=True)
            return
        print(f"転送できなかったので Pi に残しています: {root}", flush=True)

    dataset_mod.LeRobotDataset.save_episode = save_episode
    dataset_mod.LeRobotDataset.finalize = finalize
