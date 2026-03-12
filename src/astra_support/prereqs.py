from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolchainStatus:
    platformio_cmd: list[str] | None
    cpp_compiler: str | None
    notes: list[str]
    errors: list[str]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_interactive() -> bool:
    if _is_truthy(os.getenv("CI")):
        return False
    return bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())


def _install_assistant_enabled() -> bool:
    return not _is_truthy(os.getenv("ASTRA_SUPPORT_DISABLE_INSTALL_ASSIST"))


def _ask_yes_no(prompt: str, *, default_yes: bool = True) -> bool:
    default_hint = "[Y/n]" if default_yes else "[y/N]"
    try:
        raw = input(f"{prompt} {default_hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not raw:
        return default_yes
    return raw in {"y", "yes"}


def _run_install_command(cmd: list[str]) -> bool:
    display = " ".join(cmd)
    print(f"[Prereq] Running: {display}")
    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError:
        return False
    except Exception as exc:
        print(f"[Prereq] Command failed to start: {exc}")
        return False
    return result.returncode == 0


def _windows_cpp_candidate() -> str | None:
    candidates = [
        Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "LLVM" / "bin" / "clang++.exe",
        Path(r"C:\msys64\ucrt64\bin\g++.exe"),
        Path(r"C:\msys64\mingw64\bin\g++.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_platformio_command() -> list[str] | None:
    """Return a usable PlatformIO invocation."""
    if shutil.which("pio"):
        return ["pio"]

    try:
        probe = subprocess.run(
            [sys.executable, "-m", "platformio", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return None

    if probe.returncode == 0:
        return [sys.executable, "-m", "platformio"]
    return None


def resolve_cpp_compiler() -> str | None:
    for compiler in ("g++", "clang++", "c++"):
        if shutil.which(compiler):
            return compiler
    if sys.platform == "win32":
        return _windows_cpp_candidate()
    return None


def _platformio_install_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    commands.append([sys.executable, "-m", "pip", "install", "platformio"])
    if shutil.which("pipx"):
        commands.append(["pipx", "install", "platformio"])
    return commands


def _cpp_install_commands() -> tuple[list[list[str]], str]:
    system = platform.system().lower()
    if system == "windows":
        if shutil.which("winget"):
            return (
                [
                    [
                        "winget",
                        "install",
                        "-e",
                        "--id",
                        "LLVM.LLVM",
                        "--accept-source-agreements",
                        "--accept-package-agreements",
                    ]
                ],
                "LLVM (clang++) via winget",
            )
        if shutil.which("choco"):
            return ([["choco", "install", "llvm", "-y"]], "LLVM (clang++) via chocolatey")
        if shutil.which("scoop"):
            return ([["scoop", "install", "llvm"]], "LLVM (clang++) via scoop")
        return ([], "a package manager with LLVM/g++ package support (winget/choco/scoop)")

    if system == "darwin":
        if shutil.which("brew"):
            return ([["brew", "install", "gcc"]], "gcc via Homebrew")
        return ([], "Homebrew (brew install gcc)")

    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    sudo = [] if is_root else ["sudo"]
    if shutil.which("apt-get"):
        return (
            [
                [*sudo, "apt-get", "update"],
                [*sudo, "apt-get", "install", "-y", "g++"],
            ],
            "g++ via apt-get",
        )
    if shutil.which("dnf"):
        return ([ [*sudo, "dnf", "install", "-y", "gcc-c++"] ], "gcc-c++ via dnf")
    if shutil.which("yum"):
        return ([ [*sudo, "yum", "install", "-y", "gcc-c++"] ], "gcc-c++ via yum")
    if shutil.which("pacman"):
        return ([ [*sudo, "pacman", "-Sy", "--noconfirm", "gcc"] ], "gcc via pacman")
    if shutil.which("zypper"):
        return (
            [[*sudo, "zypper", "--non-interactive", "install", "gcc-c++"]],
            "gcc-c++ via zypper",
        )
    if shutil.which("apk"):
        return ([ [*sudo, "apk", "add", "g++"] ], "g++ via apk")
    return ([], "your distro package manager (install g++ or clang++)")


def _offer_install(tool_name: str, commands: list[list[str]], method_label: str) -> bool:
    print(f"[Prereq] Missing required tool: {tool_name}.")
    if method_label:
        print(f"[Prereq] Suggested method: {method_label}.")
    if not commands:
        return False

    if not _ask_yes_no(f"[Prereq] Install {tool_name} now?", default_yes=True):
        return False

    for cmd in commands:
        if _run_install_command(cmd):
            return True
    return False


def check_toolchain(
    *,
    require_platformio: bool,
    require_cpp: bool,
    offer_install: bool = False,
) -> ToolchainStatus:
    notes: list[str] = []
    errors: list[str] = []

    platformio_cmd = resolve_platformio_command() if require_platformio else None
    cpp_compiler = resolve_cpp_compiler() if require_cpp else None

    if offer_install and _install_assistant_enabled() and _is_interactive():
        if require_platformio and platformio_cmd is None:
            install_ok = _offer_install(
                "PlatformIO CLI",
                _platformio_install_commands(),
                "pip install platformio",
            )
            if install_ok:
                notes.append("PlatformIO installation command completed successfully.")
            platformio_cmd = resolve_platformio_command()

        if require_cpp and cpp_compiler is None:
            cpp_commands, cpp_method = _cpp_install_commands()
            install_ok = _offer_install("C++ compiler (g++/clang++)", cpp_commands, cpp_method)
            if install_ok:
                notes.append("C++ compiler installation command completed successfully.")
            cpp_compiler = resolve_cpp_compiler()

    if require_platformio:
        if platformio_cmd is None:
            errors.append(
                "PlatformIO CLI is required but was not found. "
                "Install it with 'pipx install platformio' or 'python -m pip install platformio'. "
                "Then re-run the command."
            )
        elif platformio_cmd[0] == "pio":
            notes.append("PlatformIO detected: using `pio` from PATH.")
        else:
            notes.append("PlatformIO detected: using `python -m platformio`.")

    if require_cpp:
        if cpp_compiler is None:
            errors.append(
                "A C++ compiler is required but was not found. "
                "Install g++ (or clang++) and ensure it is on PATH, then re-run the command."
            )
        else:
            notes.append(f"C++ compiler detected: `{cpp_compiler}`.")

    return ToolchainStatus(
        platformio_cmd=platformio_cmd,
        cpp_compiler=cpp_compiler,
        notes=notes,
        errors=errors,
    )
