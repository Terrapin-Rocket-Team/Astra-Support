from __future__ import annotations

import unittest

from scripts.bump_version import bump_project_version


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
