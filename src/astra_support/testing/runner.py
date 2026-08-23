from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..console import safe_print
from ..platformio.config import env_names, filter_envs, select_build_envs, select_test_env
from ..prereqs import check_toolchain
from .analyze import (
    STATUS_PASS,
    STATUS_SYSTEM_ERR,
    analyze_output,
    is_retryable_system_error,
    parse_test_counts,
)
from .executor import run_parallel_with_retries
from .models import RunResult, TestRunResult
from .report import ProgressReporter, print_result, print_stage, print_summary


MAX_RETRIES = 3
# Four concurrent C++ builds are a safe default on ordinary developer machines.
# Users with more memory can increase this with --jobs or ASTRA_SUPPORT_JOBS.
DEFAULT_MAX_PARALLEL_WORKERS = 4


@dataclass
class TestRunnerOptions:
    project_root: Path
    no_progress: bool = False
    no_install: bool = False
    no_builds: bool = False
    no_tests: bool = False
    clean: bool = False
    update_deps: bool = False
    jobs: int | None = None
    envs: list[str] | None = None
    default_args: list[str] = field(default_factory=list)


@dataclass
class RunnerContext:
    project_root: Path
    pio_cmd: list[str]
    test_dir: Path
    parallel_build_base: Path
    envs: list[str]
    build_envs: list[str]
    test_env: str | None


def run_tests(options: TestRunnerOptions) -> int:
    project_root = options.project_root.resolve()
    config_path = project_root / "platformio.ini"
    if not config_path.exists():
        safe_print(f"Project does not contain platformio.ini: {config_path}")
        return 2

    available_envs = env_names(config_path)
    if not available_envs:
        safe_print(f"No PlatformIO environments found in {config_path}")
        return 2
    selected_envs = filter_envs(available_envs, options.envs)
    if options.envs:
        requested_envs = {value.strip() for value in options.envs if value.strip()}
        unknown_envs = sorted(requested_envs.difference(available_envs))
        if unknown_envs:
            safe_print(f"Unknown PlatformIO environment(s): {', '.join(unknown_envs)}")
            safe_print(f"Available environments: {', '.join(available_envs)}")
            return 2
    build_envs = select_build_envs(selected_envs)
    test_env = select_test_env(selected_envs)
    jobs = _configured_jobs(options.jobs)

    will_test_native = (not options.no_tests) and test_env in {"native", "unix"}
    toolchain = check_toolchain(
        require_platformio=True,
        require_cpp=will_test_native or any(env in {"native", "unix"} for env in build_envs),
        offer_install=True,
    )
    if toolchain.errors:
        for error in toolchain.errors:
            safe_print(error)
        return 2

    ctx = RunnerContext(
        project_root=project_root,
        pio_cmd=toolchain.platformio_cmd or ["pio"],
        test_dir=project_root / "test",
        parallel_build_base=project_root / ".pio" / "build_parallel",
        envs=selected_envs,
        build_envs=build_envs,
        test_env=test_env,
    )

    clean_results: list[RunResult] = []
    dependency_results: list[RunResult] = []
    build_results: list[RunResult] = []
    test_results: list[TestRunResult] = []
    progress = ProgressReporter(enabled=not options.no_progress)

    if options.clean and ctx.envs:
        print_stage("clean")
        clean_results = [_clean_parallel_test_builds(ctx)]
        clean_results.extend(
            _run_pool(
                ctx.envs,
                lambda env: _run_clean_env(ctx, env),
                progress=progress,
                stage_name="clean",
                jobs=1,
            )
        )
        _print_results(clean_results)
        if _has_failures(clean_results):
            safe_print("Clean failed; dependency, build, and test stages were skipped.")
            print_summary(clean_results, dependency_results, build_results, test_results)
            return 1

    if options.update_deps or not options.no_install:
        stage_name = "update" if options.update_deps else "prepare"
        print_stage(stage_name)
        if not options.update_deps and _dependencies_prepared(ctx):
            dependency_results = [RunResult("cached", STATUS_PASS, 0, "", 0.0)]
        else:
            dependency_results = _run_pool(
                ctx.envs,
                lambda env: _run_dependency_env(ctx, env, update=options.update_deps),
                progress=progress,
                stage_name=stage_name,
                jobs=1,
            )
        _print_results(dependency_results)
        if _has_failures(dependency_results):
            safe_print("Dependency preparation failed; build and test stages were skipped.")
            print_summary(clean_results, dependency_results, build_results, test_results)
            return 1
        _mark_dependencies_prepared(ctx)

    if not options.no_builds:
        print_stage("build")
        build_results = _run_pool(
            ctx.build_envs,
            lambda env: _run_build_env(ctx, env),
            progress=progress,
            stage_name="build",
            jobs=jobs,
        )
        _print_results(build_results)

    if not options.no_tests:
        print_stage("test")
        if ctx.test_env is None:
            safe_print("No compatible test environment found.")
        elif not ctx.test_dir.exists():
            safe_print(f"Test directory not found: {ctx.test_dir}")
        else:
            folders = sorted(path.name for path in ctx.test_dir.iterdir() if path.is_dir())
            test_results = _run_pool(
                folders,
                lambda folder: _run_test_folder(ctx, folder),
                progress=progress,
                stage_name="test",
                jobs=jobs,
            )
            for result in test_results:
                extra = f"[{result.test_count} cases]" if result.test_count is not None else ""
                print_result(result.name, result.status, result.duration, extra=extra, log=result.log)

    print_summary(clean_results, dependency_results, build_results, test_results)
    all_results = [*clean_results, *dependency_results, *build_results, *test_results]
    return 1 if _has_failures(all_results) else 0


