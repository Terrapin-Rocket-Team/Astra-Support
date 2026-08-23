from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from astra_support.testing import runner
from astra_support.testing.analyze import STATUS_PASS


class RunnerTests(unittest.TestCase):
    def _context(self, root: Path) -> runner.RunnerContext:
        return runner.RunnerContext(
            project_root=root,
            pio_cmd=["pio"],
            test_dir=root / "test",
            parallel_build_base=root / ".pio" / "build_parallel",
            envs=["native"],
            build_envs=["native"],
            test_env="native",
        )

    def test_configured_jobs_honors_explicit_and_environment_values(self):
        with mock.patch.dict(runner.os.environ, {"ASTRA_SUPPORT_JOBS": "7"}):
            self.assertEqual(runner._configured_jobs(None), 7)
            self.assertEqual(runner._configured_jobs(2), 2)

    def test_clean_does_not_update_or_install_dependencies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = self._context(Path(tmpdir))
            with mock.patch.object(runner, "_run_command", return_value=(0, "", 0.1)) as command:
                result = runner._run_clean_env(ctx, "native")

        self.assertEqual(result.status, STATUS_PASS)
        command.assert_called_once_with(ctx, ["pio", "run", "-e", "native", "-t", "clean"])

    def test_dependency_preparation_is_install_without_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = self._context(Path(tmpdir))
            with mock.patch.object(runner, "_run_command", return_value=(0, "", 0.1)) as command:
                runner._run_dependency_env(ctx, "native", update=False)
                runner._run_dependency_env(ctx, "native", update=True)

        self.assertEqual(command.call_args_list[0].args[1], ["pio", "pkg", "install", "-e", "native"])
        self.assertEqual(command.call_args_list[1].args[1], ["pio", "pkg", "update", "-e", "native"])

    def test_clean_removes_parallel_test_builds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = self._context(Path(tmpdir))
            artifact = ctx.parallel_build_base / "suite" / "program.exe"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("test", encoding="utf-8")

            result = runner._clean_parallel_test_builds(ctx)

            self.assertEqual(result.status, STATUS_PASS)
            self.assertFalse(ctx.parallel_build_base.exists())

    def test_dependency_marker_requires_matching_config_and_env_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "platformio.ini").write_text("[env:native]\nplatform = native\n", encoding="utf-8")
            ctx = self._context(root)
            (root / ".pio" / "libdeps" / "native").mkdir(parents=True)

            runner._mark_dependencies_prepared(ctx)
            self.assertTrue(runner._dependencies_prepared(ctx))

            (root / "platformio.ini").write_text("[env:native]\nplatform = native@new\n", encoding="utf-8")
            self.assertFalse(runner._dependencies_prepared(ctx))

    def test_run_command_replaces_invalid_output_bytes(self):
        completed = subprocess.CompletedProcess(["pio"], 0, stdout="bad \ufffd output")
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = self._context(Path(tmpdir))
            with mock.patch.object(runner.subprocess, "run", return_value=completed) as run:
                code, output, _ = runner._run_command(ctx, ["pio", "--version"])

        self.assertEqual(code, 0)
        self.assertIn("\ufffd", output)
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_run_command_survives_invalid_child_output_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = self._context(Path(tmpdir))
            code, output, _ = runner._run_command(
                ctx,
                [sys.executable, "-c", "import os; os.write(1, bytes([0x81]))"],
            )

        self.assertEqual(code, 0)
        self.assertTrue(output)

    def test_run_tests_rejects_unknown_environment_before_toolchain_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "platformio.ini").write_text("[env:native]\nplatform = native\n", encoding="utf-8")
            with mock.patch.object(runner, "check_toolchain") as toolchain:
                exit_code = runner.run_tests(
                    runner.TestRunnerOptions(project_root=root, envs=["missing"], no_progress=True)
                )

        self.assertEqual(exit_code, 2)
        toolchain.assert_not_called()
