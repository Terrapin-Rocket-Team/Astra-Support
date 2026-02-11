from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Optional

CHECK_INTERVAL_SECONDS = 6 * 60 * 60
STATE_PATH = Path.home() / ".astra-support" / "update-state.json"


@dataclass
class UpdateInfo:
    available: bool
    current: str
    latest: Optional[str] = None
    install_spec: Optional[str] = None
    source: Optional[str] = None


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_interactive() -> bool:
    if _is_truthy(os.getenv("CI")):
        return False
    return bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _should_check_now(force: bool) -> bool:
    if force:
        return True
    interval = CHECK_INTERVAL_SECONDS
    env_interval = os.getenv("ASTRA_SUPPORT_UPDATE_CHECK_INTERVAL_SECONDS")
    if env_interval:
        try:
            interval = max(0, int(env_interval))
        except ValueError:
            pass

    state = _read_state()
    last_checked = state.get("last_checked", 0)
    if not isinstance(last_checked, (int, float)):
        return True
    return (time.time() - float(last_checked)) >= interval


def _mark_checked() -> None:
    state = _read_state()
    state["last_checked"] = int(time.time())
    _write_state(state)


def _check_git_install(current: str) -> Optional[UpdateInfo]:
    try:
        dist = metadata.distribution("astra-support")
        direct_url_text = dist.read_text("direct_url.json")
        if not direct_url_text:
            return None
        direct_url = json.loads(direct_url_text)
        vcs_info = direct_url.get("vcs_info") or {}
        if vcs_info.get("vcs") != "git":
            return None

        url = (direct_url.get("url") or "").strip()
        if not url:
            return None
        if url.startswith("git+"):
            url = url[4:]

        requested_revision = vcs_info.get("requested_revision") or "main"
        current_commit = (vcs_info.get("commit_id") or "").strip()
        if not current_commit:
            return None

        result = subprocess.run(
            ["git", "ls-remote", url, requested_revision],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        latest_commit = result.stdout.strip().split()[0]
        if latest_commit and latest_commit != current_commit:
            install_spec = f"git+{url}@{requested_revision}"
            return UpdateInfo(
                available=True,
                current=current,
                latest=latest_commit[:8],
                install_spec=install_spec,
                source="git",
            )
    except Exception:
        return None
    return None


def _check_pypi_install(current: str) -> Optional[UpdateInfo]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "astra-support"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return None

        latest = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("available versions:"):
                versions = line.split(":", 1)[1].strip()
                if versions:
                    latest = versions.split(",", 1)[0].strip()
                break

        if latest and latest != current:
            return UpdateInfo(
                available=True,
                current=current,
                latest=latest,
                install_spec="astra-support",
                source="pypi",
            )
    except Exception:
        return None
    return None


def _get_update_info() -> Optional[UpdateInfo]:
    try:
        current = metadata.version("astra-support")
    except Exception:
        return None

    git_update = _check_git_install(current)
    if git_update and git_update.available:
        return git_update

    pypi_update = _check_pypi_install(current)
    if pypi_update and pypi_update.available:
        return pypi_update

    return UpdateInfo(available=False, current=current)


def _run_update(install_spec: Optional[str]) -> tuple[bool, str]:
    pipx_path = shutil.which("pipx")
    if pipx_path:
        try:
            res = subprocess.run(
                [pipx_path, "upgrade", "astra-support"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
                check=False,
            )
            if res.returncode == 0:
                return True, "Updated via pipx."
        except Exception:
            pass

    upgrade_target = install_spec or "astra-support"
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", upgrade_target],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )
        if res.returncode == 0:
            return True, "Updated via pip."
        return False, res.stdout.strip()[-400:]
    except Exception as exc:
        return False, str(exc)


def maybe_prompt_for_update(*, no_update_check: bool = False, force: bool = False) -> bool:
    if no_update_check:
        return False
    if _is_truthy(os.getenv("ASTRA_SUPPORT_DISABLE_UPDATE_CHECK")):
        return False
    if not _is_interactive():
        return False
    if not _should_check_now(force):
        return False

    _mark_checked()
    update = _get_update_info()
    if not update or not update.available:
        return False

    latest_label = update.latest or "newer"
    print(f"Update available for astra-support ({update.current} -> {latest_label}).")
    answer = input("Install update now? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        return False

    ok, message = _run_update(update.install_spec)
    if ok:
        print(message)
        print("Rerun your command to use the updated version.")
        return True

    print(f"Update failed: {message}")
    return False
