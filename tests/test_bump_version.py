from __future__ import annotations

import unittest
from unittest import mock

from scripts.bump_version import bump_project_version, main


class BumpVersionTests(unittest.TestCase):
    def test_bump_project_version_updates_patch(self):
        original = (
            "[build-system]\n"
            'requires = ["setuptools>=68"]\n'
            "\n"
            "[project]\n"
            'name = "astra-support"\n'
            'version = "0.2.0"\n'
        )

        updated, new_version = bump_project_version(original)

        self.assertEqual(new_version, "0.2.1")
        self.assertIn('version = "0.2.1"', updated)

    def test_bump_project_version_only_changes_project_section(self):
        original = (
            "[tool.example]\n"
            'version = "9.9.9"\n'
            "\n"
            "[project]\n"
            'name = "astra-support"\n'
            'version = "1.4.7"\n'
        )

        updated, new_version = bump_project_version(original, part="minor")

        self.assertEqual(new_version, "1.5.0")
        self.assertIn('[tool.example]\nversion = "9.9.9"', updated)
        self.assertIn('version = "1.5.0"', updated)

    def test_main_detach_spawns_background_bump(self):
        with mock.patch("scripts.bump_version.spawn_detached_bump") as patched_spawn:
            exit_code = main(
                [
                    "--path",
                    "pyproject.toml",
                    "--part",
                    "patch",
                    "--delay-seconds",
                    "30",
                    "--detach",
                ]
            )

        self.assertEqual(exit_code, 0)
        patched_spawn.assert_called_once_with("pyproject.toml", "patch", 30.0)
