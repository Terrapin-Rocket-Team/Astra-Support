from __future__ import annotations

from ..testing.runner import run_tests


def main(argv=None):
    from argparse import ArgumentParser
    from pathlib import Path
    from ..testing.runner import TestRunnerOptions

    parser = ArgumentParser(description="Compatibility wrapper for the Astra Support test runner.")
    parser.add_argument("--project", "-C", default=".")
    parser.add_argument("--no-progress", "-P", action="store_true")
    parser.add_argument("--no-install", "-I", action="store_true")
    parser.add_argument("--no-builds", "-B", action="store_true")
    parser.add_argument("--no-tests", "-T", action="store_true")
    parser.add_argument("--clean", "-c", action="store_true")
    parser.add_argument("--env", action="append")
    args = parser.parse_args(argv)
    return run_tests(
        TestRunnerOptions(
            project_root=Path(args.project).resolve(),
            no_progress=args.no_progress,
            no_install=args.no_install,
            no_builds=args.no_builds,
            no_tests=args.no_tests,
            clean=args.clean,
            envs=args.env,
        )
    )
