import argparse
import os
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- CONFIGURATION ---
MAX_WORKERS = max(1, (os.cpu_count() or 1) - 2)
MAX_RETRIES = 3
PROJECT_ROOT = os.getcwd()
TEST_DIR = os.path.join(PROJECT_ROOT, "test")
PARALLEL_BUILD_BASE = os.path.join(PROJECT_ROOT, ".pio", "build_parallel")

# ANSI Colors
BS = "\033[1m"       # Bold
DIM = "\033[2m"      # Dim
R = "\033[91m"       # Red   – test assertion failures
G = "\033[92m"       # Green – success
Y = "\033[93m"       # Yellow – warnings / retries
M = "\033[95m"       # Magenta – system/crash errors
C = "\033[96m"       # Cyan – informational / secondary
NC = "\033[0m"       # Reset

# Status Categories
STATUS_PASS = "PASS"
STATUS_TEST_FAIL = "TEST_FAIL"
STATUS_COMPILE_ERR = "COMPILE_ERR"
STATUS_SYSTEM_ERR = "SYSTEM_ERR"

W = 50  # summary separator width


def configure_console_output() -> None:
    # Ensure unicode status symbols do not crash on Windows cp1252 consoles.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def supports_live_progress() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


@dataclass
class TestResult:
    name: str
    status: str
    code: int
    log: str
    duration: float
    test_count: Optional[int] = None
    passed_count: Optional[int] = None
    failed_count: Optional[int] = None


@dataclass
class BuildResult:
    name: str
    status: str
    code: int
    log: str
    duration: float


@dataclass
class PlatformInstallResult:
    name: str
    status: str
    code: int
    log: str
    duration: float


@dataclass
class CleanResult:
    name: str
    status: str
    code: int
    log: str
    duration: float


