from __future__ import annotations

import unittest

from astra_support.testing.analyze import STATUS_SYSTEM_ERR, analyze_output, is_retryable_system_error


class AnalyzeTests(unittest.TestCase):
    def test_windows_sharing_violation_is_retryable_system_error(self):
        status, log = analyze_output(
            "The process cannot access the file because it is being used by another process",
            1,
        )
        self.assertEqual(status, STATUS_SYSTEM_ERR)
        self.assertIn("being used by another process", log)
        self.assertTrue(is_retryable_system_error(log))

    def test_platformio_home_permissions_error_is_not_retryable(self):
        log = (
            "PermissionError: [Errno 13] Permission denied: 'platforms.lock'\n"
            "platformio.exception.HomeDirPermissionsError: directory is not owned by the current user"
        )
        self.assertFalse(is_retryable_system_error(log))

    def test_parallel_sconsign_rename_race_is_retryable(self):
        log = (
            "FileNotFoundError: [Errno 2] No such file or directory: "
            "'.pio/cache/.sconsign312.tmp' -> '.pio/cache/.sconsign312.dblite'"
        )
        self.assertTrue(is_retryable_system_error(log))
