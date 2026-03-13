from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
import time


VERSION_LINE_RE = re.compile(
    r'^(?P<prefix>\s*version\s*=\s*")'
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r'(?P<suffix>[^"]*)"(?P<trailing>.*)$'
)


def bump_project_version(text: str, part: str = "patch") -> tuple[str, str]:
    lines = text.splitlines()
    in_project = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if not in_project:
            continue

        match = VERSION_LINE_RE.match(line)
        if not match:
            continue

        major = int(match.group("major"))
        minor = int(match.group("minor"))
        patch = int(match.group("patch"))
        suffix = match.group("suffix")

        if part == "major":
            major += 1
            minor = 0
            patch = 0
        elif part == "minor":
            minor += 1
            patch = 0
        else:
            patch += 1

        new_version = f"{major}.{minor}.{patch}{suffix}"
        lines[index] = (
            f'{match.group("prefix")}{new_version}"{match.group("trailing")}'
        )
        updated_text = "\n".join(lines)
        if text.endswith("\n"):
            updated_text += "\n"
        return updated_text, new_version

    raise ValueError("Could not find [project] version in pyproject.toml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump the project version in pyproject.toml")
    parser.add_argument(
        "--path",
        default="pyproject.toml",
        help="Path to the pyproject.toml file to update",
    )
    parser.add_argument(
        "--part",
        choices=["major", "minor", "patch"],
        default="patch",
        help="Semantic version component to increment",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    original_text = path.read_text(encoding="utf-8")
    updated_text, new_version = bump_project_version(original_text, part=args.part)
    if updated_text == original_text:
        print(new_version)
        return 0

    path.write_text(updated_text, encoding="utf-8")
    print(new_version)
    return 0


if __name__ == "__main__":
    time.sleep(30)  # Wait before modifying the file to allow pressing of the sync button before the file is changed
    raise SystemExit(main())