class ProgressReporter:
    def __init__(self, enabled: bool, total_phases: int, global_start_time: float):
        self.enabled = enabled
        self.total_phases = max(1, total_phases)
        self.global_start_time = global_start_time
        self.completed_phases = 0
        self.phase_active = False
        self.stage_name = "idle"
        self.stage_done = 0
        self.stage_total = 1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._visible = False
        self._last_line_len = 0

    def start(self) -> None:
        if not self.enabled:
            return
        self.render()
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._clear_unlocked()

    def _refresh_loop(self) -> None:
        while not self._stop.wait(0.5):
            self.render()

    def set_stage(self, name: str, total: int) -> None:
        with self._lock:
            self.stage_name = name
            self.stage_total = max(1, total)
            self.stage_done = 0
            self.phase_active = True
            if self.enabled:
                self._render_unlocked()

    def advance_stage(self, inc: int = 1) -> None:
        with self._lock:
            self.stage_done = min(self.stage_total, self.stage_done + inc)
            if self.enabled:
                self._render_unlocked()

    def complete_stage(self) -> None:
        with self._lock:
            self.stage_done = self.stage_total
            self.phase_active = False
            self.completed_phases = min(self.total_phases, self.completed_phases + 1)
            if self.enabled:
                self._render_unlocked()

    def write(self, message: str) -> None:
        if not self.enabled:
            print(message)
            return
        with self._lock:
            self._clear_unlocked()
            print(message)
            self._render_unlocked()

    def render(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._render_unlocked()

    def _clear_unlocked(self) -> None:
        if not self._visible:
            return
        sys.stdout.write("\r")
        sys.stdout.write(" " * self._last_line_len)
        sys.stdout.write("\r")
        sys.stdout.flush()
        self._visible = False
        self._last_line_len = 0

    def _elapsed_str(self) -> str:
        elapsed = max(0, int(time.time() - self.global_start_time))
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _bar(done: float, total: float, width: int = 28) -> str:
        total = max(1.0, float(total))
        done = min(total, max(0.0, float(done)))
        ratio = done / total
        filled = int(width * ratio)
        bar = "=" * filled + "-" * (width - filled)
        return f"[{bar}] {int(ratio * 100):3d}% ({int(done)}/{int(total)})"

    def _render_unlocked(self) -> None:
        active_task = self.completed_phases + (1 if self.phase_active else 0)
        active_task = min(self.total_phases, active_task)
        line = (
            f"  {self.stage_name:<8} "
            f"{self._bar(self.stage_done, self.stage_total)} "
            f"| task {active_task}/{self.total_phases} "
            f"| {self._elapsed_str()}"
        )
        # Track the full written width so _clear_unlocked erases everything
        full_len = max(len(line), self._last_line_len)
        padding = " " * max(0, self._last_line_len - len(line))
        sys.stdout.write("\r")
        sys.stdout.write(line)
        if padding:
            sys.stdout.write(padding)
        sys.stdout.flush()
        self._visible = True
        self._last_line_len = full_len


def _retry_delay_seconds(attempt_number: int) -> float:
    return min(0.2 * max(1, attempt_number), 1.0)


def analyze_output(log_text: str, return_code: int) -> Tuple[str, str]:
    lines = log_text.split("\n")
    cleaned_lines = []

    found_assert_fail = False
    found_syntax_error = False
    found_system_lock = False
    found_pio_error = False

    for line in lines:
        line_strip = line.strip()
        # Unity assert: ":FAIL:" format, or "[FAILED]" only on lines with a source path (cpp:N:)
        is_unity_fail = ":FAIL:" in line or (
            "[FAILED]" in line and (".cpp:" in line or ".c:" in line)
        )
        if is_unity_fail:
            cleaned_lines.append(f"{R}    {NC}{line_strip}")
            found_assert_fail = True
        elif ": error:" in line or "undefined reference" in line or "fatal error:" in line:
            cleaned_lines.append(f"{Y}    {NC}{line_strip}")
            found_syntax_error = True
        elif "Error:" in line or "ERROR:" in line:
            cleaned_lines.append(f"{M}    {NC}{line_strip}")
            found_pio_error = True
        elif "Permission denied" in line or "cannot open output file" in line or "Device or resource busy" in line:
            cleaned_lines.append(f"{M}    {NC}{line_strip}")
            found_system_lock = True

    if return_code == 0:
        if found_assert_fail:
            return STATUS_TEST_FAIL, "\n".join(cleaned_lines)
        return STATUS_PASS, ""

    # Assert failures take priority: a crash after :FAIL: is still a test failure.
    if found_assert_fail:
        return STATUS_TEST_FAIL, "\n".join(cleaned_lines)
    if found_system_lock or found_pio_error:
        return STATUS_SYSTEM_ERR, "\n".join(cleaned_lines)
    if found_syntax_error:
        return STATUS_COMPILE_ERR, "\n".join(cleaned_lines)

    if not cleaned_lines:
        cleaned_lines = [f"{M}    No error output captured.{NC}"]
    return STATUS_SYSTEM_ERR, "\n".join(cleaned_lines)


def parse_test_counts(log_text: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    total = None
    passed = None
    failed = None
    collected = None

    for line in log_text.split("\n"):
        line_strip = line.strip()
        if line_strip.startswith("Collected ") and " tests" in line_strip:
            parts = line_strip.split()
            if len(parts) >= 2:
                try:
                    collected = int(parts[1])
                except ValueError:
                    pass
        if " test cases:" in line_strip and ("failed" in line_strip or "succeeded" in line_strip):
            left, right = line_strip.split(" test cases:", 1)
            num = ""
            for ch in left:
                if ch.isdigit():
                    num += ch
                elif num:
                    break
            if num:
                try:
                    total = int(num)
                except ValueError:
                    pass
            failed = 0
            passed = 0
            parts = right.split(",")
            for part in parts:
                part = part.strip()
                if part.endswith("failed") or " failed" in part:
                    try:
                        failed = int(part.split()[0])
                    except ValueError:
                        pass
                if part.endswith("succeeded") or " succeeded" in part:
                    try:
                        passed = int(part.split()[0])
                    except ValueError:
                        pass
            if total is not None:
                if passed is None:
                    passed = 0
                if failed is None:
                    failed = 0
            break
    if total is None:
        total = collected
    return total, passed, failed


def list_platformio_envs(config_path: str = "platformio.ini") -> List[str]:
    envs = []
    if not os.path.exists(config_path):
        return envs
    with open(config_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                header = line[1:-1].strip()
                if header.startswith("env:"):
                    env_name = header[4:].strip()
                    if env_name and env_name not in envs:
                        envs.append(env_name)
    return envs


def parse_env_platforms(config_path: str = "platformio.ini") -> Dict[str, str]:
    env_platforms: Dict[str, str] = {}
    if not os.path.exists(config_path):
        return env_platforms
    current_env = None
    with open(config_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                header = line[1:-1].strip()
                if header.startswith("env:"):
                    current_env = header[4:].strip()
                else:
                    current_env = None
                continue
            if current_env and line.lower().startswith("platform"):
                key, _, value = line.partition("=")
                if key.strip().lower() == "platform":
                    platform = value.strip().split()[0] if value.strip() else ""
                    if platform:
                        env_platforms[current_env] = platform
    return env_platforms


def select_build_envs(envs: List[str]) -> List[str]:
    if not envs:
        return []
    if "native" in envs and "unix" in envs:
        if sys.platform == "win32":
            return [e for e in envs if e != "unix"]
        return [e for e in envs if e != "native"]
    return envs


def select_test_env(envs: List[str]) -> Optional[str]:
    if "native" in envs:
        return "native"
    if "unix" in envs:
        return "unix"
    return envs[0] if envs else None


def select_platforms_for_envs(envs: List[str], env_platforms: Dict[str, str]) -> List[str]:
    platforms: List[str] = []
    for env_name in envs:
        platform = env_platforms.get(env_name)
        if platform and platform not in platforms:
            platforms.append(platform)
    return platforms


def run_platform_install(platform: str) -> PlatformInstallResult:
    cmd = ["pio", "platform", "install", platform]
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=PROJECT_ROOT,
        )
        duration = time.time() - start_time
        status, clean_log = analyze_output(result.stdout, result.returncode)
        return PlatformInstallResult(platform, status, result.returncode, clean_log, duration)
    except Exception as e:
        return PlatformInstallResult(platform, STATUS_SYSTEM_ERR, -1, str(e), 0)


def run_clean_env(env_name: str) -> CleanResult:
    commands = [
        ["pio", "run", "-e", env_name, "-t", "clean"],
        ["pio", "pkg", "update", "-e", env_name],
        ["pio", "pkg", "install", "-e", env_name],
    ]
    start_time = time.time()
    output_chunks: List[str] = []
    return_code = 0
    try:
        for cmd in commands:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=PROJECT_ROOT,
            )
            output_chunks.append(result.stdout or "")
            if result.returncode != 0:
                return_code = result.returncode
                break
        duration = time.time() - start_time
        joined_output = "\n".join(chunk for chunk in output_chunks if chunk)
        status, clean_log = analyze_output(joined_output, return_code)
        return CleanResult(env_name, status, return_code, clean_log, duration)
    except Exception as e:
        return CleanResult(env_name, STATUS_SYSTEM_ERR, -1, str(e), 0)


def run_build_env(env_name: str) -> BuildResult:
    cmd = ["pio", "run", "-e", env_name]
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=PROJECT_ROOT,
        )
        duration = time.time() - start_time
        status, clean_log = analyze_output(result.stdout, result.returncode)
        return BuildResult(env_name, status, result.returncode, clean_log, duration)
    except Exception as e:
        return BuildResult(env_name, STATUS_SYSTEM_ERR, -1, str(e), 0)


def run_test_folder(folder_name: str, test_env: str) -> TestResult:
    unique_build_path = os.path.join(PARALLEL_BUILD_BASE, folder_name)
    env = os.environ.copy()
    env["PLATFORMIO_BUILD_DIR"] = unique_build_path

    cmd = ["pio", "test", "-e", test_env, "-f", folder_name]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=PROJECT_ROOT,
        )

        duration = time.time() - start_time
        status, clean_log = analyze_output(result.stdout, result.returncode)
        test_count, passed_count, failed_count = parse_test_counts(result.stdout)
        return TestResult(folder_name, status, result.returncode, clean_log, duration, test_count, passed_count, failed_count)
    except Exception as e:
        return TestResult(folder_name, STATUS_SYSTEM_ERR, -1, str(e), 0)


