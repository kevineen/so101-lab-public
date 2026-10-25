"""Drop-in logger that records lerobot-train metrics to local MLflow.

``lerobot-train`` constructs ``WandBLogger`` when ``--wandb.enable=true``.
The lab entrypoint replaces that class with this one, so the training loop
stays in the vendor checkout and the curves land in the local store.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

from tracking.settings import MlflowSettings, load_settings

logger = logging.getLogger(__name__)

# Scalar hyperparameters only. Dataset stats and image features stay out of
# the param table; the full config is stored once as a small JSON artifact.
# The policy.* paths below are the usual experiment axes (chunk / horizon /
# regularization); ones a policy does not have simply stay absent.
_PARAM_PATHS = (
    "seed",
    "steps",
    "batch_size",
    "num_workers",
    "log_freq",
    "save_freq",
    "eval_steps",
    "job_name",
    "output_dir",
    "policy.type",
    "policy.device",
    "policy.push_to_hub",
    "policy.path",
    "policy.chunk_size",
    "policy.n_action_steps",
    "policy.horizon",
    "policy.kl_weight",
    "policy.num_inference_steps",
    "dataset.repo_id",
    "dataset.root",
    "optimizer.lr",
)
_CAMERA_PREFIX = "observation.images."
_MAX_PARAM_LEN = 500
_MAX_CONFIG_BYTES = 5_000_000
_RUN_ID_NAME = "mlflow_run_id.txt"


def select_params(payload: dict[str, Any]) -> dict[str, str]:
    """Pick short scalar hyperparameters from a draccus-encoded config."""
    selected: dict[str, str] = {}
    for path in _PARAM_PATHS:
        value = _lookup(payload, path)
        if value is None or isinstance(value, (dict, list, tuple)):
            continue
        text = str(value)
        if len(text) > _MAX_PARAM_LEN:
            text = text[:_MAX_PARAM_LEN]
        selected[path] = text
    cameras = select_cameras(payload)
    if cameras:
        selected["obs_cameras"] = cameras
    return selected


def select_cameras(payload: dict[str, Any]) -> str:
    """Camera keys the policy consumes, e.g. ``front+wrist``.

    The camera set (wrist-only vs front+wrist) is a first-class experiment
    axis, so it is logged as one queryable param instead of hiding inside the
    JSON artifact.
    """
    features = _lookup(payload, "policy.input_features")
    if not isinstance(features, dict):
        return ""
    keys = sorted(
        key[len(_CAMERA_PREFIX):]
        for key in features
        if isinstance(key, str) and key.startswith(_CAMERA_PREFIX)
    )
    return "+".join(keys)


def _lookup(payload: dict[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
    elif hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            number = float(value.item())
        except (TypeError, ValueError):
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def tracking_uri_for(settings: MlflowSettings) -> tuple[str, bool]:
    """Return ``(uri, via_http)``.

    An explicit ``MLFLOW_TRACKING_URI`` wins. Otherwise use the local server
    when its port accepts connections, so the UI and the client share one
    writer. If the server is down, write the sqlite file directly.
    """
    explicit = os.environ.get("MLFLOW_TRACKING_URI")
    if explicit:
        via_http = explicit.startswith("http://") or explicit.startswith("https://")
        return explicit, via_http
    probe_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    if _port_open(probe_host, settings.port):
        return f"http://{probe_host}:{settings.port}", True
    return settings.sqlite_uri, False


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_experiment(settings: MlflowSettings, via_http: bool) -> None:
    """Create or select the lab experiment in the local MLflow store."""
    import mlflow

    client = mlflow.MlflowClient()
    existing = client.get_experiment_by_name(settings.experiment)
    if existing is not None:
        if existing.lifecycle_stage == "deleted":
            client.restore_experiment(existing.experiment_id)
        mlflow.set_experiment(settings.experiment)
        return
    artifact_location = None
    if not via_http:
        settings.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_location = settings.artifact_dir.resolve().as_uri()
    client.create_experiment(settings.experiment, artifact_location=artifact_location)
    mlflow.set_experiment(settings.experiment)


class MLflowLogger:
    """Records train/eval scalars to the local MLflow experiment.

    Checkpoint weights and eval videos stay on the training output directory.
    Copying them into the tracking store is opt-in (``SO101_MLFLOW_LOG_MEDIA=1``)
    because those files are large. The store itself is gitignored either way.
    """

    def __init__(self, cfg: Any):
        os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
        import mlflow

        self._mlflow = mlflow
        self._cfg = cfg
        self.log_dir = Path(cfg.output_dir)
        self.job_name = cfg.job_name
        self.env_fps = cfg.env.fps if getattr(cfg, "env", None) else None
        self._log_media = os.environ.get("SO101_MLFLOW_LOG_MEDIA", "").strip() in {"1", "true", "True"}
        settings = load_settings()
        uri, via_http = tracking_uri_for(settings)
        os.environ["MLFLOW_TRACKING_URI"] = uri
        os.environ.setdefault("MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING", "false")
        mlflow.set_tracking_uri(uri)
        self._ensure_experiment(settings, via_http)
        run_id = self._resume_run_id()
        mlflow.start_run(run_id=run_id, run_name=None if run_id else self.job_name)
        active = mlflow.active_run()
        if active is None:
            raise RuntimeError("MLflow did not start a run")
        self.run_id = active.info.run_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / _RUN_ID_NAME).write_text(self.run_id + "\n", encoding="utf-8")
        self._log_params_and_config()
        notes = getattr(getattr(cfg, "wandb", None), "notes", None)
        if notes:
            mlflow.set_tag("mlflow.note.content", str(notes)[:5000])
        mlflow.set_tag("job_name", str(self.job_name))
        where = "tracking server" if via_http else "sqlite file"
        logger.info("MLflow run %s -> %s (%s)", self.run_id, uri, where)
        if not via_http:
            logger.info(
                "UI を見るには別ターミナルで ./scripts/start_mlflow.sh を起動する（http://127.0.0.1:%s）",
                settings.port,
            )

    def _ensure_experiment(self, settings: MlflowSettings, via_http: bool) -> None:
        ensure_experiment(settings, via_http)

    def _resume_run_id(self) -> str | None:
        if not getattr(self._cfg, "resume", False):
            return None
        path = self.log_dir / _RUN_ID_NAME
        if not path.is_file():
            logger.warning("resume だが %s が無いので新しい MLflow run を作る", path)
            return None
        run_id = path.read_text(encoding="utf-8").strip()
        return run_id or None

    def _log_params_and_config(self) -> None:
        to_dict = getattr(self._cfg, "to_dict", None)
        if not callable(to_dict):
            return
        try:
            payload = to_dict()
        except Exception:
            logger.warning("train config を MLflow に書けなかった", exc_info=True)
            return
        if not isinstance(payload, dict):
            return
        params = select_params(payload)
        if params:
            self._mlflow.log_params(params)
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        if len(encoded) > _MAX_CONFIG_BYTES:
            logger.warning("train config が %s bytes あるので MLflow artifact を省略", len(encoded))
            return
        # Keep the training output dir free of a second config copy. The artifact
        # store (gitignored) holds this JSON.
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "mlflow_train_config.json"
            dest.write_bytes(encoded)
            self._mlflow.log_artifact(str(dest))

    def log_dict(
        self,
        data: dict[str, Any],
        step: int | None = None,
        mode: str = "train",
        custom_step_key: str | None = None,
    ) -> None:
        if mode not in {"train", "eval"}:
            raise ValueError(mode)
        if step is None and custom_step_key is None:
            raise ValueError("Either step or custom_step_key must be provided.")
        metric_step = step
        if custom_step_key is not None:
            metric_step = int(_as_float(data.get(custom_step_key)) or 0)
        if metric_step is None:
            raise ValueError("step is required when custom_step_key is absent")
        for key, value in data.items():
            if custom_step_key is not None and key == custom_step_key:
                continue
            number = _as_float(value)
            if number is None:
                continue
            self._mlflow.log_metric(f"{mode}/{key}", number, step=int(metric_step))

    def log_policy(self, checkpoint_dir: Path) -> None:
        """Record the checkpoint path. Weights stay in ``output_dir``."""
        path = Path(checkpoint_dir)
        self._mlflow.set_tag("last_checkpoint", str(path))
        config_file = path / "pretrained_model" / "config.json"
        if config_file.is_file():
            self._mlflow.log_artifact(str(config_file), artifact_path=f"checkpoints/{path.name}")

    def log_video(self, video_path: str, step: int, mode: str = "train") -> None:
        if mode not in {"train", "eval"}:
            raise ValueError(mode)
        if not video_path:
            return
        self._mlflow.set_tag(f"{mode}/video_path", str(video_path)[:5000])
        if self._log_media and Path(video_path).is_file():
            self._mlflow.log_artifact(str(video_path), artifact_path=f"videos/step_{step}")
