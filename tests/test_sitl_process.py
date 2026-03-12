from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from astra_support.sim.sitl_process import SitlProcess


class SitlProcessTests(unittest.TestCase):
    def test_ensure_running_raises_when_process_exits_early(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            process = SitlProcess(
                project_root=Path(tmpdir),
                executable=sys.executable,
                log_path=None,
                echo_output=False,
            )
            process.executable = f'{sys.executable} -c "import sys; sys.exit(3)"'
            process.start = _start_via_shell.__get__(process, SitlProcess)
            process.start()
            process.process.wait(timeout=5.0)
            with self.assertRaises(RuntimeError):
                process.ensure_running("SITL")
            process.stop()


def _start_via_shell(self: SitlProcess) -> None:
    import subprocess

    self.process = subprocess.Popen(
        self.executable,
        cwd=self.project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True,
    )
