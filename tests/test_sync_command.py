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
