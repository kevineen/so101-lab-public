"""Model catalog for phone-side switching during ready."""

from __future__ import annotations

import json
import logging
import os
import pickle  # nosec
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("infer_buttons")


@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    policy_type: str
    path: str
    actions_per_chunk: int
    optional: bool = False

    @property
    def short_name(self) -> str:
        return Path(self.path.rstrip("/")).name
        # if path ends with pretrained_model, prefer parent run name via hook.model_label


def _default_catalog_path() -> Path:
    """解決順: configs/infer_models.local.json（gitignore・実機の path を置く）→
    configs/infer_models.snakebowl.json（example）。SO101_INFER_MODELS で差し替え可。"""
    root = Path(__file__).resolve().parents[1]
    local = root / "configs" / "infer_models.local.json"
    if local.is_file():
        return local
    return root / "configs" / "infer_models.snakebowl.json"


def _resolve_entry_path(raw: str) -> str:
    """カタログの path は policy server 側ホストのチェックポイント。

    $VAR と ~ は**クライアント側で**展開してから送る。ラボ内は同一ユーザー名
    （~/robot 配置）を前提としているため $HOME/robot/... と書ける。クライアントと
    サーバでユーザー名が違う場合は、サーバ側の絶対パスをそのまま書くこと。
    """
    return os.path.expandvars(os.path.expanduser(raw))


def load_catalog(path: str | Path | None = None) -> list[ModelEntry]:
    """Load models from JSON. Missing optional checkpoints are skipped."""
    raw_path = path or os.environ.get("SO101_INFER_MODELS") or _default_catalog_path()
    file_path = Path(raw_path).expanduser()
    if not file_path.is_file():
        logger.warning("infer model catalog missing: %s", file_path)
        return []
    data = json.loads(file_path.read_text(encoding="utf-8"))
    entries: list[ModelEntry] = []
    for row in data.get("models") or []:
        if not isinstance(row, dict):
            continue
        entry = ModelEntry(
            id=str(row.get("id") or "").strip() or "M",
            label=str(row.get("label") or row.get("policy_type") or "model").strip(),
            policy_type=str(row.get("policy_type") or "").strip(),
            path=_resolve_entry_path(str(row.get("path") or "").strip()),
            actions_per_chunk=int(row.get("actions_per_chunk") or 0),
            optional=bool(row.get("optional")),
        )
        if not entry.policy_type or not entry.path or entry.actions_per_chunk < 1:
            continue
        # Weights live on the policy server (WSL). Optional rows stay hidden until
        # SO101_INFER_INCLUDE_OPTIONAL=1 (e.g. after SmolVLA finishes training).
        if entry.optional and os.environ.get("SO101_INFER_INCLUDE_OPTIONAL", "0") != "1":
            logger.info("skip optional model %s (set SO101_INFER_INCLUDE_OPTIONAL=1 to show)", entry.id)
            continue
        entries.append(entry)
    return entries


def catalog_task(path: str | Path | None = None) -> str:
    raw_path = path or os.environ.get("SO101_INFER_MODELS") or _default_catalog_path()
    file_path = Path(raw_path).expanduser()
    if not file_path.is_file():
        return ""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return str(data.get("task") or "").strip()


def index_for_path(entries: list[ModelEntry], path: str) -> int:
    norm = (path or "").rstrip("/")
    if not norm:
        return 0
    for i, entry in enumerate(entries):
        if entry.path.rstrip("/") == norm:
            return i
    # Match by run directory name when both end with pretrained_model.
    needle = Path(norm)
    if needle.name == "pretrained_model":
        run = needle.parent.name if needle.parent.name != "last" else needle.parents[2].name
        for i, entry in enumerate(entries):
            if run and run in entry.path.rstrip("/"):
                return i
    else:
        for i, entry in enumerate(entries):
            if Path(entry.path.rstrip("/")).name == needle.name:
                return i
    return 0


def send_policy(client: object, entry: ModelEntry) -> None:
    """Ask the policy server to load ``entry`` (blocks until loaded)."""
    from lerobot.transport import services_pb2

    policy_config = getattr(client, "policy_config", None)
    config = getattr(client, "config", None)
    stub = getattr(client, "stub", None)
    if policy_config is None or stub is None:
        raise RuntimeError("client is missing policy_config or stub")

    policy_config.policy_type = entry.policy_type
    policy_config.pretrained_name_or_path = entry.path
    policy_config.actions_per_chunk = entry.actions_per_chunk
    if config is not None:
        config.policy_type = entry.policy_type
        config.pretrained_name_or_path = entry.path
        config.actions_per_chunk = entry.actions_per_chunk

    with getattr(client, "latest_action_lock"):
        client.latest_action = -1
    client.action_chunk_size = -1

    payload = pickle.dumps(policy_config)
    stub.SendPolicyInstructions(services_pb2.PolicySetup(data=payload))
