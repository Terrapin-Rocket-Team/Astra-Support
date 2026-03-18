from __future__ import annotations

import unittest
from unittest import mock

from astra_support import self_update


class SelfUpdateTests(unittest.TestCase):
    def test_build_update_notice_includes_commit_summaries(self):
        update = self_update.UpdateInfo(
            available=True,
            current="0.2.11",
            latest="abc12345",
            source="git",
            changes=[
                "abc12345 Tighten update prompt formatting",
                "def67890 Remove Mach line from control plot",
            ],
            additional_changes=2,
        )

        lines = self_update._build_update_notice(update, "pipx upgrade astra-support")

        self.assertEqual(lines[0], "Update available: 0.2.11 -> abc12345")
        self.assertEqual(lines[1], "  run: pipx upgrade astra-support")
        self.assertIn("  recent changes:", lines)
        self.assertIn("    - abc12345 Tighten update prompt formatting", lines)
        self.assertIn("    - def67890 Remove Mach line from control plot", lines)
        self.assertIn("    - ... and 2 more", lines)

    def test_maybe_prompt_for_update_prints_notice_lines(self):
        update = self_update.UpdateInfo(
            available=True,
            current="0.2.11",
            latest="abc12345",
            source="git",
            changes=["abc12345 Tighten update prompt formatting"],
        )

        with (
            mock.patch.object(self_update, "_is_interactive", return_value=True),
            mock.patch.object(self_update, "_should_check_now", return_value=True),
            mock.patch.object(self_update, "_mark_checked"),
            mock.patch.object(self_update, "_get_update_info", return_value=update),
            mock.patch.object(self_update.shutil, "which", return_value="pipx"),
            mock.patch("builtins.print") as patched_print,
        ):
            result = self_update.maybe_prompt_for_update()

        self.assertFalse(result)
        printed_lines = [call.args[0] for call in patched_print.call_args_list]
        self.assertEqual(
            printed_lines,
            [
                "Update available: 0.2.11 -> abc12345",
                "  run: pipx upgrade astra-support",
                "  recent changes:",
                "    - abc12345 Tighten update prompt formatting",
            ],
        )

    def test_check_git_install_attaches_change_summary(self):
        direct_url_payload = """
        {
          "url": "git+https://example.com/astra-support.git",
          "vcs_info": {
            "vcs": "git",
            "requested_revision": "main",
            "commit_id": "oldcommit"
          }
        }
        """.strip()
        dist = mock.Mock()
        dist.read_text.return_value = direct_url_payload

        ls_remote_result = mock.Mock(returncode=0, stdout="newcommit\trefs/heads/main\n")
        with (
            mock.patch.object(self_update.metadata, "distribution", return_value=dist),
            mock.patch.object(self_update, "_run_git_command", return_value=ls_remote_result),
            mock.patch.object(
                self_update,
                "_get_git_change_summary",
                return_value=(["abcd1234 Improve update notices"], 1),
            ),
        ):
            update = self_update._check_git_install("0.2.11")

        self.assertIsNotNone(update)
        assert update is not None
        self.assertTrue(update.available)
        self.assertEqual(update.latest, "newcommi")
        self.assertEqual(update.changes, ["abcd1234 Improve update notices"])
        self.assertEqual(update.additional_changes, 1)
