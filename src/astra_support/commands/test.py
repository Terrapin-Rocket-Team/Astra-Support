from __future__ import annotations

from pathlib import Path

from ..config.support_file import load_support_config
from ..testing.runner import TestRunnerOptions, run_tests


def run(args) -> int:
    project_root = Path(args.project).resolve()
    config = load_support_config(project_root, args.config)
    default_flags = set(config.test_args)
    options = TestRunnerOptions(
        project_root=project_root,
        no_progress=args.no_progress or "--no-progress" in default_flags or "-P" in default_flags,
        no_install=args.no_install or "--no-install" in default_flags or "-I" in default_flags,
        no_builds=args.no_builds or "--no-builds" in default_flags or "-B" in default_flags,
        no_tests=args.no_tests or "--no-tests" in default_flags or "-T" in default_flags,
        clean=args.clean or "--clean" in default_flags or "-c" in default_flags,
        envs=args.env,
        default_args=config.test_args,
    )
    return run_tests(options)
