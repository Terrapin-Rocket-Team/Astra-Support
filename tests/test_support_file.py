from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astra_support.config.support_file import load_support_config, write_default_config


class SupportFileTests(unittest.TestCase):
    def test_write_and_load_default_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / ".astra-support.yml"
            self.assertTrue(write_default_config(config_path, overwrite=False))
            config = load_support_config(root)
            self.assertEqual(config.project, ".")
            self.assertIn("--no-progress", config.test_args)
            self.assertTrue(config.write_workflow)
