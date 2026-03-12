from __future__ import annotations

import sys
import threading
import time

from ..console import Ansi, paint
from .analyze import STATUS_COMPILE_ERR, STATUS_PASS, STATUS_SYSTEM_ERR, STATUS_TEST_FAIL


def supports_live_progress() -> bool:
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        return True
    return True


class ProgressReporter:
    def __init__(self, enabled: bool):
        self.enabled = enabled and supports_live_progress()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._visible = False
        self._last_line = ""
        self._stage_name = ""
        self._done = 0
        self._total = 0
        self._stage_start = 0.0

    def start(self, stage_name: str, total: int) -> None:
        self._stage_name = stage_name
        self._done = 0
        self._total = max(1, total)
        self._stage_start = time.time()
        if not self.enabled:
            return
        self._stop.clear()
        self._render()
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def advance(self) -> None:
        with self._lock:
            self._done = min(self._total, self._done + 1)
            if self.enabled:
                self._render_locked()

    def write(self, message: str) -> None:
        if not self.enabled:
            print(message)
            return
        with self._lock:
            self._clear_locked()
            print(message)
            self._render_locked()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._clear_locked()
        self._thread = None

    def _refresh_loop(self) -> None:
        while not self._stop.wait(0.25):
            with self._lock:
                self._render_locked()

    def _render(self) -> None:
        with self._lock:
            self._render_locked()

    def _render_locked(self) -> None:
        elapsed = int(time.time() - self._stage_start)
        minutes, seconds = divmod(elapsed, 60)
        width = 24
        filled = int((self._done / max(1, self._total)) * width)
        bar = "=" * filled + "-" * (width - filled)
        line = (
            f"{Ansi.DIM}{self._stage_name:<8}{Ansi.RESET} "
            f"[{bar}] {self._done}/{self._total} "
            f"{Ansi.DIM}{minutes:02d}:{seconds:02d}{Ansi.RESET}"
        )
        pad = " " * max(0, len(self._last_line) - len(line))
        sys.stdout.write("\r" + line + pad)
        sys.stdout.flush()
        self._last_line = line
        self._visible = True

    def _clear_locked(self) -> None:
        if not self._visible:
            return
        sys.stdout.write("\r" + (" " * len(self._last_line)) + "\r")
        sys.stdout.flush()
        self._visible = False
        self._last_line = ""


def print_stage(name: str) -> None:
    print(f"\n{paint(f'[{name}]', Ansi.BOLD)}")


def print_retry(item: str, attempt: int) -> None:
    print(f"{paint('retry', Ansi.YELLOW)} {attempt}: {item}")


def print_result(name: str, status: str, duration: float, *, extra: str = "", log: str = "") -> None:
    icon, color = _status_style(status)
    line = f"{paint(icon, color)} {name}: {paint(status.lower(), color)} {paint(f'({duration:.1f}s)', Ansi.DIM)}"
    if extra:
        line = f"{line} {extra}"
    print(line)
    if log:
        print(paint(log, Ansi.DIM))


def print_summary(clean_results, install_results, build_results, test_results) -> None:
    print(f"\n{paint('[summary]', Ansi.BOLD)}")
    _print_group("clean", clean_results)
    _print_group("platforms", install_results)
    _print_group("builds", build_results)
    _print_group("tests", list(test_results))


def _print_group(name: str, results) -> None:
    if not results:
        print(f"{name}: {paint('skipped', Ansi.DIM)}")
        return
    counts = {
        STATUS_PASS: 0,
        STATUS_TEST_FAIL: 0,
        STATUS_COMPILE_ERR: 0,
        STATUS_SYSTEM_ERR: 0,
    }
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(
        f"{name}: "
        f"{paint(f'pass={counts[STATUS_PASS]}', Ansi.GREEN)} "
        f"{paint(f'fail={counts[STATUS_TEST_FAIL]}', Ansi.RED)} "
        f"{paint(f'compile={counts[STATUS_COMPILE_ERR]}', Ansi.YELLOW)} "
        f"{paint(f'system={counts[STATUS_SYSTEM_ERR]}', Ansi.MAGENTA)}"
    )


def _status_style(status: str) -> tuple[str, str]:
    if status == STATUS_PASS:
        return "✔", Ansi.GREEN
    if status == STATUS_TEST_FAIL:
        return "✘", Ansi.RED
    if status == STATUS_COMPILE_ERR:
        return "✘", Ansi.YELLOW
    return "✘", Ansi.MAGENTA
