from __future__ import annotations

import sys
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformioEnv:
    name: str
    section: str
    values: dict[str, str]

    @property
    def platform(self) -> str | None:
        value = self.values.get("platform", "").strip()
        return value or None


def load_platformio_envs(path: Path) -> list[PlatformioEnv]:
    if not path.exists():
        return []

    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")

    envs: list[PlatformioEnv] = []
    for section in parser.sections():
        if not section.startswith("env:"):
            continue
        name = section.split(":", 1)[1].strip()
        values = {key.strip(): value.strip() for key, value in parser.items(section)}
        envs.append(PlatformioEnv(name=name, section=section, values=values))
    return envs


def env_names(path: Path) -> list[str]:
    return [env.name for env in load_platformio_envs(path)]


def env_platform_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for env in load_platformio_envs(path):
        if env.platform:
            mapping[env.name] = env.platform
    return mapping


def filter_envs(all_envs: list[str], requested: list[str] | None) -> list[str]:
    if not requested:
        return list(all_envs)
    requested_set = {value.strip() for value in requested if value.strip()}
    return [name for name in all_envs if name in requested_set]


def select_build_envs(envs: list[str]) -> list[str]:
    if "native" in envs and "unix" in envs:
        if sys.platform == "win32":
            return [env for env in envs if env != "unix"]
        return [env for env in envs if env != "native"]
    return list(envs)


def select_test_env(envs: list[str]) -> str | None:
    if "native" in envs:
        return "native"
    if "unix" in envs:
        return "unix"
    return envs[0] if envs else None
