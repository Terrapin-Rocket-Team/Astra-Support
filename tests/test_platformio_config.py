from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astra_support.platformio.config import env_names, env_platform_map, select_build_envs, select_test_env


class PlatformioConfigTests(unittest.TestCase):
    def test_env_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "platformio.ini"
            path.write_text(
                "[env:native]\nplatform = native\n\n[env:teensy41]\nplatform = teensy\n",
                encoding="utf-8",
            )
            self.assertEqual(env_names(path), ["native", "teensy41"])
            self.assertEqual(env_platform_map(path)["native"], "native")
            self.assertEqual(select_test_env(["teensy41", "native"]), "native")
            self.assertIn("native", select_build_envs(["native", "teensy41"]))
