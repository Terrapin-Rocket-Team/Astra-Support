from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MANAGED_ENVS = ["native", "teensy41", "esp32s3", "stm32h723vehx"]


@dataclass
class SupportConfig:
    path: Path | None = None
    project: str = "."
    test_args: list[str] = field(default_factory=list)
    sim_args: list[str] = field(default_factory=list)
    dataset_paths: list[str] = field(default_factory=list)
    sitl_exe: str | None = None
    hitl_port: str | None = None
    managed_envs: list[str] = field(default_factory=lambda: list(DEFAULT_MANAGED_ENVS))
    write_workflow: bool = True


def default_config_text() -> str:
    return """version: 1
project: .
defaults:
  test_args:
    - --no-progress
  sim_args: []
paths:
  dataset_paths: []
  sitl_exe:
  hitl_port:
managed:
  envs:
    - native
    - teensy41
    - esp32s3
    - stm32h723vehx
  write_workflow: true
"""


def find_support_file(project_root: Path, explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        candidate = Path(explicit_path)
        return candidate if candidate.is_absolute() else (project_root / candidate)
    candidate = project_root / ".astra-support.yml"
    return candidate if candidate.exists() else None


def load_support_config(project_root: Path, explicit_path: str | None = None) -> SupportConfig:
    path = find_support_file(project_root, explicit_path)
    if path is None or not path.exists():
        return SupportConfig()

    payload = _parse_support_file(path.read_text(encoding="utf-8"))
    defaults = payload.get("defaults") or {}
    paths = payload.get("paths") or {}
    managed = payload.get("managed") or {}
    config = SupportConfig(path=path)
    config.project = str(payload.get("project", "."))
    config.test_args = [str(value) for value in defaults.get("test_args", [])]
    config.sim_args = [str(value) for value in defaults.get("sim_args", [])]
    config.dataset_paths = [str(value) for value in paths.get("dataset_paths", [])]
    config.sitl_exe = _clean_optional(paths.get("sitl_exe"))
    config.hitl_port = _clean_optional(paths.get("hitl_port"))
    config.managed_envs = [str(value) for value in managed.get("envs", DEFAULT_MANAGED_ENVS)]
    config.write_workflow = bool(managed.get("write_workflow", True))
    return config


def resolve_project_root(project_arg: str, config: SupportConfig) -> Path:
    value = project_arg or config.project or "."
    return Path(value).resolve()


def write_default_config(path: Path, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(), encoding="utf-8")
    return True


def _clean_optional(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _parse_support_file(text: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    section: str | None = None
    nested_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if indent == 0:
            nested_key = None
            if line.endswith(":"):
                section = line[:-1]
                payload.setdefault(section, {})
                continue
            key, _, value = line.partition(":")
            payload[key.strip()] = _parse_scalar(value.strip())
            section = None
            continue

        if section is None:
            continue
        container = payload.setdefault(section, {})
        if not isinstance(container, dict):
            continue

        if indent == 2:
            if line.endswith(":"):
                nested_key = line[:-1]
                container[nested_key] = []
            else:
                key, _, value = line.partition(":")
                container[key.strip()] = _parse_scalar(value.strip())
                nested_key = key.strip()
            continue

        if indent == 4 and line.startswith("- ") and nested_key:
            target = container.setdefault(nested_key, [])
            if isinstance(target, list):
                target.append(_parse_scalar(line[2:].strip()))

    return payload


def _parse_scalar(value: str):
    if value == "":
        return None
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return value
