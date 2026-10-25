#!/usr/bin/env python3
"""Log a real-robot evaluation result onto the training run's MLflow record.

After an eval campaign (docs/24) record success rate and failure breakdown on
the same MLflow run as the training, so hyperparameters and real-robot
success can be compared in one place. Metrics go to ``eval/success_rate``,
``eval/trials``, ``eval/successes``, ``eval/avg_success_s`` and
``eval/fail_<type>`` with an incrementing step per campaign; tags
``eval.last_id`` / ``eval.ids`` / ``eval.last_summary`` carry the metadata.

Usage (lerobot venv — it has mlflow):

    cd ~/robot/so101-lab
    ~/robot/lerobot/.venv/bin/python scripts/log_eval_mlflow.py \
      --output_dir ~/robot/lerobot/outputs/train/<run_name> \
      --eval-id E-20261021-01 --trials 10 --successes 6 \
      --avg-success-s 41.2 --failures no_reach=2,no_grasp=1 \
      --note "物体は定位置固定"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracking.logger import ensure_experiment, tracking_uri_for  # noqa: E402
from tracking.settings import load_settings  # noqa: E402

_RUN_ID_NAME = "mlflow_run_id.txt"


def parse_failures(text: str) -> dict[str, int]:
    failures: dict[str, int] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep or not key or not value.isdigit():
            raise SystemExit(f"--failures は no_reach=2,no_grasp=1 の形式で: 入力 {part!r}")
        failures[key] = int(value)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", help="MLflow run ID（省略時は --output_dir/mlflow_run_id.txt を読む）")
    parser.add_argument("--output_dir", type=Path, help="学習の output_dir")
    parser.add_argument("--eval-id", required=True, help="評価セッション ID（例: E-20261021-01）")
    parser.add_argument("--trials", type=int, required=True)
    parser.add_argument("--successes", type=int, required=True)
    parser.add_argument("--avg-success-s", type=float, help="成功試行の平均完了秒数")
    parser.add_argument("--failures", default="", help="失敗内訳。no_reach=2,no_grasp=1 の形式")
    parser.add_argument("--note", default="", help="1 行メモ（物体位置など）")
    args = parser.parse_args()

    if not args.run_id and not args.output_dir:
        parser.error("--run-id か --output_dir のどちらかは必須です")
    if not 0 <= args.successes <= args.trials:
        raise SystemExit("0 <= successes <= trials を満たす必要があります")
    failures = parse_failures(args.failures)
    if failures and sum(failures.values()) > args.trials - args.successes:
        raise SystemExit(
            f"失敗内訳の合計 {sum(failures.values())} が失敗数 {args.trials - args.successes} を超えています"
        )

    import mlflow
    from mlflow.tracking import MlflowClient

    if args.run_id:
        run_id = args.run_id
    else:
        path = args.output_dir / _RUN_ID_NAME
        if not path.is_file():
            raise SystemExit(
                f"{path} がありません。train_mlflow.sh 経由で学習するか、"
                "backfill_mlflow.py で後付け登録してください"
            )
        run_id = path.read_text(encoding="utf-8").strip()
        if not run_id:
            raise SystemExit(f"{path} が空です")

    settings = load_settings()
    uri, via_http = tracking_uri_for(settings)
    mlflow.set_tracking_uri(uri)
    ensure_experiment(settings, via_http)
    client = MlflowClient(tracking_uri=uri)
    run = client.get_run(run_id)
    if run.info.lifecycle_stage == "deleted":
        raise SystemExit(f"run {run_id} は削除されています")

    step = len(client.get_metric_history(run_id, "eval/success_rate"))
    metrics: dict[str, float] = {
        "eval/success_rate": args.successes / args.trials,
        "eval/trials": float(args.trials),
        "eval/successes": float(args.successes),
    }
    for key, count in failures.items():
        metrics[f"eval/fail_{key}"] = float(count)
    if args.avg_success_s is not None:
        metrics["eval/avg_success_s"] = args.avg_success_s
    for key, value in metrics.items():
        client.log_metric(run_id, key, value, step=step)

    summary = {
        "eval_id": args.eval_id,
        "date": dt.date.today().isoformat(),
        "trials": args.trials,
        "successes": args.successes,
        "failures": failures,
        "note": args.note,
    }
    client.set_tag(run_id, "eval.last_id", args.eval_id)
    client.set_tag(run_id, "eval.last_summary", json.dumps(summary, ensure_ascii=False))
    previous_ids = run.data.tags.get("eval.ids", "")
    ids = [item for item in previous_ids.split(",") if item]
    if args.eval_id not in ids:
        ids.append(args.eval_id)
    client.set_tag(run_id, "eval.ids", ",".join(ids))

    where = "tracking server" if via_http else "sqlite file"
    print(f"run {run_id}（{run.data.tags.get('job_name', '?')}）へ eval を記録しました -> {uri} ({where})")
    for key in sorted(metrics):
        print(f"  {key} = {metrics[key]:g} (step {step})")


if __name__ == "__main__":
    main()