def _sep(char: str = "-") -> str:
    return char * W


def main(argv=None):
    global PROJECT_ROOT
    global TEST_DIR
    global PARALLEL_BUILD_BASE

    configure_console_output()

    parser = argparse.ArgumentParser(description="Run PlatformIO builds/tests with parallel execution.")
    parser.add_argument(
        "--project",
        default=".",
        help="Path to the PlatformIO project root (default: current directory).",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar updates (CI friendly).")
    parser.add_argument("--no-install", action="store_true", help="Skip PlatformIO platform installation step.")
    parser.add_argument("--no-builds", action="store_true", help="Skip environment build step.")
    parser.add_argument("--no-tests", action="store_true", help="Skip test execution step.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Refresh per-env dependencies by running clean, 'pio pkg update -e <env>', then install.",
    )
    args = parser.parse_args(argv)

    PROJECT_ROOT = os.path.abspath(args.project)
    TEST_DIR = os.path.join(PROJECT_ROOT, "test")
    PARALLEL_BUILD_BASE = os.path.join(PROJECT_ROOT, ".pio", "build_parallel")

    progress_enabled = (not args.no_progress) and supports_live_progress()
    run_start_time = time.time()

    config_path = os.path.join(PROJECT_ROOT, "platformio.ini")
    if not os.path.exists(config_path):
        print(f"{R}Project does not contain platformio.ini: {config_path}{NC}")
        return 2

    envs = list_platformio_envs(config_path)
    build_envs = select_build_envs(envs)
    env_platforms = parse_env_platforms(config_path)
    platforms_to_install = select_platforms_for_envs(build_envs, env_platforms)
    test_env = select_test_env(envs)
    clean_envs = build_envs if build_envs else envs

    # --- Print discovered environments ---
    if envs:
        print(f"{BS}Environments ({len(build_envs)} active):{NC}  " + "  ".join(
            f"{G}{e}{NC}" if e in build_envs else f"{DIM}{e}{NC}" for e in envs
        ))
        if test_env:
            print(f"{DIM}Test env: {test_env}{NC}")
        print()
    else:
        print(f"{Y}⚠️  No PlatformIO environments found in {config_path}.{NC}\n")

    test_folders: List[str] = []
    tests_skipped_reason: Optional[str] = None
    if args.no_tests:
        tests_skipped_reason = "Disabled by --no-tests."
    elif not test_env:
        tests_skipped_reason = "No compatible test environment."
    elif not os.path.exists(TEST_DIR):
        tests_skipped_reason = f"Directory '{TEST_DIR}' not found."
    else:
        test_folders = sorted(
            folder
            for folder in os.listdir(TEST_DIR)
            if os.path.isdir(os.path.join(TEST_DIR, folder))
        )
        if not test_folders:
            tests_skipped_reason = f"No test suite folders found in '{TEST_DIR}'."

    planned_phases: List[str] = []
    if args.clean:
        planned_phases.append("clean")
    if not args.no_install:
        planned_phases.append("install")
    if not args.no_builds:
        planned_phases.append("build")
    if not args.no_tests:
        planned_phases.append("test")

    progress = ProgressReporter(
        enabled=progress_enabled and bool(planned_phases),
        total_phases=len(planned_phases),
        global_start_time=run_start_time,
    )
    progress.start()

    clean_failed = False
    clean_note = ""
    clean_results: List[CleanResult] = []
    install_results: List[PlatformInstallResult] = []
    build_results: List[BuildResult] = []
    test_results: Dict[str, TestResult] = {}
    test_duration = 0.0
    total_tests = len(test_folders)

    try:
        # ── CLEAN ─────────────────────────────────────────────────────────────
        if args.clean:
            progress.set_stage("clean", max(1, len(clean_envs)))
            if clean_envs:
                # Package install/resolve is not concurrency-safe across multiple
                # environments in practice (lock contention and partial states).
                # Run clean/install sequentially for deterministic results.
                worker_count = 1
                progress.write(
                    f"{BS}🧹 Refreshing dependencies for {len(clean_envs)} environment(s){NC}"
                )
                progress.write(f"{DIM}  {worker_count} workers{NC}")
                clean_start_time = time.time()
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    retries: Dict[str, int] = {name: 0 for name in clean_envs}
                    pending = deque(clean_envs)
                    in_flight = {}

                    while pending or in_flight:
                        while pending and len(in_flight) < worker_count:
                            env_name = pending.popleft()
                            in_flight[executor.submit(run_clean_env, env_name)] = env_name

                        done_futures, _ = wait(
                            in_flight.keys(),
                            return_when=FIRST_COMPLETED,
                        )
                        for future in done_futures:
                            env_name = in_flight.pop(future)
                            try:
                                res = future.result()
                            except Exception as exc:
                                res = CleanResult(env_name, STATUS_SYSTEM_ERR, -1, str(exc), 0)

                            if res.status == STATUS_SYSTEM_ERR and retries[env_name] < MAX_RETRIES:
                                retries[env_name] += 1
                                progress.write(
                                    f"{Y}  ⚠  Retry {retries[env_name]}/{MAX_RETRIES}: clean {env_name}{NC}"
                                )
                                time.sleep(_retry_delay_seconds(retries[env_name]))
                                pending.append(env_name)
                                continue

                            clean_results.append(res)
                            progress.advance_stage()
                            if res.status == STATUS_PASS:
                                progress.write(f"{G}  ✔  clean {res.name}{NC}  {DIM}({res.duration:.1f}s){NC}")
                            else:
                                progress.write(f"{M}  ✘  clean {res.name}{NC}  {DIM}({res.duration:.1f}s){NC}")
                                if res.log:
                                    progress.write(res.log)
                clean_duration = time.time() - clean_start_time
                clean_failed_count = sum(1 for r in clean_results if r.status != STATUS_PASS)
                clean_failed = clean_failed_count > 0
                if clean_failed:
                    clean_note = (
                        f"{M}  ✘  {clean_failed_count}/{len(clean_results)} environment(s) failed "
                        f"dependency refresh{NC}"
                    )
                else:
                    clean_note = (
                        f"{G}  ✔  Refreshed {len(clean_results)} environment(s) "
                        f"in {clean_duration:.2f}s{NC}"
                    )
            else:
                clean_note = f"{Y}  ⚠  No environments found for dependency refresh{NC}"
                progress.advance_stage()
            progress.complete_stage()
            progress.write(clean_note)

        # ── PLATFORM INSTALL ──────────────────────────────────────────────────
        if args.no_install:
            print(f"{Y}  ⚠  Platform install skipped (--no-install){NC}")
        else:
            progress.set_stage("install", max(1, len(platforms_to_install)))
            if platforms_to_install:
                worker_count = min(MAX_WORKERS, len(platforms_to_install))
                progress.write(f"\n{BS}📦 Installing {len(platforms_to_install)} PlatformIO platform(s){NC}")
                progress.write(f"{DIM}  {worker_count} workers{NC}")
                install_start_time = time.time()
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    retries: Dict[str, int] = {name: 0 for name in platforms_to_install}
                    pending = deque(platforms_to_install)
                    in_flight = {}

                    while pending or in_flight:
                        while pending and len(in_flight) < worker_count:
                            platform = pending.popleft()
                            in_flight[executor.submit(run_platform_install, platform)] = platform

                        done_futures, _ = wait(
                            in_flight.keys(),
                            return_when=FIRST_COMPLETED,
                        )
                        for future in done_futures:
                            platform = in_flight.pop(future)
                            try:
                                res = future.result()
                            except Exception as exc:
                                res = PlatformInstallResult(platform, STATUS_SYSTEM_ERR, -1, str(exc), 0)

                            if res.status == STATUS_SYSTEM_ERR and retries[platform] < MAX_RETRIES:
                                retries[platform] += 1
                                progress.write(
                                    f"{Y}  ⚠  Retry {retries[platform]}/{MAX_RETRIES}: platform {platform}{NC}"
                                )
                                time.sleep(_retry_delay_seconds(retries[platform]))
                                pending.append(platform)
                                continue

                            install_results.append(res)
                            progress.advance_stage()
                            if res.status == STATUS_PASS:
                                progress.write(f"{G}  ✔  {res.name}{NC}  {DIM}({res.duration:.1f}s){NC}")
                            else:
                                progress.write(f"{M}  ✘  {res.name}{NC}  {DIM}({res.duration:.1f}s){NC}")
                                if res.log:
                                    progress.write(res.log)
                install_duration = time.time() - install_start_time
                progress.write(f"{DIM}  done in {install_duration:.2f}s{NC}")

                failed_platforms = {r.name for r in install_results if r.status != STATUS_PASS}
                if failed_platforms:
                    before_count = len(build_envs)
                    build_envs = [e for e in build_envs if env_platforms.get(e) not in failed_platforms]
                    skipped = before_count - len(build_envs)
                    if skipped > 0:
                        progress.write(
                            f"{Y}  ⚠  Skipping {skipped} build env(s) due to failed platform install(s){NC}"
                        )
            else:
                if envs:
                    progress.write(f"{Y}  ⚠  No compatible build platforms found — skipping installs{NC}")
                else:
                    progress.write(f"{Y}  ⚠  No PlatformIO environments found — skipping installs{NC}")
                progress.advance_stage()
            progress.complete_stage()

        # ── BUILD ──────────────────────────────────────────────────────────────
        if args.no_builds:
            print(f"{Y}  ⚠  Build stage skipped (--no-builds){NC}")
        else:
            progress.set_stage("build", max(1, len(build_envs)))
            if build_envs:
                worker_count = min(MAX_WORKERS, len(build_envs))
                progress.write(f"\n{BS}🔨 Building {len(build_envs)} environment(s){NC}")
                progress.write(f"{DIM}  {worker_count} workers{NC}")
                build_start_time = time.time()
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    retries: Dict[str, int] = {name: 0 for name in build_envs}
                    pending = deque(build_envs)
                    in_flight = {}

                    while pending or in_flight:
                        while pending and len(in_flight) < worker_count:
                            env_name = pending.popleft()
                            in_flight[executor.submit(run_build_env, env_name)] = env_name

                        done_futures, _ = wait(
                            in_flight.keys(),
                            return_when=FIRST_COMPLETED,
                        )
                        for future in done_futures:
                            env_name = in_flight.pop(future)
                            try:
                                res = future.result()
                            except Exception as exc:
                                res = BuildResult(env_name, STATUS_SYSTEM_ERR, -1, str(exc), 0)

                            if res.status == STATUS_SYSTEM_ERR and retries[env_name] < MAX_RETRIES:
                                retries[env_name] += 1
                                progress.write(
                                    f"{Y}  ⚠  Retry {retries[env_name]}/{MAX_RETRIES}: build {env_name}{NC}"
                                )
                                time.sleep(_retry_delay_seconds(retries[env_name]))
                                pending.append(env_name)
                                continue

                            build_results.append(res)
                            progress.advance_stage()
                            if res.status == STATUS_PASS:
                                progress.write(f"{G}  ✔  {res.name}{NC}  {DIM}({res.duration:.1f}s){NC}")
                            elif res.status == STATUS_COMPILE_ERR:
                                progress.write(f"{Y}  ✘  {res.name}  (build error){NC}  {DIM}({res.duration:.1f}s){NC}")
                                if res.log:
                                    progress.write(res.log)
                            else:
                                progress.write(f"{M}  ✘  {res.name}  (system crash){NC}  {DIM}({res.duration:.1f}s){NC}")
                                if res.log:
                                    progress.write(res.log)
                build_duration = time.time() - build_start_time
                progress.write(f"{DIM}  done in {build_duration:.2f}s{NC}")
            else:
                if envs:
                    progress.write(f"{Y}  ⚠  No compatible build environments for this platform — skipping{NC}")
                else:
                    progress.write(f"{Y}  ⚠  No PlatformIO environments found — skipping builds{NC}")
                progress.advance_stage()
            progress.complete_stage()

        # ── TESTS ──────────────────────────────────────────────────────────────
        if args.no_tests:
            print(f"{Y}  ⚠  Test stage skipped (--no-tests){NC}")
        else:
            progress.set_stage("test", max(1, total_tests))
            if tests_skipped_reason:
                progress.write(f"{Y}  ⚠  Tests skipped: {tests_skipped_reason}{NC}")
                progress.advance_stage()
                progress.complete_stage()
            else:
                worker_count = min(MAX_WORKERS, total_tests)
                progress.write(f"\n{BS}🧪 Testing on {test_env} — {total_tests} suite(s){NC}")
                progress.write(f"{DIM}  {worker_count} workers{NC}")
                stage_start = time.time()
                retries: Dict[str, int] = {name: 0 for name in test_folders}
                pending = deque(test_folders)

                try:
                    with ThreadPoolExecutor(max_workers=worker_count) as executor:
                        in_flight = {}

                        while pending or in_flight:
                            while pending and len(in_flight) < worker_count:
                                folder = pending.popleft()
                                future = executor.submit(run_test_folder, folder, test_env)
                                in_flight[future] = folder

                            done_futures, _ = wait(
                                in_flight.keys(),
                                return_when=FIRST_COMPLETED,
                            )
                            for future in done_futures:
                                folder = in_flight.pop(future)
                                try:
                                    res = future.result()
                                except Exception as exc:
                                    res = TestResult(folder, STATUS_SYSTEM_ERR, -1, str(exc), 0)

                                if res.status == STATUS_SYSTEM_ERR and retries[folder] < MAX_RETRIES:
                                    retries[folder] += 1
                                    progress.write(
                                        f"{Y}  ⚠  Retry {retries[folder]}/{MAX_RETRIES}: {folder}{NC}"
                                    )
                                    time.sleep(_retry_delay_seconds(retries[folder]))
                                    pending.append(folder)
                                    continue

                                test_results[folder] = res
                                progress.advance_stage()
                                count_str = f"  {DIM}[{res.test_count} cases]{NC}" if res.test_count is not None else ""
                                dur_str = f"  {DIM}({res.duration:.1f}s){NC}"
                                if res.status == STATUS_PASS:
                                    progress.write(
                                        f"{G}  ✔  {res.name}{NC}{count_str}{dur_str}"
                                    )
                                elif res.status == STATUS_TEST_FAIL:
                                    progress.write(f"{R}  ✘  {res.name}  (test failure){NC}{count_str}{dur_str}")
                                    if res.log:
                                        progress.write(res.log)
                                elif res.status == STATUS_COMPILE_ERR:
                                    progress.write(
                                        f"{Y}  ✘  {res.name}  (build failed){NC}{count_str}{dur_str}"
                                    )
                                    if res.log:
                                        progress.write(res.log)
                                else:
                                    progress.write(
                                        f"{M}  ✘  {res.name}  (system crash){NC}{count_str}{dur_str}"
                                    )
                                    if res.log:
                                        progress.write(res.log)
                except KeyboardInterrupt:
                    progress.stop()
                    print(f"\n{R}🛑 Cancelled.{NC}")
                    return 1

                test_duration = time.time() - stage_start
                progress.write(f"{DIM}  done in {test_duration:.2f}s{NC}")
                progress.complete_stage()
    finally:
        progress.stop()

    total_elapsed = time.time() - run_start_time
    elapsed_m, elapsed_s = divmod(int(total_elapsed), 60)
    elapsed_str = f"{elapsed_m}m {elapsed_s}s" if elapsed_m else f"{elapsed_s}s"

    # ── SUMMARY ────────────────────────────────────────────────────────────────
    def _status_color(status: str) -> str:
        return {STATUS_PASS: G, STATUS_TEST_FAIL: R, STATUS_COMPILE_ERR: Y}.get(status, M)

    def _status_label(status: str) -> str:
        return {
            STATUS_PASS: "pass",
            STATUS_TEST_FAIL: "fail",
            STATUS_COMPILE_ERR: "error",
            STATUS_SYSTEM_ERR: "crash",
        }.get(status, status)

    def _print_rows(rows: list) -> None:
        # rows: list of (icon, name, status_str, status_color, extra)
        # Pad name column to align status and extra columns.
        name_w = max((len(r[1]) for r in rows), default=0)
        for icon, name, status_str, color, extra in rows:
            name_pad = name.ljust(name_w)
            extra_str = f"  {DIM}{extra}{NC}" if extra else ""
            print(f"  {color}{icon}  {name_pad}  {status_str}{NC}{extra_str}")

    print(f"\n{_sep('═')}")
    print(f"{BS}  RESULTS{NC}  {DIM}({elapsed_str}){NC}")
    print(_sep("─"))

    # Clean
    if args.clean:
        print(f"{BS}  Clean{NC}")
        print(f"  {clean_note}")
        clean_failed_results = [r for r in clean_results if r.status != STATUS_PASS]
        if clean_failed_results:
            rows = [("✘", r.name, "fail", M, "") for r in clean_failed_results]
            _print_rows(rows)
        print(_sep("─"))

    # Platform installs
    if install_results:
        print(f"{BS}  Platforms{NC}")
        install_failed = [r for r in install_results if r.status != STATUS_PASS]
        if not install_failed:
            print(f"{G}  ✔  all {len(install_results)} installed{NC}")
        else:
            rows = [
                ("✔" if r.status == STATUS_PASS else "✘", r.name,
                 _status_label(r.status), _status_color(r.status), "")
                for r in install_results
            ]
            _print_rows(rows)
        print(_sep("─"))

    # Builds
    if build_results:
        print(f"{BS}  Builds{NC}")
        rows = [
            ("✔" if r.status == STATUS_PASS else "✘", r.name,
             _status_label(r.status), _status_color(r.status), f"{r.duration:.1f}s")
            for r in build_results
        ]
        _print_rows(rows)
        print(_sep("─"))
    elif not args.no_builds:
        print(f"{Y}  No build results.{NC}")
        print(_sep("─"))

    # Tests
    if tests_skipped_reason:
        print(f"{Y}  Tests skipped: {tests_skipped_reason}{NC}")
    elif test_results:
        total_test_cases = sum(r.test_count or 0 for r in test_results.values())
        total_passed_cases = sum(r.passed_count or 0 for r in test_results.values())
        total_failed_cases = sum(r.failed_count or 0 for r in test_results.values())

        print(f"{BS}  Tests{NC}  {DIM}env: {test_env}  {test_duration:.1f}s{NC}")
        rows = [
            (
                "✔" if r.status == STATUS_PASS else "✘",
                r.name,
                _status_label(r.status),
                _status_color(r.status),
                f"{r.test_count} cases" if r.test_count is not None else "",
            )
            for r in test_results.values()
        ]
        # Sort: passes first, then by name within each group
        rows.sort(key=lambda x: (0 if x[2] == "pass" else 1, x[1]))
        _print_rows(rows)

        print(_sep("─"))
        if total_test_cases > 0:
            fail_color = R if total_failed_cases > 0 else G
            print(
                f"  {G}{total_passed_cases} passed{NC}  "
                f"{fail_color}{total_failed_cases} failed{NC}  "
                f"{DIM}{total_test_cases} total{NC}"
            )
        else:
            print(f"{DIM}  No test case counts available.{NC}")
    elif test_env and not args.no_tests:
        print(f"{Y}  No test results.{NC}")

    print(_sep("═"))

    install_failed_list = [r for r in install_results if r.status != STATUS_PASS]
    build_failed_list = [r for r in build_results if r.status != STATUS_PASS]
    test_failed_list = [r for r in test_results.values() if r.status in (STATUS_TEST_FAIL, STATUS_COMPILE_ERR, STATUS_SYSTEM_ERR)]

    exit_code = 0
    if clean_failed:
        exit_code = 1
    if install_failed_list:
        exit_code = 1
    if build_failed_list:
        exit_code = 1
    if test_failed_list:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
