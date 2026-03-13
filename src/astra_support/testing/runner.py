from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..platformio.config import env_platform_map, env_names, filter_envs, select_build_envs, select_test_env
from ..prereqs import check_toolchain
from .analyze import STATUS_PASS, STATUS_SYSTEM_ERR, analyze_output, parse_test_counts
from .executor import run_parallel_with_retries
from .models import RunResult, TestRunResult
from .report import ProgressReporter, print_result, print_stage, print_summary


MAX_RETRIES = 3


@dataclass
class TestRunnerOptions:
    project_root: Path
    no_progress: bool = False
    no_install: bool = False
    no_builds: bool = False
    no_tests: bool = False
    clean: bool = False
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
    platforms: dict[str, str]
    test_env: str | None


def run_tests(options: TestRunnerOptions) -> int:
    project_root = options.project_root.resolve()
    config_path = project_root / "platformio.ini"
    if not config_path.exists():
        print(f"Project does not contain platformio.ini: {config_path}")
        return 2

    all_envs = env_names(config_path)
    selected_envs = filter_envs(all_envs, options.envs)
    build_envs = select_build_envs(selected_envs)
    test_env = select_test_env(selected_envs)
    platforms = env_platform_map(config_path)

    will_test_native = (not options.no_tests) and test_env in {"native", "unix"}
    toolchain = check_toolchain(
        require_platformio=True,
        require_cpp=will_test_native or any(env in {"native", "unix"} for env in build_envs),
        offer_install=True,
    )
    if toolchain.errors:
        for error in toolchain.errors:
            print(error)
        return 2

    ctx = RunnerContext(
        project_root=project_root,
        pio_cmd=toolchain.platformio_cmd or ["pio"],
        test_dir=project_root / "test",
        parallel_build_base=project_root / ".pio" / "build_parallel",
        envs=selected_envs,
        build_envs=build_envs,
        platforms=platforms,
        test_env=test_env,
    )

    clean_results: list[RunResult] = []
    install_results: list[RunResult] = []
    build_results: list[RunResult] = []
    test_results: list[TestRunResult] = []
    progress = ProgressReporter(enabled=not options.no_progress)

    if options.clean and ctx.envs:
        print_stage("clean")
        clean_results = _run_pool(
            ctx.envs,
            lambda env: _run_clean_env(ctx, env),
            progress=progress,
            stage_name="clean",
        )
        for result in clean_results:
            print_result(result.name, result.status, result.duration, log=result.log)

    if not options.no_install:
        print_stage("install")
        platforms_to_install = _platforms_for_envs(ctx.build_envs, ctx.platforms)
        install_results = _run_pool(
            platforms_to_install,
            lambda platform: _run_platform_install(ctx, platform),
            progress=progress,
            stage_name="install",
        )
        for result in install_results:
            print_result(result.name, result.status, result.duration, log=result.log)

    if not options.no_builds:
        print_stage("build")
        build_results = _run_pool(
            ctx.build_envs,
            lambda env: _run_build_env(ctx, env),
            progress=progress,
            stage_name="build",
        )
        for result in build_results:
            print_result(result.name, result.status, result.duration, log=result.log)

    if not options.no_tests:
        print_stage("test")
        if ctx.test_env is None:
            print("No compatible test environment found.")
        elif not ctx.test_dir.exists():
            print(f"Test directory not found: {ctx.test_dir}")
        else:
            folders = sorted(path.name for path in ctx.test_dir.iterdir() if path.is_dir())
            test_results = _run_pool(
                folders,
                lambda folder: _run_test_folder(ctx, folder),
                progress=progress,
                stage_name="test",
            )
            for result in test_results:
                extra = f"[{result.test_count} cases]" if result.test_count is not None else ""
                print_result(result.name, result.status, result.duration, extra=extra, log=result.log)

    print_summary(clean_results, install_results, build_results, test_results)
    failures = [result for result in [*clean_results, *install_results, *build_results, *test_results] if result.status != STATUS_PASS]
    return 1 if failures else 0


def _run_pool(items, worker, *, progress: ProgressReporter, stage_name: str):
    if not items:
        return []
    progress.start(stage_name, len(items))
    max_workers = max(1, min(len(items), (os.cpu_count() or 1) - 1))
    try:
        return run_parallel_with_retries(
            items,
            worker,
            max_workers=max_workers,
            max_retries=MAX_RETRIES,
            should_retry=lambda result: result.status == STATUS_SYSTEM_ERR,
            on_retry=lambda item, attempt: progress.write(f"retry {attempt}: {item}"),
            on_result=lambda _item, _result: progress.advance(),
        )
    finally:
        progress.stop()


def _platforms_for_envs(envs: list[str], mapping: dict[str, str]) -> list[str]:
    ordered: list[str] = []
    for env in envs:
        platform = mapping.get(env)
        if platform and platform not in ordered:
            ordered.append(platform)
    return ordered


def _run_command(ctx: RunnerContext, cmd: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    start = time.time()
    result = subprocess.run(
        cmd,
        cwd=ctx.project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout, time.time() - start


def _run_platform_install(ctx: RunnerContext, platform: str) -> RunResult:
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "platform", "install", platform])
    status, log = analyze_output(output, code)
    return RunResult(platform, status, code, log, duration)


def _run_clean_env(ctx: RunnerContext, env_name: str) -> RunResult:
    outputs: list[str] = []
    code = 0
    duration = 0.0
    for cmd in (
        [*ctx.pio_cmd, "run", "-e", env_name, "-t", "clean"],
        [*ctx.pio_cmd, "pkg", "update", "-e", env_name],
        [*ctx.pio_cmd, "pkg", "install", "-e", env_name],
    ):
        code, output, step_duration = _run_command(ctx, cmd)
        outputs.append(output)
        duration += step_duration
        if code != 0:
            break
    joined = "\n".join(part for part in outputs if part)
    status, log = analyze_output(joined, code)
    return RunResult(env_name, status, code, log, duration)


def _run_build_env(ctx: RunnerContext, env_name: str) -> RunResult:
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "run", "-e", env_name])
    status, log = analyze_output(output, code)
    return RunResult(env_name, status, code, log, duration)


def _run_test_folder(ctx: RunnerContext, folder_name: str) -> TestRunResult:
    unique_build_path = ctx.parallel_build_base / folder_name
    env = os.environ.copy()
    env["PLATFORMIO_BUILD_DIR"] = str(unique_build_path)
    code, output, duration = _run_command(ctx, [*ctx.pio_cmd, "test", "-e", ctx.test_env or "", "-f", folder_name], env=env)
    status, log = analyze_output(output, code)
    test_count, passed_count, failed_count = parse_test_counts(output)
    return TestRunResult(folder_name, status, code, log, duration, test_count, passed_count, failed_count)