def _configured_jobs(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, explicit)
    env_value = os.getenv("ASTRA_SUPPORT_JOBS")
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            pass
    return DEFAULT_MAX_PARALLEL_WORKERS


def _run_pool(items, worker, *, progress: ProgressReporter, stage_name: str, jobs: int):
    if not items:
        return []
    progress.start(stage_name, len(items))
    max_workers = max(1, min(len(items), (os.cpu_count() or 1), jobs))
    try:
        return run_parallel_with_retries(
            items,
            worker,
            max_workers=max_workers,
            max_retries=MAX_RETRIES,
            should_retry=lambda result: (
                result.status == STATUS_SYSTEM_ERR and is_retryable_system_error(result.log)
            ),
            on_retry=lambda item, attempt, result: progress.write(_retry_message(item, attempt, result)),
            on_result=lambda _item, _result: progress.advance(),
        )
    finally:
        progress.stop()


def _retry_message(item: object, attempt: int, result: RunResult) -> str:
    lines = [line.strip() for line in result.log.splitlines() if line.strip()]
    reason = lines[-1] if lines else "system error"
    if len(reason) > 160:
        reason = reason[:157] + "..."
    return f"retry {attempt}: {item} ({reason})"


def _run_command(ctx: RunnerContext, cmd: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=ctx.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return 1, f"System error while starting command: {exc}", time.time() - start
    return result.returncode, result.stdout, time.time() - start


def _run_dependency_env(ctx: RunnerContext, env_name: str, *, update: bool) -> RunResult:
    action = "update" if update else "install"
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "pkg", action, "-e", env_name])
    status, log = analyze_output(output, code)
    return RunResult(env_name, status, code, log, duration)


def _dependency_fingerprint(ctx: RunnerContext) -> str:
    digest = hashlib.sha256()
    digest.update((ctx.project_root / "platformio.ini").read_bytes())
    for env_name in ctx.envs:
        digest.update(b"\0")
        digest.update(env_name.encode("utf-8"))
    return digest.hexdigest()


def _dependency_stamp_path(ctx: RunnerContext) -> Path:
    return ctx.project_root / ".pio" / "astra-support" / "dependencies.json"


def _dependencies_prepared(ctx: RunnerContext) -> bool:
    stamp_path = _dependency_stamp_path(ctx)
    try:
        payload = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if payload.get("fingerprint") != _dependency_fingerprint(ctx):
        return False
    libdeps = ctx.project_root / ".pio" / "libdeps"
    return all((libdeps / env_name).is_dir() for env_name in ctx.envs)


def _mark_dependencies_prepared(ctx: RunnerContext) -> None:
    stamp_path = _dependency_stamp_path(ctx)
    try:
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = stamp_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps({"fingerprint": _dependency_fingerprint(ctx)}, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(stamp_path)
    except OSError:
        # A missing cache marker only costs another dependency check next run.
        pass


def _run_clean_env(ctx: RunnerContext, env_name: str) -> RunResult:
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "run", "-e", env_name, "-t", "clean"])
    status, log = analyze_output(output, code)
    return RunResult(env_name, status, code, log, duration)


def _clean_parallel_test_builds(ctx: RunnerContext) -> RunResult:
    start = time.time()
    try:
        _remove_tree_with_retries(ctx.parallel_build_base)
    except OSError as exc:
        return RunResult("parallel-tests", STATUS_SYSTEM_ERR, 1, str(exc), time.time() - start)
    return RunResult("parallel-tests", STATUS_PASS, 0, "", time.time() - start)


def _remove_tree_with_retries(path: Path, attempts: int = 5) -> None:
    if not path.exists():
        return
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt >= attempts:
                raise
            time.sleep(min(0.1 * attempt, 0.5))


def _run_build_env(ctx: RunnerContext, env_name: str) -> RunResult:
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "run", "-e", env_name])
    status, log = analyze_output(output, code)
    return RunResult(env_name, status, code, log, duration)


def _run_test_folder(ctx: RunnerContext, folder_name: str) -> TestRunResult:
    unique_build_path = ctx.parallel_build_base / folder_name
    env = os.environ.copy()
    env["PLATFORMIO_BUILD_DIR"] = str(unique_build_path)
    code, output, duration = _run_command(
        ctx,
        [*ctx.pio_cmd, "test", "-e", ctx.test_env or "", "-f", folder_name],
        env=env,
    )
    status, log = analyze_output(output, code)
    test_count, passed_count, failed_count = parse_test_counts(output)
    return TestRunResult(folder_name, status, code, log, duration, test_count, passed_count, failed_count)


def _print_results(results: list[RunResult]) -> None:
    for result in results:
        print_result(result.name, result.status, result.duration, log=result.log)


def _has_failures(results: list[RunResult]) -> bool:
    return any(result.status != STATUS_PASS for result in results)
