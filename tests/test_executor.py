from __future__ import annotations

import unittest

from astra_support.testing.executor import run_parallel_with_retries


class ExecutorTests(unittest.TestCase):
    def test_retry_callback_receives_failed_result(self):
        attempts = 0
        retries = []

        def worker(item):
            nonlocal attempts
            attempts += 1
            return "retry" if attempts == 1 else "pass"

        results = run_parallel_with_retries(
            ["suite"],
            worker,
            max_workers=1,
            max_retries=1,
            should_retry=lambda result: result == "retry",
            on_retry=lambda item, attempt, result: retries.append((item, attempt, result)),
        )

        self.assertEqual(results, ["pass"])
        self.assertEqual(retries, [("suite", 1, "retry")])

