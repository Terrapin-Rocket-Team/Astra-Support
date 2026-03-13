from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from astra_support.commands.sync import run


class SyncCommandTests(unittest.TestCase):
    def test_sync_creates_config_and_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "platformio.ini").write_text("", encoding="utf-8")
            args = SimpleNamespace(
                project=str(root),
                config=None,
                write_workflow=True,
                overwrite=False,
                skip_platformio_env=False,
                env=["native"],
                list_envs=False,
                support_install="git+https://example.invalid/astra-support.git@main",
            )
            exit_code = run(args)
            self.assertEqual(exit_code, 0)
            self.assertTrue((root / ".astra-support.yml").exists())
            self.assertTrue((root / ".github" / "workflows" / "run_astra_support.yml").exists())

    def test_sync_appends_requested_platformio_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "platformio.ini").write_text("[platformio]\ndefault_envs = native", encoding="utf-8")
            args = SimpleNamespace(
                project=str(root),
                config=None,
                write_workflow=False,
                overwrite=False,
                skip_platformio_env=False,
                env=["teensy41"],
                list_envs=False,
                support_install="git+https://example.invalid/astra-support.git@main",
            )

            exit_code = run(args)

            self.assertEqual(exit_code, 0)
            platformio_text = (root / "platformio.ini").read_text(encoding="utf-8")
            self.assertIn("[platformio]\ndefault_envs = native", platformio_text)
            self.assertIn("[env:teensy41]", platformio_text)
