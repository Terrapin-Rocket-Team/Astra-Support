from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import __version__
from .self_update import maybe_prompt_for_update

DEFAULT_WORKFLOW = """name: Run Unit Tests

on:
  pull_request:
  push:

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        with:
          path: |
            ~/.cache/pip
            ~/.platformio
          key: ${{ runner.os }}-pio-${{ hashFiles('platformio.ini') }}
          restore-keys: |
            ${{ runner.os }}-pio-
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install PlatformIO Core
        run: pip install --upgrade platformio pipx
      - name: Install Astra Support CLI
        run: pipx install \"__SUPPORT_INSTALL__\"
      - name: Run Shared Test Runner
        run: astra-support test --project . --no-progress
"""

DEFAULT_CONFIG = """version: 1
project: .
default_test_args:
  - --no-progress
"""


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    _ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def _cmd_init(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_root}")

    _write_text(project_root / ".astra-support.yml", DEFAULT_CONFIG, args.overwrite)

    if args.write_workflow:
        workflow_content = DEFAULT_WORKFLOW.replace("__SUPPORT_INSTALL__", args.support_install)
        _write_text(
            project_root / ".github" / "workflows" / "run_unit_tests.yml",
            workflow_content,
            args.overwrite,
        )

    print(f"Initialized Astra Support in {project_root}")
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    from .tools import run_tests

    forward = []
    if args.no_progress:
        forward.append("--no-progress")
    if args.no_install:
        forward.append("--no-install")
    if args.no_builds:
        forward.append("--no-builds")
    if args.no_tests:
        forward.append("--no-tests")
    forward.extend(["--project", args.project])
    return run_tests.main(forward)


def _cmd_hitl(args: argparse.Namespace) -> int:
    from .tools import run_sim

    forward = ["--project", args.project]
    passthrough = list(args.args)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    forward.extend(passthrough)
    return run_sim.main(forward)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astra-support", description="Shared tooling for Astra-based repos")
    parser.add_argument("--version", action="version", version=f"astra-support {__version__}")
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Skip interactive CLI update checks for this invocation.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize a repo with Astra Support config/workflow")
    p_init.add_argument("--project", default=".", help="Target repo path (default: .)")
    p_init.add_argument("--write-workflow", action="store_true", help="Write .github/workflows/run_unit_tests.yml")
    p_init.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files")
    p_init.add_argument(
        "--support-install",
        default="git+https://github.com/Terrapin-Rocket-Team/Astra-Support.git@main",
        help="pip/pipx install spec written into generated workflow",
    )
    p_init.set_defaults(func=_cmd_init)

    p_test = sub.add_parser("test", help="Run shared PlatformIO test runner")
    p_test.add_argument("--project", default=".", help="Target repo path (default: .)")
    p_test.add_argument("--no-progress", action="store_true")
    p_test.add_argument("--no-install", action="store_true")
    p_test.add_argument("--no-builds", action="store_true")
    p_test.add_argument("--no-tests", action="store_true")
    p_test.set_defaults(func=_cmd_test)

    p_hitl = sub.add_parser("hitl", help="Run shared HITL/SITL simulation harness")
    p_hitl.add_argument("--project", default=".", help="Target repo path (default: .)")
    p_hitl.add_argument("args", nargs=argparse.REMAINDER, help="Arguments forwarded to run_sim")
    p_hitl.set_defaults(func=_cmd_hitl)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if maybe_prompt_for_update(no_update_check=args.no_update_check):
        return 0
    return int(args.func(args))
