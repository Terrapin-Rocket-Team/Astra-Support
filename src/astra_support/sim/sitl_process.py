from __future__ import annotations

import threading
import subprocess
import sys
from pathlib import Path


class SitlProcess:
    def __init__(self, project_root: Path, executable: str, *, log_path: Path | None, echo_output: bool):
        self.project_root = project_root
        self.executable = executable
        self.log_path = log_path
        self.echo_output = echo_output
        self.process: subprocess.Popen | None = None
        self._log_handle = None
        self._monitor_thread: threading.Thread | None = None
        self._exit_code: int | None = None

    def start(self) -> None:
        if self.process is not None:
            return
        stdout_target = subprocess.DEVNULL
        if self.echo_output:
            stdout_target = None
        elif self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.log_path.open("w", encoding="utf-8")
            stdout_target = self._log_handle

        self.process = subprocess.Popen(
            [self.executable],
            cwd=self.project_root,
            stdout=stdout_target,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    def ensure_running(self, context: str = "SITL") -> None:
        if self.process is None:
            return
        code = self.process.poll()
        if code is not None:
            self._exit_code = code
            raise RuntimeError(f"{context} process exited early with code {code}")

    def stop(self) -> None:
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=1.0)
            self._monitor_thread = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _monitor(self) -> None:
        if self.process is None:
            return
        self._exit_code = self.process.wait()


def default_sitl_executable(project_root: Path) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return project_root / ".pio" / "build" / "native" / f"program{suffix}"
