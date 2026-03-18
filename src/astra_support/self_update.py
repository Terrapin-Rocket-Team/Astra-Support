from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Optional

CHECK_INTERVAL_SECONDS = 30
CHANGELOG_ENTRY_LIMIT = 5
CHANGELOG_DEPTH_STEPS = (32, 128, 512)
STATE_PATH = Path.home() / ".astra-support" / "update-state.json"


@dataclass
class UpdateInfo:
    available: bool
    current: str
    latest: Optional[str] = None
    install_spec: Optional[str] = None
    source: Optional[str] = None
    changes: list[str] = field(default_factory=list)
    additional_changes: int = 0


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


def _run_git_command(args: list[str], *, cwd: Path | None = None, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
    )


def _git_commit_exists(repo_dir: Path, commit: str) -> bool:
    result = _run_git_command(["cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo_dir)
    return result.returncode == 0


def _git_is_ancestor(repo_dir: Path, older: str, newer: str) -> bool:
    result = _run_git_command(["merge-base", "--is-ancestor", older, newer], cwd=repo_dir)
    return result.returncode == 0


def _git_log_subjects(repo_dir: Path, revspec: str, *, limit: int) -> list[str]:
    result = _run_git_command(
        ["log", "--format=%h %s", f"--max-count={limit}", revspec],
        cwd=repo_dir,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_git_change_summary(
    url: str,
    requested_revision: str,
    current_commit: str,
    latest_commit: str,
) -> tuple[list[str], int]:
    try:
        with tempfile.TemporaryDirectory(prefix="astra-support-update-") as temp_dir:
            repo_dir = Path(temp_dir)
            if _run_git_command(["init"], cwd=repo_dir).returncode != 0:
                return [], 0
            if _run_git_command(["remote", "add", "origin", url], cwd=repo_dir).returncode != 0:
                return [], 0

            log_lines: list[str] = []
            for depth in CHANGELOG_DEPTH_STEPS:
                fetch_result = _run_git_command(
                    ["fetch", "--depth", str(depth), "origin", requested_revision],
                    cwd=repo_dir,
                    timeout=15,
                )
                if fetch_result.returncode != 0:
                    return [], 0
                if _git_commit_exists(repo_dir, current_commit) and _git_is_ancestor(repo_dir, current_commit, "FETCH_HEAD"):
                    log_lines = _git_log_subjects(
                        repo_dir,
                        f"{current_commit}..FETCH_HEAD",
                        limit=CHANGELOG_ENTRY_LIMIT + 1,
                    )
                    break

            if not log_lines:
                log_lines = _git_log_subjects(repo_dir, latest_commit, limit=CHANGELOG_ENTRY_LIMIT + 1)

            additional_changes = max(0, len(log_lines) - CHANGELOG_ENTRY_LIMIT)
            return log_lines[:CHANGELOG_ENTRY_LIMIT], additional_changes
    except Exception:
        return [], 0


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

        result = _run_git_command(["ls-remote", url, requested_revision])
        if result.returncode != 0 or not result.stdout.strip():
            return None

        latest_commit = result.stdout.strip().split()[0]
        if latest_commit and latest_commit != current_commit:
            install_spec = f"git+{url}@{requested_revision}"
            changes, additional_changes = _get_git_change_summary(url, requested_revision, current_commit, latest_commit)
            return UpdateInfo(
                available=True,
                current=current,
                latest=latest_commit[:8],
                install_spec=install_spec,
                source="git",
                changes=changes,
                additional_changes=additional_changes,
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


def _build_update_notice(update: UpdateInfo, upgrade_cmd: str) -> list[str]:
    latest_label = update.latest or "newer"
    lines = [
        f"Update available: {update.current} -> {latest_label}",
        f"  run: {upgrade_cmd}",
    ]
    if update.changes:
        lines.append("  recent changes:")
        lines.extend(f"    - {change}" for change in update.changes)
        if update.additional_changes > 0:
            lines.append(f"    - ... and {update.additional_changes} more")
    return lines


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

    if shutil.which("pipx"):
        upgrade_cmd = "pipx upgrade astra-support"
    else:
        upgrade_cmd = "pip install --upgrade astra-support"

    for line in _build_update_notice(update, upgrade_cmd):
        print(line)
    return False
