from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunResult:
    name: str
    status: str
    code: int
    log: str
    duration: float


@dataclass
class TestRunResult(RunResult):
    test_count: int | None = None
    passed_count: int | None = None
    failed_count: int | None = None
