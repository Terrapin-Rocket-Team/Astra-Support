from __future__ import annotations

import argparse
import shutil
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
        run: astra-support test --project . --no-progress --clean
"""

DEFAULT_CONFIG = """version: 1
project: .
default_test_args:
  - --no-progress
"""

ENV_ALIASES = {
    "native": "native",
    "host": "native",
    "teensy41": "teensy41",
    "teensy": "teensy41",
    "esp32s3": "esp32s3",
    "esp32": "esp32s3",
    "stm32h723vehx": "stm32h723vehx",
    "stm32h7": "stm32h723vehx",
    "stm32": "stm32h723vehx",
}

ENV_TEMPLATES = {
    "native": {
        "env_name": "native",
        "snippet": """; --- Astra Support: managed native env ---
[env:native]
platform = native
test_build_src = yes
lib_compat_mode = off
lib_ldf_mode = chain+
build_flags =
  -std=c++17
  -DNATIVE=1
; --- Astra Support: end managed native env ---""",
    },
    "teensy41": {
        "env_name": "teensy41",
        "snippet": """; --- Astra Support: managed teensy41 env ---
[env:teensy41]
platform = teensy
framework = arduino
board = teensy41
build_flags =
  -D ENV_TEENSY
; --- Astra Support: end managed teensy41 env ---""",
    },
    "esp32s3": {
        "env_name": "esp32s3",
        "snippet": """; --- Astra Support: managed esp32s3 env ---
[env:esp32s3]
platform = espressif32
framework = arduino
board = esp32-s3-devkitm-1
build_unflags = -std=gnu++11
build_flags =
  -D ENV_ESP
; --- Astra Support: end managed esp32s3 env ---""",
    },
    "stm32h723vehx": {
        "env_name": "stm32h723vehx",
        "snippet": """; --- Astra Support: managed stm32h723vehx env ---
[env:stm32h723vehx]
platform = ststm32
framework = arduino
board = stm32h723vehx
board_build.variants_dir = custom_variants
board_build.ldscript = ldscripts/ldscript.ld
build_flags =
  -D ENV_STM
  -D STM32
  -D ARDUINO_GENERIC_H723VEHX
  -D USE_PWR_LDO_SUPPLY
  -D PIO_FRAMEWORK_ARDUINO_ENABLE_CDC
  -D USBCON
  -D USE_USB_HS
  -D USE_USB_HS_IN_FS
