from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from astra_support.testing.analyze import STATUS_PASS
from astra_support.testing.report import print_result


class ReportTests(unittest.TestCase):
    def test_redirected_result_output_is_ascii_and_has_no_ansi(self):
        output = io.StringIO()
        with redirect_stdout(output):
            print_result("native", STATUS_PASS, 1.25)

        rendered = output.getvalue()
        self.assertIn("[ok] native: pass", rendered)
        self.assertNotIn("\x1b", rendered)
        rendered.encode("ascii")
