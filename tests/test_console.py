from __future__ import annotations

import io
import unittest
from unittest import mock

from astra_support import console


class _AsciiStream(io.StringIO):
    @property
    def encoding(self):
        return "ascii"

    def isatty(self):
        return False


class ConsoleTests(unittest.TestCase):
    def test_safe_text_replaces_unencodable_characters(self):
        self.assertEqual(console.safe_text("bad \u2603", _AsciiStream()), "bad ?")

    def test_safe_print_handles_unencodable_characters(self):
        stream = _AsciiStream()
        console.safe_print("bad \u2603", file=stream)
        self.assertEqual(stream.getvalue(), "bad ?\n")

    def test_paint_omits_ansi_for_redirected_output(self):
        with mock.patch.object(console.sys, "stdout", _AsciiStream()):
            self.assertEqual(console.paint("message", console.Ansi.RED), "message")

