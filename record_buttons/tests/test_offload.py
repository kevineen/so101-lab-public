"""Dataset offload builds an rsync command and deletes the Pi tree only after success."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from record_buttons.offload import (
    OffloadSession,
    OffloadSettings,
    load_settings,
    rsync_argv,
    safe_to_delete,
)


class SettingsTests(unittest.TestCase):
    def test_empty_ssh_stays_on_pi(self) -> None:
        with mock.patch.dict(os.environ, {"SO101_DATASET_SSH": ""}, clear=False):
            self.assertIsNone(load_settings())

    def test_requires_absolute_remote_dir(self) -> None:
        env = {"SO101_DATASET_SSH": "root@192.168.77.20", "SO101_DATASET_DIR": "datasets"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertIsNone(load_settings())

    def test_reads_delete_flag(self) -> None:
        env = {
            "SO101_DATASET_SSH": "root@192.168.77.20",
            "SO101_DATASET_DIR": "/home/tester/.cache/huggingface/lerobot",
            "SO101_DATASET_DELETE_LOCAL": "0",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            settings = load_settings()
        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertFalse(settings.delete_local)


class CommandTests(unittest.TestCase):
    def test_rsync_targets_repo_id(self) -> None:
        argv = rsync_argv(
            Path("/tmp/local/so101_smoke"),
            "root@192.168.77.20",
            "/home/tester/.cache/huggingface/lerobot/local/so101_smoke",
        )
        self.assertEqual(argv[0], "rsync")
        self.assertEqual(argv[-2], "/tmp/local/so101_smoke/")
        self.assertEqual(
            argv[-1],
            "root@192.168.77.20:/home/tester/.cache/huggingface/lerobot/local/so101_smoke/",
        )
        self.assertIn("BatchMode=yes", argv[4])


class SessionTests(unittest.TestCase):
    def _dataset(self) -> Path:
        root = Path(tempfile.mkdtemp()) / "lerobot" / "local" / "so101_smoke"
        (root / "meta").mkdir(parents=True)
        (root / "meta" / "info.json").write_text("{}", encoding="utf-8")
        return root

    def test_failed_sync_keeps_local_files(self) -> None:
        root = self._dataset()
        settings = OffloadSettings("root@host", "/remote/lerobot", delete_local=True)
        session = OffloadSession(settings, runner=lambda _argv: 1)
        session.note_saved(root, "local/so101_smoke")
        self.assertFalse(session.finish(root, "local/so101_smoke"))
        self.assertTrue((root / "meta" / "info.json").is_file())

    def test_success_removes_local_tree(self) -> None:
        root = self._dataset()
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> int:
            calls.append(argv)
            return 0

        settings = OffloadSettings("root@host", "/remote/lerobot", delete_local=True)
        session = OffloadSession(settings, runner=runner)
        session.note_saved(root, "local/so101_smoke")
        self.assertTrue(session.finish(root, "local/so101_smoke"))
        self.assertFalse(root.exists())
        self.assertEqual(calls[0][0], "ssh")
        self.assertEqual(calls[1][0], "rsync")

    def test_sync_before_finish_and_second_finish_does_not_rsync(self) -> None:
        root = self._dataset()
        calls: list[str] = []

        def runner(argv: list[str]) -> int:
            calls.append(argv[0])
            return 0

        settings = OffloadSettings("root@host", "/remote/lerobot", delete_local=True)
        session = OffloadSession(settings, runner=runner)
        session.note_saved(root, "local/so101_smoke")
        self.assertTrue(session.sync_saved())
        self.assertTrue(root.exists())
        self.assertFalse(session.needs_sync)
        self.assertTrue(session.finish(root, "local/so101_smoke"))
        self.assertFalse(root.exists())
        self.assertTrue(session.finish(root, "local/so101_smoke"))
        self.assertEqual(calls.count("rsync"), 2)

    def test_nothing_kept_skips_sync(self) -> None:
        root = self._dataset()
        calls: list[str] = []
        settings = OffloadSettings("root@host", "/remote/lerobot", delete_local=True)
        session = OffloadSession(settings, runner=lambda argv: calls.append(argv[0]) or 0)
        self.assertTrue(session.finish(root, "local/so101_smoke"))
        self.assertEqual(calls, [])
        self.assertTrue(root.exists())

    def test_home_is_not_deletable(self) -> None:
        self.assertFalse(safe_to_delete(Path.home()))


if __name__ == "__main__":
    unittest.main()
