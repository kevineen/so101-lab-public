#!/usr/bin/env python3
"""Register a finished training run in the local MLflow store (backfill).

For runs launched with plain ``lerobot-train`` before the lab rule (docs/16):
reads ``checkpoints/last/pretrained_model/train_config.json``, logs the same
params and config artifact that ``train_mlflow.sh`` would have logged, and
links the run back via ``mlflow_run_id.txt``. Loss curves cannot be recovered
from the config, so a backfilled run has params/artifacts but no scalars.

Usage (lerobot venv — it has mlflow):

    cd ~/robot/so101-lab
    ~/robot/lerobot/.venv/bin/python scripts/backfill_mlflow.py \
      ~/robot/lerobot/outputs/train/<run_name> [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracking.logger import ensure_experiment, select_params, tracking_uri_for  # noqa: E402
from tracking.settings import load_settings  # noqa: E402

_RUN_ID_NAME = "mlflow_run_id.txt"


def find_train_config(output_dir: Path) -> Path:
    direct = output_dir / "checkpoints" / "last" / "pretrained_model" / "train_config.json"
    if direct.is_file():
        return direct
    candidates = sorted(
        output_dir.glob("checkpoints/*/pretrained_model/train_config.json"),
        key=lambda path: path.parents[1].name,
    )
    if candidates:
        return candidates[-1]
    raise SystemExit(f"train_config.json が見つかりません: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("output_dir", type=Path, help="学習の output_dir（checkpoints/ を含む）")
    parser.add_argument("--force", action="store_true", help="mlflow_run_id.txt が既にあっても新しい run を作る")
    args = parser.parse_args()

    import mlflow
    from mlflow.tracking import MlflowClient

    output_dir = args.output_dir.resolve()
    config_path = find_train_config(output_dir)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    job_name = payload.get("job_name") or output_dir.name
    # job_name defaults to the policy type when the launch omitted it, which
    # collides across runs. The run name follows the directory instead; the
    # job_name param keeps the recorded value either way.
    run_name = output_dir.name
    if job_name != run_name:
        print(f"注意: config の job_name が output_dir 名と違います（job_name={job_name!r}）。run 名は {run_name!r} を使います")

    settings = load_settings()
    uri, via_http = tracking_uri_for(settings)
    mlflow.set_tracking_uri(uri)
    ensure_experiment(settings, via_http)
    client = MlflowClient(tracking_uri=uri)

    run_id = None
    run_id_file = output_dir / _RUN_ID_NAME
    if run_id_file.is_file() and not args.force:
        run_id = run_id_file.read_text(encoding="utf-8").strip() or None
    if run_id:
        try:
            run = client.get_run(run_id)
            if run.info.lifecycle_stage == "deleted":
                run_id = None
        except Exception:
            run_id = None

    created = run_id is None
    if created:
        with mlflow.start_run(run_name=run_name) as active:
            run_id = active.info.run_id

    with mlflow.start_run(run_id=run_id):
        run = client.get_run(run_id)
        have = run.data.params
        wanted = select_params(payload)
        conflicts = {k: (have[k], v) for k, v in wanted.items() if k in have and have[k] != v}
        missing = {k: v for k, v in wanted.items() if k not in have}
        if missing:
            mlflow.log_params(missing)
        if not any(item.path == "mlflow_train_config.json" for item in client.list_artifacts(run_id)):
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "mlflow_train_config.json"
                dest.write_text(
                    json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8"
                )
                mlflow.log_artifact(str(dest))
        mlflow.set_tag("job_name", job_name)
        mlflow.set_tag("output_dir", str(output_dir))
        if created:
            mlflow.set_tag("backfill", "1")

    run_id_file.write_text(run_id + "\n", encoding="utf-8")
    where = "tracking server" if via_http else "sqlite file"
    print(f"MLflow run {run_id} ({'created' if created else 'reused'}) -> {uri} ({where})")
    if conflicts:
        print("既存 run と値が違うため上書きしなかった params:")
        for key, (old, new) in sorted(conflicts.items()):
            print(f"  {key}: run={old} != config={new}")


if __name__ == "__main__":
    main()
