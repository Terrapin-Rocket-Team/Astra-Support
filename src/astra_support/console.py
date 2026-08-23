from __future__ import annotations

import os
import sys


class Ansi:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    RESET = "\033[0m"


def configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def supports_color(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.getenv("NO_COLOR") is not None:
        return False
    isatty = getattr(stream, "isatty", None)
    try:
        return bool(callable(isatty) and isatty())
    except Exception:
        return False


def safe_text(value: object, stream=None) -> str:
    text = str(value)
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except (LookupError, UnicodeEncodeError):
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def safe_print(*values: object, sep: str = " ", end: str = "\n", file=None, flush: bool = False) -> None:
    stream = file or sys.stdout
    text = sep.join(safe_text(value, stream) for value in values)
    print(text, end=end, file=stream, flush=flush)


def paint(text: str, color: str) -> str:
    if not supports_color():
        return text
    return f"{color}{text}{Ansi.RESET}"