; --- Astra Support: end managed stm32h723vehx env ---""",
    },
}

ENV_ASSET_DIRS = {
    "stm32h723vehx": "env_assets/stm32h723vehx",
}

DEFAULT_INIT_ENVS = ["native", "teensy41", "esp32s3", "stm32h723vehx"]


def _template_root() -> Path:
    return Path(__file__).resolve().parent / "templates" / "project"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    _ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def _list_platformio_env_names(path: Path) -> set[str]:
    if not path.exists():
        return set()

    env_names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith("env:"):
                env_name = section[4:].strip()
                if env_name:
                    env_names.add(env_name)
    return env_names


def _resolve_env_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized not in ENV_ALIASES:
        supported = ", ".join(sorted(ENV_TEMPLATES.keys()))
        raise ValueError(f"Unsupported env '{name}'. Supported envs: {supported}")
    return ENV_ALIASES[normalized]


def _collect_requested_envs(values: list[str] | None) -> list[str]:
    requested = values or list(DEFAULT_INIT_ENVS)
    resolved: list[str] = []
    seen: set[str] = set()
    for value in requested:
        env_name = _resolve_env_name(value)
        if env_name in seen:
            continue
        resolved.append(env_name)
        seen.add(env_name)
    return resolved


def _ensure_platformio_envs(project_root: Path, envs: list[str]) -> list[str]:
    platformio_path = project_root / "platformio.ini"
    existing_envs = _list_platformio_env_names(platformio_path)
    existing_text = platformio_path.read_text(encoding="utf-8") if platformio_path.exists() else ""

    snippets_to_add: list[str] = []
    notes: list[str] = []
    for env_key in envs:
        env_name = ENV_TEMPLATES[env_key]["env_name"]
        if env_name in existing_envs:
            notes.append(f"platformio.ini: [env:{env_name}] already present")
            continue
        snippets_to_add.append(ENV_TEMPLATES[env_key]["snippet"])
        notes.append(f"platformio.ini: appended [env:{env_name}]")

    if snippets_to_add:
        prefix = "\n\n" if existing_text and not existing_text.endswith("\n") else "\n" if existing_text else ""
        addition = "\n\n".join(snippets_to_add).rstrip() + "\n"
        platformio_path.write_text(f"{existing_text}{prefix}{addition}", encoding="utf-8")

    return notes


def _copy_assets_for_env(project_root: Path, env_key: str, overwrite: bool) -> list[str]:
    asset_rel = ENV_ASSET_DIRS.get(env_key)
    if not asset_rel:
        return []

    source_root = _template_root() / asset_rel
    if not source_root.exists():
        return [f"assets: no packaged assets found for {env_key}"]

    copied = 0
    skipped = 0
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(source_root)
        destination = project_root / rel
        _ensure_parent(destination)
        if destination.exists() and not overwrite:
            skipped += 1
            continue
        shutil.copy2(source, destination)
        copied += 1

    return [f"assets: {env_key} copied={copied} skipped={skipped}"]


def _cmd_init(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_root}")

    if args.list_envs:
        print("Supported envs:")
        for env_name in sorted(ENV_TEMPLATES.keys()):
            print(f"- {env_name}")
        return 0

    requested_envs = _collect_requested_envs(args.env)
    _write_text(project_root / ".astra-support.yml", DEFAULT_CONFIG, args.overwrite)

    notes: list[str] = []
    if not args.skip_platformio_env:
        notes.extend(_ensure_platformio_envs(project_root, requested_envs))

    for env_key in requested_envs:
        notes.extend(_copy_assets_for_env(project_root, env_key, args.overwrite))

    if args.write_workflow:
        workflow_content = DEFAULT_WORKFLOW.replace("__SUPPORT_INSTALL__", args.support_install)
        _write_text(
            project_root / ".github" / "workflows" / "run_unit_tests.yml",
            workflow_content,
            args.overwrite,
        )

    print(f"Initialized Astra Support in {project_root}")
    if requested_envs:
        print(f"Requested envs: {', '.join(requested_envs)}")
    for note in notes:
        print(note)
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
    if args.clean:
        forward.append("--clean")
    forward.extend(["--project", args.project])
    return run_tests.main(forward)


def _cmd_hitl(args: argparse.Namespace) -> int:
    from .tools import run_sim

    forward = ["--project", args.project]
    passthrough = list(getattr(args, "extras", []))
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
        "--skip-platformio-env",
        action="store_true",
        help="Do not modify platformio.ini environment sections.",
    )
    p_init.add_argument(
        "--env",
        action="append",
        help=(
            "Environment to add (repeatable). Aliases: native|host, teensy|teensy41, "
            "esp32|esp32s3, stm32|stm32h7|stm32h723vehx. Defaults to native, teensy41, esp32s3, stm32h723vehx."
        ),
    )
    p_init.add_argument(
        "--list-envs",
        action="store_true",
        help="Print supported environment keys and exit.",
    )
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
    p_test.add_argument("--clean", action="store_true")
    p_test.set_defaults(func=_cmd_test)

    p_hitl = sub.add_parser("hitl", help="Run shared HITL/SITL simulation harness")
    p_hitl.add_argument("--project", default=".", help="Target repo path (default: .)")
    p_hitl.set_defaults(func=_cmd_hitl)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extras = parser.parse_known_args(argv)
    if maybe_prompt_for_update(no_update_check=args.no_update_check):
        return 0
    if getattr(args, "func", None) is _cmd_hitl:
        args.extras = extras
    elif extras:
        parser.error(f"unrecognized arguments: {' '.join(extras)}")
    return int(args.func(args))
