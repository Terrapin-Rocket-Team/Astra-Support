from __future__ import annotations

import unittest
from unittest import mock

from astra_support import prereqs


class PrereqTests(unittest.TestCase):
    def test_resolve_cpp_compiler_requires_gpp(self):
        with (
            mock.patch.object(prereqs.sys, "platform", "linux"),
            mock.patch.object(prereqs.shutil, "which", side_effect=lambda name: {"clang++": "C:/LLVM/bin/clang++.exe"}.get(name)),
        ):
            self.assertIsNone(prereqs.resolve_cpp_compiler())

    def test_windows_install_recipe_targets_msys2_gpp(self):
        with (
            mock.patch.object(prereqs.platform, "system", return_value="Windows"),
            mock.patch.object(prereqs.shutil, "which", side_effect=lambda name: "winget" if name == "winget" else None),
        ):
            commands, label = prereqs._cpp_install_commands()

        self.assertEqual(label, "MSYS2 UCRT64 g++ via winget")
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertEqual(command[:4], ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"])
        self.assertIn("MSYS2.MSYS2", command[-1])
        self.assertIn("mingw-w64-ucrt-x86_64-gcc", command[-1])
