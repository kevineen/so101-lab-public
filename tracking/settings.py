"""Load local MLflow settings from configs/mlflow.yaml and the environment."""

from __future__ import annotations

import argparse
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "mlflow.yaml"

_ENV_KEYS = {
    "host": "SO101_MLFLOW_HOST",
    "port": "SO101_MLFLOW_PORT",
    "store_dir": "SO101_MLFLOW_STORE",
    "experiment": "SO101_MLFLOW_EXPERIMENT",
}


@dataclass(frozen=True)
class MlflowSettings:
    """Resolved local tracking locations.

    ``store_dir`` is the gitignored tree. The sqlite file and artifact
    directory live inside it so a single ignore rule covers the heavy data.
    """

    host: str
    port: int
    store_dir: Path
    experiment: str

    @property
    def db_path(self) -> Path:
        return self.store_dir / "mlflow.db"

    @property
    def artifact_dir(self) -> Path:
        return self.store_dir / "artifacts"

    @property
    def sqlite_uri(self) -> str:
        # Absolute path: sqlite:/// + /home/... => four slashes.
        return "sqlite:///" + self.db_path.resolve().as_posix()


def _parse_yaml_scalars(text: str) -> dict[str, str]:
    """Read a flat ``key: value`` file. Comments and blank lines are ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_settings(config_path: Path | None = None) -> MlflowSettings:
    """Merge yaml defaults with environment overrides.

    Environment variables win so a GPU host can point at another disk
    without editing the tracked config.
    """
    path = config_path if config_path is not None else CONFIG_PATH
    file_values: dict[str, str] = {}
    if path.is_file():
        file_values = _parse_yaml_scalars(path.read_text(encoding="utf-8"))

    def pick(key: str, default: str) -> str:
        env_name = _ENV_KEYS[key]
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value
        if key in file_values and file_values[key] != "":
            return file_values[key]
        return default

    store_text = pick("store_dir", "mlflow_store")
    store = Path(store_text)
    if not store.is_absolute():
        store = REPO_ROOT / store
    port_text = pick("port", "5000")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"MLflow port must be an integer, got {port_text!r}") from exc
    if not (0 < port < 65536):
        raise ValueError(f"MLflow port out of range: {port}")
    return MlflowSettings(
        host=pick("host", "0.0.0.0"),
        port=port,
        store_dir=store,
        experiment=pick("experiment", "so101"),
    )


def shell_exports(settings: MlflowSettings) -> str:
    """Print assignments that ``eval`` can load in the start script."""
    pairs = {
        "HOST": settings.host,
        "PORT": str(settings.port),
        "STORE_DIR": str(settings.store_dir),
        "ARTIFACT_DIR": str(settings.artifact_dir),
        "DB_URI": settings.sqlite_uri,
        "EXPERIMENT": settings.experiment,
    }
    return "\n".join(f"{key}={shlex.quote(value)}" for key, value in pairs.items())


def main() -> None:
    parser = argparse.ArgumentParser(description="Print local MLflow settings")
    parser.add_argument("--shell", action="store_true", help="emit shell assignments")
    args = parser.parse_args()
    settings = load_settings()
    if args.shell:
        print(shell_exports(settings))
        return
    print(f"ui=http://127.0.0.1:{settings.port}")
    print(f"store={settings.store_dir}")
    print(f"sqlite={settings.sqlite_uri}")
    print(f"experiment={settings.experiment}")


if __name__ == "__main__":
    main()
