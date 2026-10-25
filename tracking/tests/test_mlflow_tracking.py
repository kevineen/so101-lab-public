"""Tests for local MLflow settings, the train flag rewrite, and metric logging."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tracking.settings import load_settings
from tracking.train_main import align_job_name, force_local_tracker_flag


class JobNameAlignTests(unittest.TestCase):
    def test_derives_job_name_from_output_dir(self) -> None:
        argv = ["prog", "--output_dir=outputs/train/act_cobra_frontwrist-bs32_20261020"]
        self.assertEqual(
            align_job_name(argv),
            argv + ["--job_name=act_cobra_frontwrist-bs32_20261020"],
        )

    def test_accepts_matching_space_form(self) -> None:
        argv = ["prog", "--output_dir", "outputs/train/run_a", "--job_name", "run_a"]
        self.assertEqual(align_job_name(argv), argv)

    def test_rejects_mismatch(self) -> None:
        with self.assertRaises(SystemExit):
            align_job_name(["prog", "--output_dir=outputs/train/run_a", "--job_name=other"])

    def test_ignores_missing_output_dir(self) -> None:
        argv = ["prog", "--steps=10"]
        self.assertEqual(align_job_name(argv), argv)


class FlagRewriteTests(unittest.TestCase):
    def test_appends_enable_when_absent(self) -> None:
        self.assertEqual(
            force_local_tracker_flag(["prog", "--policy.type=act"]),
            ["prog", "--policy.type=act", "--wandb.enable=true"],
        )

    def test_rewrites_false_forms(self) -> None:
        self.assertEqual(
            force_local_tracker_flag(["prog", "--wandb.enable=false", "--steps=3"]),
            ["prog", "--wandb.enable=true", "--steps=3"],
        )
        self.assertEqual(
            force_local_tracker_flag(["prog", "--wandb.enable", "false"]),
            ["prog", "--wandb.enable=true"],
        )


class SettingsTests(unittest.TestCase):
    def test_env_overrides_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mlflow.yaml"
            path.write_text("host: 127.0.0.1\nport: 5001\nstore_dir: store\nexperiment: lab\n", encoding="utf-8")
            previous = os.environ.get("SO101_MLFLOW_PORT")
            os.environ["SO101_MLFLOW_PORT"] = "5002"
            try:
                settings = load_settings(path)
            finally:
                if previous is None:
                    os.environ.pop("SO101_MLFLOW_PORT", None)
                else:
                    os.environ["SO101_MLFLOW_PORT"] = previous
            self.assertEqual(settings.port, 5002)
            self.assertEqual(settings.experiment, "lab")
            self.assertTrue(str(settings.sqlite_uri).endswith("/store/mlflow.db"))


class SelectParamsTests(unittest.TestCase):
    def test_logs_policy_axes_and_obs_cameras(self) -> None:
        from tracking.logger import select_params

        payload = {
            "seed": 1000,
            "steps": 8040,
            "batch_size": 32,
            "policy": {
                "type": "act",
                "chunk_size": 100,
                "n_action_steps": 100,
                "kl_weight": 10.0,
                "input_features": {
                    "observation.state": {"type": "STATE", "shape": [6]},
                    "observation.images.front": {"type": "VISUAL"},
                    "observation.images.wrist": {"type": "VISUAL"},
                },
            },
            "dataset": {"repo_id": "local/demo", "root": "/tmp/data"},
        }
        params = select_params(payload)
        self.assertEqual(params["obs_cameras"], "front+wrist")
        self.assertEqual(params["policy.chunk_size"], "100")
        self.assertEqual(params["policy.n_action_steps"], "100")
        self.assertEqual(params["policy.kl_weight"], "10.0")
        self.assertNotIn("policy.horizon", params)

    def test_diffusion_axes_and_absent_cameras(self) -> None:
        from tracking.logger import select_params

        payload = {
            "policy": {"type": "diffusion", "horizon": 64, "n_action_steps": 32},
            "dataset": {"repo_id": "local/demo"},
        }
        params = select_params(payload)
        self.assertEqual(params["policy.horizon"], "64")
        self.assertNotIn("obs_cameras", params)

    def test_obs_cameras_is_sorted(self) -> None:
        from tracking.logger import select_params

        payload = {
            "policy": {
                "type": "act",
                "input_features": {
                    "observation.images.wrist": {"type": "VISUAL"},
                    "observation.images.front": {"type": "VISUAL"},
                },
            }
        }
        self.assertEqual(select_params(payload)["obs_cameras"], "front+wrist")


class _Policy:
    type = "act"


class _Dataset:
    repo_id = "local/demo"
    root = "/tmp/data"


class _Wandb:
    notes = "local"
    project = "lerobot"


class _Cfg:
    def __init__(self, out: Path) -> None:
        self.job_name = "act_job"
        self.output_dir = out
        self.resume = False
        self.env = None
        self.seed = 1
        self.wandb = _Wandb()
        self.policy = _Policy()
        self.dataset = _Dataset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": 1,
            "steps": 20,
            "batch_size": 8,
            "job_name": "act_job",
            "output_dir": str(self.output_dir),
            "policy": {"type": "act", "device": "cpu", "push_to_hub": False},
            "dataset": {"repo_id": "local/demo", "root": "/tmp/data", "stats": {"mean": [1, 2, 3]}},
            "optimizer": {"lr": 1e-4},
        }


class LoggerTests(unittest.TestCase):
    def test_logs_metrics_and_skips_weights(self) -> None:
        import mlflow
        from mlflow.tracking import MlflowClient

        from tracking.logger import MLflowLogger, select_params

        params = select_params(_Cfg(Path(".")).to_dict())
        self.assertEqual(params["policy.type"], "act")
        self.assertNotIn("dataset.stats", params)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            uri = "sqlite:///" + (root / "mlflow.db").as_posix()
            previous_uri = os.environ.get("MLFLOW_TRACKING_URI")
            previous_exp = os.environ.get("SO101_MLFLOW_EXPERIMENT")
            previous_store = os.environ.get("SO101_MLFLOW_STORE")
            os.environ["MLFLOW_TRACKING_URI"] = uri
            os.environ["SO101_MLFLOW_EXPERIMENT"] = "so101-test"
            os.environ["SO101_MLFLOW_STORE"] = str(root / "store")
            try:
                tracker = MLflowLogger(_Cfg(out))
                tracker.log_dict({"loss": 1.5, "note": "skip-me", "nested": {"a": 1}}, step=2)
                weight = root / "model.safetensors"
                weight.write_bytes(b"not-a-real-weight")
                ckpt = out / "checkpoints" / "000002" / "pretrained_model"
                ckpt.mkdir(parents=True)
                (ckpt / "config.json").write_text('{"type": "act"}', encoding="utf-8")
                (ckpt / "model.safetensors").write_bytes(b"weights")
                tracker.log_policy(ckpt.parent)
                tracker.log_video(str(root / "missing.mp4"), step=2, mode="eval")
                mlflow.end_run()
                client = MlflowClient(tracking_uri=uri)
                run = client.get_run(tracker.run_id)
                metrics = client.get_metric_history(tracker.run_id, "train/loss")
            finally:
                if previous_uri is None:
                    os.environ.pop("MLFLOW_TRACKING_URI", None)
                else:
                    os.environ["MLFLOW_TRACKING_URI"] = previous_uri
                if previous_exp is None:
                    os.environ.pop("SO101_MLFLOW_EXPERIMENT", None)
                else:
                    os.environ["SO101_MLFLOW_EXPERIMENT"] = previous_exp
                if previous_store is None:
                    os.environ.pop("SO101_MLFLOW_STORE", None)
                else:
                    os.environ["SO101_MLFLOW_STORE"] = previous_store
            self.assertEqual(metrics[-1].value, 1.5)
            self.assertEqual(metrics[-1].step, 2)
            self.assertNotIn("train/note", run.data.metrics)
            self.assertEqual(run.data.tags["last_checkpoint"], str(ckpt.parent))
            artifacts = [item.path for item in client.list_artifacts(tracker.run_id)]
            self.assertIn("mlflow_train_config.json", artifacts)
            self.assertTrue(all("safetensors" not in name for name in artifacts))


if __name__ == "__main__":
    unittest.main()
