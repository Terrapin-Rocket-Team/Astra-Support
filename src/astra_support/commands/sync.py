from __future__ import annotations

import shutil
from pathlib import Path

from ..config.support_file import DEFAULT_MANAGED_ENVS, write_default_config

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

ENV_TEMPLATE_FILES = {
    "native": "assets/envs/native.ini",
    "teensy41": "assets/envs/teensy41.ini",
    "esp32s3": "assets/envs/esp32s3.ini",
    "stm32h723vehx": "assets/envs/stm32h723vehx.ini",
}

ENV_ASSET_DIRS = {
    "stm32h723vehx": "env_assets/stm32h723vehx",
}

DEFAULT_GITIGNORE_PATTERNS = [
    ".pio_native_verbose.log",
    "sim_log_*.csv",
]


def run(args) -> int:
    project_root = Path(args.project).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_root}")

    if args.list_envs:
        print("Supported envs:")
        for env_name in sorted(ENV_TEMPLATE_FILES):
            print(f"- {env_name}")
        return 0

    envs = _collect_requested_envs(args.env)
    notes: list[str] = []
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else project_root / ".astra-support.yml"
    config_written = write_default_config(config_path, args.overwrite)
    if config_written:
        notes.append(f"{config_path.name}: created")
    elif config_path.exists():
        notes.append(f"{config_path.name}: preserved")

    notes.extend(_ensure_gitignore_patterns(project_root, DEFAULT_GITIGNORE_PATTERNS))
    if not args.skip_platformio_env:
        notes.extend(_ensure_platformio_envs(project_root, envs))

    for env_key in envs:
        notes.extend(_copy_assets_for_env(project_root, env_key, args.overwrite))

    if args.write_workflow:
        workflow_content = _workflow_template().replace("__SUPPORT_INSTALL__", args.support_install)
        wrote = _write_text(
            project_root / ".github" / "workflows" / "run_astra_support.yml",
            workflow_content,
            args.overwrite,
        )
        notes.append(".github/workflows/run_astra_support.yml: created" if wrote else ".github/workflows/run_astra_support.yml: preserved")

    print(f"Synchronized Astra Support in {project_root}")
    if envs:
        print(f"Managed envs: {', '.join(envs)}")
    for note in notes:
        print(note)
    return 0


def _asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "project"


def _workflow_template() -> str:
    workflow_path = Path(__file__).resolve().parents[1] / "assets" / "run-support-workflow.yml"
    return workflow_path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _resolve_env_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized not in ENV_ALIASES:
        supported = ", ".join(sorted(ENV_TEMPLATE_FILES))
        raise ValueError(f"Unsupported env '{name}'. Supported envs: {supported}")
    return ENV_ALIASES[normalized]


def _collect_requested_envs(values: list[str] | None) -> list[str]:
    requested = values or list(DEFAULT_MANAGED_ENVS)
    resolved: list[str] = []
    seen: set[str] = set()
    for value in requested:
        env_name = _resolve_env_name(value)
        if env_name in seen:
            continue
        seen.add(env_name)
        resolved.append(env_name)
    return resolved


def _list_platformio_env_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    env_names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[env:") and line.endswith("]"):
            env_name = line[5:-1].strip()
            if env_name:
                env_names.add(env_name)
    return env_names


def _ensure_platformio_envs(project_root: Path, envs: list[str]) -> list[str]:
    platformio_path = project_root / "platformio.ini"
    existing_envs = _list_platformio_env_names(platformio_path)
    existing_text = platformio_path.read_text(encoding="utf-8") if platformio_path.exists() else ""
    snippets: list[str] = []
    notes: list[str] = []
    for env_name in envs:
        if env_name in existing_envs:
            notes.append(f"platformio.ini: [env:{env_name}] already present")
            continue
        snippet_path = _asset_root() / ENV_TEMPLATE_FILES[env_name]
        snippets.append(snippet_path.read_text(encoding="utf-8").rstrip())
        notes.append(f"platformio.ini: appended [env:{env_name}]")
    if snippets:
        prefix = "\n\n" if existing_text and not existing_text.endswith("\n") else "\n" if existing_text else ""
        appended_text = "\n\n".join(snippets).rstrip()
        platformio_path.write_text(
            f"{existing_text}{prefix}{appended_text}\n",
            encoding="utf-8",
        )
    return notes


def _copy_assets_for_env(project_root: Path, env_key: str, overwrite: bool) -> list[str]:
    asset_rel = ENV_ASSET_DIRS.get(env_key)
    if not asset_rel:
        return []
    source_root = _asset_root() / asset_rel
    copied = 0
    skipped = 0
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        destination = project_root / source.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not overwrite:
            skipped += 1
            continue
        shutil.copy2(source, destination)
        copied += 1
    return [f"assets: {env_key} copied={copied} skipped={skipped}"]


def _ensure_gitignore_patterns(project_root: Path, patterns: list[str]) -> list[str]:
    gitignore_path = project_root / ".gitignore"
    lines = gitignore_path.read_text(encoding="utf-8").splitlines() if gitignore_path.exists() else []
    existing = {line.strip() for line in lines if line.strip()}
    missing = [pattern for pattern in patterns if pattern not in existing]
    if not missing:
        return [".gitignore: diagnostics patterns already present"]
    if lines and lines[-1].strip():
        lines.append("")
    if "# Astra Support diagnostics" not in existing:
        lines.append("# Astra Support diagnostics")
    lines.extend(missing)
    gitignore_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [f".gitignore: added {', '.join(missing)}"]
