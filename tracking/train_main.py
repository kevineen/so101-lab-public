"""Start ``lerobot-train`` with the local MLflow logger installed.

LeRobot only calls its tracker when wandb is enabled. This module turns that
flag on and swaps the class before ``main()`` runs, so metrics go to MLflow
and the wandb client is not imported.
"""

from __future__ import annotations

import sys
from pathlib import Path


def force_local_tracker_flag(argv: list[str]) -> list[str]:
    """Ensure the train script builds a logger object.

    Existing ``--wandb.enable`` values are rewritten to true. The object that
    gets constructed is :class:`tracking.logger.MLflowLogger`, not WandB.
    """
    rewritten: list[str] = []
    seen = False
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--wandb.enable":
            seen = True
            rewritten.append("--wandb.enable=true")
            if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                index += 1
        elif token.startswith("--wandb.enable="):
            seen = True
            rewritten.append("--wandb.enable=true")
        else:
            rewritten.append(token)
        index += 1
    if not seen:
        rewritten.append("--wandb.enable=true")
    return rewritten


def _read_flag(argv: list[str], name: str) -> str | None:
    prefix = f"--{name}="
    for index, token in enumerate(argv):
        if token.startswith(prefix):
            return token[len(prefix):]
        if token == f"--{name}" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def align_job_name(argv: list[str]) -> list[str]:
    """Enforce the lab naming rule: ``job_name == output_dir`` basename.

    ``job_name`` is the MLflow run name, so comparing runs means comparing
    directories. When it is omitted it is derived from ``output_dir``; when it
    contradicts, the launch stops instead of recording an ambiguous run
    (docs/16 の命名規約).
    """
    output_dir = _read_flag(argv, "output_dir")
    if output_dir is None:
        return argv
    expected = Path(output_dir.rstrip("/")).name
    job_name = _read_flag(argv, "job_name")
    if job_name is None:
        return argv + [f"--job_name={expected}"]
    if job_name != expected:
        raise SystemExit(
            f"命名規約エラー: --job_name={job_name!r} は --output_dir の basename {expected!r} と"
            "一致させてください（docs/16_local_mlflow.md）"
        )
    return argv


def _end_run(status: str) -> None:
    try:
        import mlflow
    except ImportError:
        return
    if mlflow.active_run() is not None:
        mlflow.end_run(status=status)


def main() -> None:
    sys.argv = align_job_name(force_local_tracker_flag(sys.argv))
    import lerobot.scripts.lerobot_train as train_mod

    from tracking.logger import MLflowLogger

    train_mod.WandBLogger = MLflowLogger
    try:
        train_mod.main()
    except SystemExit as exc:
        _end_run("FINISHED" if exc.code in (0, None) else "FAILED")
        raise
    except BaseException:
        _end_run("FAILED")
        raise
    else:
        _end_run("FINISHED")


if __name__ == "__main__":
    main()
